from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel


class AgentFenceError(Exception):
    """Base error raised by AgentFence SDK."""
    pass


class PolicyDeniedError(AgentFenceError):
    """Raised when an action request is blocked by policy."""
    def __init__(self, message: str, violations: list):
        super().__init__(message)
        self.violations = violations


class QuotaExceededError(AgentFenceError):
    """Raised when request quota has been exceeded."""
    pass


class ApprovalPendingError(AgentFenceError):
    """Raised when an action requires explicit human approval."""
    pass


class AgentFenceClient:
    """
    Python SDK for calling protected tools through the AgentFence Gateway.
    Encapsulates connection lifecycle, strict error mapping, and diagnostic headers.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", policy_id: str = "default-policy"):
        self.base_url = base_url.rstrip("/")
        self.policy_id = policy_id
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0),
        )

    async def close(self):
        await self._client.aclose()

    async def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Submits an action execution request to the gateway.
        Raises specific typed exceptions on policy denials or quota limits.
        """
        payload = {
            "policy_id": self.policy_id,
            "tool_name": tool_name,
            "arguments": arguments or {},
        }

        try:
            resp = await self._client.post("/actions/execute", json=payload)
        except httpx.TransportError as exc:
            raise AgentFenceError(f"Gateway connection error: {str(exc)}") from exc

        if resp.status_code == 400:
            raise AgentFenceError(f"Bad request: {resp.text}")

        data = resp.json()
        decision = data.get("decision")

        if decision == "DENIED":
            violations = data.get("violations", [])
            for v in violations:
                if v.get("code") == "QUOTA_EXHAUSTED":
                    raise QuotaExceededError(v.get("message", "Quota exceeded"))
            raise PolicyDeniedError("Action was denied by AgentFence policy engine", violations)

        if decision == "PENDING_APPROVAL":
            raise ApprovalPendingError(
                f"Action '{tool_name}' requires human-in-the-loop approval before execution."
            )

        if decision == "ALLOWED":
            return data.get("result", {})

        raise AgentFenceError(f"Unknown gateway response decision: {decision}")
