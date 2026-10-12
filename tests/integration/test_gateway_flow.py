import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from gateway.main import app
from gateway.policy.schema import ArgumentRule, QuotaConfig, SecurityPolicy, ToolPolicy
from storage.database import init_schema

TEST_DB = "test_gateway_integration.db"


@pytest_asyncio.fixture(autouse=True)
async def setup_env():
    os.environ["DATABASE_PATH"] = TEST_DB
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass
    await init_schema(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_full_gateway_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a test policy
        policy = SecurityPolicy(
            policy_id="prod-finance-agent",
            version=1,
            description="Production Finance Agent Policy",
            quota=QuotaConfig(max_requests_per_window=3, window_seconds=60),
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
            ),
        )

        reg_resp = await client.post("/policies", json={"policy": policy.model_dump(mode="json")})
        assert reg_resp.status_code == 201
        data = reg_resp.json()
        assert data["commitment_hash"].startswith("0x")

        # 2. Execute allowed tool (within quota)
        exec_resp = await client.post(
            "/actions/execute",
            json={
                "policy_id": "prod-finance-agent",
                "tool_name": "read_safe_document",
                "arguments": {"path": "/reports/q3.pdf"},
            },
        )
        assert exec_resp.status_code == 200
        exec_data = exec_resp.json()
        assert exec_data["decision"] == "ALLOWED"
        assert exec_data["status"] == "executed"
        assert exec_data["result"]["bytes_read"] == 128

        # 3. Unauthorized tool (default-deny)
        unauth_resp = await client.post(
            "/actions/execute",
            json={
                "policy_id": "prod-finance-agent",
                "tool_name": "delete_all_records",
                "arguments": {},
            },
        )
        assert unauth_resp.status_code == 200
        unauth_data = unauth_resp.json()
        assert unauth_data["decision"] == "DENIED"
        assert unauth_data["violations"][0]["code"] == "TOOL_NOT_REGISTERED"

        # 4. Sensitive action requires approval
        appr_resp = await client.post(
            "/actions/execute",
            json={
                "policy_id": "prod-finance-agent",
                "tool_name": "execute_transfer",
                "arguments": {"recipient": "0x123", "amount_mon": 5.0},
            },
        )
        assert appr_resp.status_code == 200
        appr_data = appr_resp.json()
        assert appr_data["decision"] == "PENDING_APPROVAL"

        # 5. Check audit logs
        audit_resp = await client.get("/audit/events")
        assert audit_resp.status_code == 200
        events = audit_resp.json()["events"]
        assert len(events) >= 3
