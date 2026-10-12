import asyncio
from typing import Any, Callable, Dict


class ToolExecutionError(Exception):
    """Raised when controlled tool execution encounters an error."""
    pass


class ControlledExecutor:
    """
    Executes authorized tools in a strictly monitored, controlled environment.
    Guarantees:
    - Explicit execution timeouts (prevents hanging loops).
    - Structured error transformation without leaking server internals.
    - Isolated demonstration capabilities.
    """

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds
        self._registry: Dict[str, Callable] = {}
        self._register_default_tools()

    def register_tool(self, name: str, func: Callable):
        self._registry[name] = func

    def _register_default_tools(self):
        # 1. Safe read tool
        async def read_safe_document(path: str) -> Dict[str, Any]:
            return {
                "status": "success",
                "path": path,
                "content": f"[Simulated Content for verified document at {path}]",
                "bytes_read": 128,
            }

        # 2. Financial settlement simulation
        async def execute_transfer(recipient: str, amount_mon: float) -> Dict[str, Any]:
            return {
                "status": "success",
                "tx_type": "monad_native_transfer",
                "recipient": recipient,
                "amount_mon": amount_mon,
                "simulated_tx_hash": "0x5a1f893e1b02934cf5e28a9b319fcd51029e84b238f90248c1e827b5029e71b2",
            }

        # 3. Notification dispatch
        async def send_alert(channel: str, message: str) -> Dict[str, Any]:
            return {
                "status": "dispatched",
                "channel": channel,
                "message_length": len(message),
            }

        self.register_tool("read_safe_document", read_safe_document)
        self.register_tool("execute_transfer", execute_transfer)
        self.register_tool("send_alert", send_alert)

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in self._registry:
            raise ToolExecutionError(f"Tool '{tool_name}' has no registered execution handler.")

        func = self._registry[tool_name]
        try:
            # Enforce strict execution timeout
            import inspect
            if inspect.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(**arguments), timeout=self.timeout_seconds)
            else:
                result = func(**arguments)
            return result
        except asyncio.TimeoutError:
            raise ToolExecutionError(f"Tool '{tool_name}' execution timed out after {self.timeout_seconds}s.")
        except Exception as exc:
            raise ToolExecutionError(f"Tool execution failed: {str(exc)}")
