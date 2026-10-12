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


@pytest.mark.asyncio
async def test_demo_runner_and_quota_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Setup demo policy
        setup_res = await client.get("/demo/setup")
        assert setup_res.status_code == 200
        assert setup_res.json()["policy_id"] == "demo-finance-agent"

        # 2. Run in-process 5-step scenario
        demo_res = await client.post("/demo/run")
        assert demo_res.status_code == 200
        steps = demo_res.json()["steps"]
        assert len(steps) == 5

        # Step 1: read_safe_document -> ALLOWED
        assert steps[0]["decision"] == "ALLOWED"
        # Step 2: send_alert -> ALLOWED
        assert steps[1]["decision"] == "ALLOWED"
        # Step 3: drop_production_database -> DENIED
        assert steps[2]["decision"] == "DENIED"
        # Step 4: exec_arbitrary_shell -> DENIED
        assert steps[3]["decision"] == "DENIED"
        # Step 5: execute_transfer -> PENDING_APPROVAL
        assert steps[4]["decision"] == "PENDING_APPROVAL"

        # 3. Quota usage tracking
        quota_res = await client.get("/quota/usage?policy_id=demo-finance-agent")
        assert quota_res.status_code == 200
        quota_data = quota_res.json()
        assert quota_data["used"] >= 2  # steps 1 and 2 reserved quota

