from contextlib import asynccontextmanager
import asyncio
import os
import time
import uuid
from typing import Any, Dict, List, Optional
import aiosqlite
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gateway.executor import ControlledExecutor, ToolExecutionError
from gateway.middleware import DiagnosticsMiddleware
from gateway.policy.engine import PolicyEngine
from gateway.policy.schema import (
    ArgumentRule, QuotaConfig, SecurityPolicy, ToolPolicy
)
from gateway.quota import QuotaExhaustedError, QuotaManager
from storage.database import DEFAULT_DB_PATH, get_db_connection, init_schema
from storage.repositories.policies import AuditRepository, PolicyRepository
from verifier.verifier import EvidenceVerifier, compute_canonical_policy_commitment

# Global components
executor = ControlledExecutor(timeout_seconds=5.0)

# Demo policy definition — reused by /demo/setup and /demo/run
DEMO_POLICY = SecurityPolicy(
    policy_id="demo-finance-agent",
    version=1,
    description="Production Autonomous Finance Agent Boundary",
    quota=QuotaConfig(max_requests_per_window=100, window_seconds=3600),
    allowed_tools=(
        ToolPolicy(
            tool_name="read_safe_document",
            allowed=True,
            argument_rules=(
                ArgumentRule(name="path", data_type="string", required=True),
            ),
        ),
        ToolPolicy(
            tool_name="execute_transfer",
            allowed=True,
            requires_approval=True,
            argument_rules=(
                ArgumentRule(name="recipient", data_type="string", required=True),
                ArgumentRule(name="amount_mon", data_type="float", required=True),
            ),
        ),
        ToolPolicy(
            tool_name="send_alert",
            allowed=True,
            argument_rules=(
                ArgumentRule(name="channel", data_type="string", required=True),
                ArgumentRule(name="message", data_type="string", required=True),
            ),
        ),
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    await init_schema(db_path)
    # Auto-seed demo policy on startup so dashboard works immediately
    conn = await get_db_connection(db_path)
    try:
        existing = await PolicyRepository.get_active_policy(conn, DEMO_POLICY.policy_id)
        if not existing:
            await PolicyRepository.save_policy(conn, DEMO_POLICY)
    finally:
        await conn.close()
    yield


app = FastAPI(
    title="AgentFence Security Gateway",
    description="Deterministic security and accountability boundary for AI agents.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(DiagnosticsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Request & Response Schemas
# ==============================================================================

class ActionRequest(BaseModel):
    policy_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    request_id: str
    decision: str
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
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    try:
        async with conn.execute("SELECT COUNT(*) FROM audit_events") as cur:
            row = await cur.fetchone()
            total_events = row[0] if row else 0
        return {
            "status": "ok",
            "service": "AgentFence Gateway",
            "boundary": "active",
            "total_audit_events": total_events,
        }
    finally:
        await conn.close()


@app.post("/policies", status_code=status.HTTP_201_CREATED)
async def register_policy(req: PolicyRegistrationRequest):
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
            "monad_contract": "0x1D3Db94C310B5ecA586bBac035C8030c9cad6068",
            "anchor_tx": "0x81cc7f547be3860c42f47242197a328e4e95a6fc49129e63ef7d7c58dbe736fb",
            "anchor_block": 70481801,
        }
    finally:
        await conn.close()


@app.get("/demo/setup")
async def demo_setup():
    """Ensures the demo policy exists — safe to call repeatedly."""
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    try:
        existing = await PolicyRepository.get_active_policy(conn, DEMO_POLICY.policy_id)
        if not existing:
            await PolicyRepository.save_policy(conn, DEMO_POLICY)
            action = "registered"
        else:
            action = "already_active"
        commitment_hash = compute_canonical_policy_commitment(DEMO_POLICY)
        return {
            "status": action,
            "policy_id": DEMO_POLICY.policy_id,
            "version": DEMO_POLICY.version,
            "commitment_hash": commitment_hash,
        }
    finally:
        await conn.close()


@app.post("/demo/run")
async def run_demo_scenario():
    """
    Executes the full demonstration scenario in-process:
    1. Allowed: read_safe_document
    2. Allowed: send_alert
    3. DENIED: drop_production_database (not in policy)
    4. DENIED: exec_arbitrary_shell (not in policy)
    5. PENDING_APPROVAL: execute_transfer (requires human approval)
    Returns structured results for each step.
    """
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)

    DEMO_STEPS = [
        {
            "step": 1,
            "label": "📄 Read verified system document",
            "policy_id": "demo-finance-agent",
            "tool_name": "read_safe_document",
            "arguments": {"path": "/analytics/q3_metrics.json"},
        },
        {
            "step": 2,
            "label": "🔔 Send operational alert",
            "policy_id": "demo-finance-agent",
            "tool_name": "send_alert",
            "arguments": {"channel": "ops-team-slack", "message": "Q3 metrics review completed."},
        },
        {
            "step": 3,
            "label": "💀 Attempt database wipe (prompt injection)",
            "policy_id": "demo-finance-agent",
            "tool_name": "drop_production_database",
            "arguments": {"target": "all_records"},
        },
        {
            "step": 4,
            "label": "💀 Attempt shell command (tool hijack)",
            "policy_id": "demo-finance-agent",
            "tool_name": "exec_arbitrary_shell",
            "arguments": {"command": "rm -rf /"},
        },
        {
            "step": 5,
            "label": "🔒 Request treasury transfer (approval gate)",
            "policy_id": "demo-finance-agent",
            "tool_name": "execute_transfer",
            "arguments": {
                "recipient": "0x1111111111111111111111111111111111111111",
                "amount_mon": 2.5,
            },
        },
    ]

    results = []
    for step in DEMO_STEPS:
        conn = await get_db_connection(db_path)
        req_id = str(uuid.uuid4())[:8]
        start_ts = time.perf_counter()
        try:
            policy = await PolicyRepository.get_active_policy(conn, step["policy_id"])
            if not policy:
                results.append({**step, "decision": "ERROR", "reason": "Policy not found"})
                continue

            eval_result = PolicyEngine.evaluate(policy, step["tool_name"], step["arguments"])

            if not eval_result.authorized:
                latency_ms = (time.perf_counter() - start_ts) * 1000.0
                err_code = eval_result.violations[0].code if eval_result.violations else "POLICY_VIOLATION"
                await AuditRepository.record_event(
                    conn, req_id, policy.policy_id, policy.version, step["tool_name"],
                    eval_result.action_fingerprint, "DENIED", "REJECTED", err_code, round(latency_ms, 2)
                )
                results.append({
                    "step": step["step"],
                    "label": step["label"],
                    "tool_name": step["tool_name"],
                    "decision": "DENIED",
                    "reason": eval_result.violations[0].code if eval_result.violations else "unknown",
                    "latency_ms": round(latency_ms, 2),
                })
                continue

            if eval_result.requires_approval:
                latency_ms = (time.perf_counter() - start_ts) * 1000.0
                await AuditRepository.record_event(
                    conn, req_id, policy.policy_id, policy.version, step["tool_name"],
                    eval_result.action_fingerprint, "PENDING_APPROVAL", "SUSPENDED", None, round(latency_ms, 2)
                )
                results.append({
                    "step": step["step"],
                    "label": step["label"],
                    "tool_name": step["tool_name"],
                    "decision": "PENDING_APPROVAL",
                    "reason": "Human-in-the-loop approval required before execution",
                    "latency_ms": round(latency_ms, 2),
                })
                continue

            try:
                await QuotaManager.try_reserve_quota(
                    conn, policy.policy_id,
                    policy.quota.max_requests_per_window, policy.quota.window_seconds
                )
            except QuotaExhaustedError as qe:
                latency_ms = (time.perf_counter() - start_ts) * 1000.0
                await AuditRepository.record_event(
                    conn, req_id, policy.policy_id, policy.version, step["tool_name"],
                    eval_result.action_fingerprint, "DENIED", "REJECTED", "QUOTA_EXHAUSTED", round(latency_ms, 2)
                )
                results.append({
                    "step": step["step"], "label": step["label"],
                    "tool_name": step["tool_name"], "decision": "DENIED",
                    "reason": "QUOTA_EXHAUSTED", "latency_ms": round(latency_ms, 2),
                })
                continue

            exec_output = await executor.execute(step["tool_name"], step["arguments"])
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, req_id, policy.policy_id, policy.version, step["tool_name"],
                eval_result.action_fingerprint, "ALLOWED", "SUCCESS", None, round(latency_ms, 2)
            )
            results.append({
                "step": step["step"],
                "label": step["label"],
                "tool_name": step["tool_name"],
                "decision": "ALLOWED",
                "result": exec_output,
                "latency_ms": round(latency_ms, 2),
            })

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            results.append({
                "step": step["step"], "label": step["label"],
                "tool_name": step["tool_name"], "decision": "ERROR",
                "reason": str(exc), "latency_ms": round(latency_ms, 2),
            })
        finally:
            await conn.close()

    return {"scenario": "demo-finance-agent", "steps": results}


@app.post("/actions/execute", response_model=ActionResponse)
async def execute_action(req: ActionRequest, request: Request):
    request_id = getattr(request.state, "request_id", "req-unknown")
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    start_ts = time.perf_counter()

    try:
        policy = await PolicyRepository.get_active_policy(conn, req.policy_id)
        if not policy:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, req.policy_id, 0, req.tool_name,
                "none", "DENIED", "REJECTED", "POLICY_NOT_FOUND", latency_ms
            )
            raise HTTPException(status_code=400, detail="Active policy not found for given policy_id")

        eval_result = PolicyEngine.evaluate(policy, req.tool_name, req.arguments)

        if not eval_result.authorized:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            err_code = eval_result.violations[0].code if eval_result.violations else "POLICY_VIOLATION"
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "DENIED", "REJECTED", err_code, latency_ms
            )
            return ActionResponse(
                request_id=request_id, decision="DENIED", status="rejected",
                violations=[v.model_dump() for v in eval_result.violations],
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id, policy_version=policy.version,
            )

        if eval_result.requires_approval:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "PENDING_APPROVAL", "SUSPENDED", None, latency_ms
            )
            return ActionResponse(
                request_id=request_id, decision="PENDING_APPROVAL",
                status="suspended_pending_review",
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id, policy_version=policy.version,
            )

        try:
            await QuotaManager.try_reserve_quota(
                conn, policy.policy_id,
                policy.quota.max_requests_per_window, policy.quota.window_seconds,
            )
        except QuotaExhaustedError as qe:
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "DENIED", "REJECTED", "QUOTA_EXHAUSTED", latency_ms
            )
            return ActionResponse(
                request_id=request_id, decision="DENIED", status="rejected",
                violations=[{"code": "QUOTA_EXHAUSTED", "message": str(qe)}],
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id, policy_version=policy.version,
            )

        try:
            exec_output = await executor.execute(req.tool_name, req.arguments)
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            await AuditRepository.record_event(
                conn, request_id, policy.policy_id, policy.version, req.tool_name,
                eval_result.action_fingerprint, "ALLOWED", "SUCCESS", None, latency_ms
            )
            return ActionResponse(
                request_id=request_id, decision="ALLOWED", status="executed",
                result=exec_output,
                action_fingerprint=eval_result.action_fingerprint,
                policy_id=policy.policy_id, policy_version=policy.version,
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
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    try:
        events = await AuditRepository.list_events(conn, limit)
        return {"events": events, "count": len(events)}
    finally:
        await conn.close()


@app.get("/quota/usage")
async def get_quota_usage(policy_id: str = "demo-finance-agent"):
    """Returns current quota usage for the dashboard."""
    import time as tmod
    db_path = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
    conn = await get_db_connection(db_path)
    try:
        policy = await PolicyRepository.get_active_policy(conn, policy_id)
        if not policy:
            return {"used": 0, "max": 100, "window_seconds": 3600}
        from gateway.quota import QuotaManager
        bucket = QuotaManager.calculate_window_bucket(policy.quota.window_seconds)
        async with conn.execute(
            "SELECT COALESCE(SUM(allocated_count), 0) FROM quota_reservations WHERE policy_id=? AND window_bucket=?",
            (policy_id, bucket),
        ) as cur:
            row = await cur.fetchone()
            used = row[0] if row else 0
        return {
            "policy_id": policy_id,
            "used": used,
            "max": policy.quota.max_requests_per_window,
            "window_seconds": policy.quota.window_seconds,
        }
    finally:
        await conn.close()
