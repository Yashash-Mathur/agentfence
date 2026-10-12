import json
import uuid
from typing import Any, Dict, List, Optional
import aiosqlite
from gateway.policy.schema import SecurityPolicy
from verifier.verifier import compute_canonical_policy_commitment


class PolicyRepository:
    """Persistence repository for SecurityPolicy definitions."""

    @staticmethod
    async def save_policy(conn: aiosqlite.Connection, policy: SecurityPolicy) -> str:
        commitment_hash = compute_canonical_policy_commitment(policy)
        policy_json = policy.model_dump_json()

        await conn.execute("BEGIN IMMEDIATE;")
        try:
            # Set older versions inactive if this is active
            await conn.execute(
                "UPDATE policies SET is_active = 0 WHERE policy_id = ?;",
                (policy.policy_id,),
            )
            # Insert or replace
            await conn.execute(
                """
                INSERT INTO policies (policy_id, version, policy_json, commitment_hash, is_active, is_revoked)
                VALUES (?, ?, ?, ?, 1, ?);
                """,
                (policy.policy_id, policy.version, policy_json, commitment_hash, int(policy.is_revoked)),
            )
            await conn.execute("COMMIT;")
            return commitment_hash
        except Exception:
            await conn.execute("ROLLBACK;")
            raise

    @staticmethod
    async def get_active_policy(conn: aiosqlite.Connection, policy_id: str) -> Optional[SecurityPolicy]:
        async with conn.execute(
            """
            SELECT policy_json FROM policies
            WHERE policy_id = ? AND is_active = 1
            ORDER BY version DESC LIMIT 1;
            """,
            (policy_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            return SecurityPolicy.model_validate(data)

    @staticmethod
    async def revoke_policy(conn: aiosqlite.Connection, policy_id: str):
        await conn.execute("BEGIN IMMEDIATE;")
        try:
            await conn.execute(
                "UPDATE policies SET is_revoked = 1 WHERE policy_id = ?;",
                (policy_id,),
            )
            await conn.execute("COMMIT;")
        except Exception:
            await conn.execute("ROLLBACK;")
            raise


class AuditRepository:
    """Persistence repository for Audit events."""

    @staticmethod
    async def record_event(
        conn: aiosqlite.Connection,
        request_id: str,
        policy_id: str,
        policy_version: int,
        tool_name: str,
        action_fingerprint: str,
        decision: str,
        execution_status: str,
        error_code: Optional[str],
        latency_ms: float,
    ) -> str:
        event_id = str(uuid.uuid4())
        await conn.execute("BEGIN IMMEDIATE;")
        try:
            await conn.execute(
                """
                INSERT INTO audit_events (
                    event_id, request_id, policy_id, policy_version,
                    tool_name, action_fingerprint, decision, execution_status,
                    error_code, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event_id, request_id, policy_id, policy_version,
                    tool_name, action_fingerprint, decision, execution_status,
                    error_code, latency_ms
                ),
            )
            await conn.execute("COMMIT;")
            return event_id
        except Exception:
            await conn.execute("ROLLBACK;")
            raise

    @staticmethod
    async def list_events(conn: aiosqlite.Connection, limit: int = 50) -> List[Dict[str, Any]]:
        async with conn.execute(
            """
            SELECT event_id, request_id, policy_id, policy_version,
                   tool_name, action_fingerprint, decision, execution_status,
                   error_code, latency_ms, created_at
            FROM audit_events
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "event_id": r[0],
                    "request_id": r[1],
                    "policy_id": r[2],
                    "policy_version": r[3],
                    "tool_name": r[4],
                    "action_fingerprint": r[5],
                    "decision": r[6],
                    "execution_status": r[7],
                    "error_code": r[8],
                    "latency_ms": r[9],
                    "created_at": r[10],
                }
                for r in rows
            ]
