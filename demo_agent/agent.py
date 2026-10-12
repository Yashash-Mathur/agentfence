import asyncio
from typing import Any, Dict, List
from sdk.client import (
    AgentFenceClient,
    ApprovalPendingError,
    PolicyDeniedError,
    QuotaExceededError,
)


class AutonomousDemoAgent:
    """
    Demonstration AI Agent acting through the AgentFence protected boundary.
    Performs standard operational workflows:
    1. Reads verified system document (Authorized).
    2. Attempts an unauthorized file-system wipe (Default Deny).
    3. Requests a sensitive treasury transfer (Approval Required).
    4. Triggers rapid requests to demonstrate atomic quota enforcement.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", policy_id: str = "demo-finance-agent"):
        self.client = AgentFenceClient(base_url=base_url, policy_id=policy_id)

    async def run_scenario(self) -> List[Dict[str, Any]]:
        scenario_log = []

        # --- Action 1: Legitimate Allowed Action ---
        scenario_log.append({"action": "read_safe_document", "intent": "Read operational metrics"})
        try:
            res = await self.client.execute_tool(
                "read_safe_document",
                {"path": "/analytics/q3_metrics.json"},
            )
            scenario_log.append({
                "action": "read_safe_document",
                "status": "SUCCESS",
                "result": res,
            })
        except Exception as e:
            scenario_log.append({
                "action": "read_safe_document",
                "status": "FAILED",
                "error": str(e),
            })

        # --- Action 2: Adversarial / Prohibited Action (Direct Bypass / Tool Hijack attempt) ---
        scenario_log.append({"action": "drop_production_database", "intent": "Attacker prompt injection"})
        try:
            res = await self.client.execute_tool(
                "drop_production_database",
                {"target": "all_records"},
            )
            scenario_log.append({
                "action": "drop_production_database",
                "status": "UNEXPECTED_SUCCESS",
                "result": res,
            })
        except PolicyDeniedError as pde:
            scenario_log.append({
                "action": "drop_production_database",
                "status": "BLOCKED_BY_POLICY",
                "message": str(pde),
                "violations": pde.violations,
            })
        except Exception as e:
            scenario_log.append({
                "action": "drop_production_database",
                "status": "FAILED",
                "error": str(e),
            })

        # --- Action 3: Sensitive Action (Human Approval Required) ---
        scenario_log.append({"action": "execute_transfer", "intent": "Treasury payout"})
        try:
            res = await self.client.execute_tool(
                "execute_transfer",
                {"recipient": "0x1111111111111111111111111111111111111111", "amount_mon": 2.5},
            )
            scenario_log.append({
                "action": "execute_transfer",
                "status": "UNEXPECTED_SUCCESS",
                "result": res,
            })
        except ApprovalPendingError as ape:
            scenario_log.append({
                "action": "execute_transfer",
                "status": "INTERCEPTED_APPROVAL_REQUIRED",
                "message": str(ape),
            })

        await self.client.close()
        return scenario_log
