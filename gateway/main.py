from contextlib import asynccontextmanager
import os
import time
from typing import Any, Dict, List, Optional
import aiosqlite
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gateway.executor import ControlledExecutor, ToolExecutionError
from gateway.middleware import DiagnosticsMiddleware
from gateway.policy.engine import PolicyEngine
from gateway.policy.schema import SecurityPolicy
from gateway.quota import QuotaExhaustedError, QuotaManager
from storage.database import DEFAULT_DB_PATH, get_db_connection, init_schema
from storage.repositories.policies import AuditRepository, PolicyRepository
from verifier.verifier import EvidenceVerifier, compute_canonical_policy_commitment

# Global components
executor = ControlledExecutor(timeout_seconds=5.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    await init_schema(db_path)
    yield


app = FastAPI(
    title="AgentFence Security Gateway",
    description="Deterministic security and accountability boundary for AI agents.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(DiagnosticsMiddleware)


# ==============================================================================
# Request & Response Schemas
# ==============================================================================

class ActionRequest(BaseModel):
    policy_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    request_id: str
    decision: str  # ALLOWED | DENIED | PENDING_APPROVAL
    status: str
    result: Optional[Dict[str, Any]] = None
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    action_fingerprint: str
    policy_id: str
    policy_version: int


class PolicyRegistrationRequest(BaseModel):
    policy: SecurityPolicy


# ==============================================================================
# Routes
# ==============================================================================

@app.get("/")
async def get_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        from fastapi.responses import HTMLResponse
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"status": "ok", "service": "AgentFence Gateway"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "AgentFence Gateway", "boundary": "active"}


@app.post("/policies", status_code=status.HTTP_201_CREATED)
async def register_policy(req: PolicyRegistrationRequest):
    """Registers or updates a SecurityPolicy."""
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    try:
        commitment_hash = await PolicyRepository.save_policy(conn, req.policy)
        return {
            "status": "registered",
            "policy_id": req.policy.policy_id,
            "version": req.policy.version,
            "commitment_hash": commitment_hash,
        }
    finally:
        await conn.close()


@app.get("/policies/{policy_id}")
async def get_policy(policy_id: str):
    """Retrieves the active SecurityPolicy for a given ID."""
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    try:
        policy = await PolicyRepository.get_active_policy(conn, policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        commitment_hash = compute_canonical_policy_commitment(policy)
        return {
            "policy": policy.model_dump(),
            "commitment_hash": commitment_hash,
        }
    finally:
        await conn.close()


@app.post("/actions/execute", response_model=ActionResponse)
async def execute_action(req: ActionRequest, request: Request):
    """
    Primary Enforcement Boundary.
    Enforces deterministic policy evaluation, quota checks, and safe execution.
    """
    request_id = getattr(request.state, "request_id", "req-unknown")
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    start_ts = time.perf_counter()

    try:
        # 1. Fetch active policy
        policy = await PolicyRepository.get_active_policy(conn, req.policy_id)
        if not policy:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, req.policy_id, 0, req.tool_name,
                "none", "DENIED", "REJECTED", "POLICY_NOT_FOUND", latency_ms
            )
            raise HTTPException(status_code=400, detail="Active policy not found for given policy_id")

        # 2. Deterministic policy evaluation
        eval_result = PolicyEngine.evaluate(policy, req.tool_name, req.arguments)

        # 3. Denied Path
        if not eval_result.authorized:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            err_code = eval_result.violations[0].code if eval_result.violations else "POLICY_VIOLATION"
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "DENIED", "REJECTED", err_code, latency_ms
            )
            return ActionResponse(
                request_id=request_id,
                decision="DENIED",
                status="rejected",
                violations=[v.model_dump() for v in eval_result.violations],
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )

        # 4. Approval Gate Path
        if eval_result.requires_approval:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "PENDING_APPROVAL", "SUSPENDED", None, latency_ms
            )
            return ActionResponse(
                request_id=request_id,
                decision="PENDING_APPROVAL",
                status="suspended_pending_review",
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )

        # 5. Atomic Quota Reservation
        reservation_id = None
        try:
            reservation_id = await QuotaManager.try_reserve_quota(
                conn,
                policy.policy_id,
                policy.quota.max_requests_per_window,
                policy.quota.window_seconds,
            )
        except QuotaExhaustedError as qe:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "DENIED", "REJECTED", "QUOTA_EXHAUSTED", latency_ms
            )
            return ActionResponse(
                request_id=request_id,
                decision="DENIED",
                status="rejected",
                violations=[{"code": "QUOTA_EXHAUSTED", "message": str(qe)}],
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )

        # 6. Controlled Tool Execution
        try:
            exec_output = await executor.execute(req.tool_name, req.arguments)
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "ALLOWED", "SUCCESS", None, latency_ms
            )
            return ActionResponse(
                request_id=request_id,
                decision="ALLOWED",
                status="executed",
                result=exec_output,
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )
        except ToolExecutionError as tee:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "ALLOWED", "FAILED", "TOOL_EXECUTION_ERROR", latency_ms
            )
            raise HTTPException(status_code=500, detail=str(tee))

    finally:
        await conn.close()


@app.get("/audit/events")
async def get_audit_events(limit: int = 50):
    """Returns recent audit events for observability and dashboard."""
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    try:
        events = await AuditRepository.list_events(conn, limit)
        return {"events": events}
    finally:
        await conn.close()
