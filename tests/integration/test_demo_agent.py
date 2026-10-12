import asyncio
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from demo_agent.agent import AutonomousDemoAgent
from gateway.main import app
from gateway.policy.schema import ArgumentRule, QuotaConfig, SecurityPolicy, ToolPolicy
from storage.database import init_schema

TEST_DB = "test_demo_agent_run.db"


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
async def test_demo_agent_full_behavior():
    # Setup the policy for the demo agent
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        policy = SecurityPolicy(
            policy_id="demo-finance-agent",
            version=1,
            description="Demo Finance Agent Boundary",
            quota=QuotaConfig(max_requests_per_window=10, window_seconds=60),
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
        res = await client.post("/policies", json={"policy": policy.model_dump(mode="json")})
        assert res.status_code == 201

        # Use demo agent directly against the app
        agent = AutonomousDemoAgent(base_url="http://test", policy_id="demo-finance-agent")
        # Route agent's internal client through test ASGI transport
        agent.client._client = client

        log = await agent.run_scenario()

        # Check action 1: read_safe_document was successful
        read_event = [e for e in log if e.get("action") == "read_safe_document" and "status" in e][0]
        assert read_event["status"] == "SUCCESS"

        # Check action 2: drop_production_database was blocked by policy
        blocked_event = [e for e in log if e.get("action") == "drop_production_database" and "status" in e][0]
        assert blocked_event["status"] == "BLOCKED_BY_POLICY"
        assert any(v["code"] == "TOOL_NOT_REGISTERED" for v in blocked_event["violations"])

        # Check action 3: execute_transfer was intercepted
        appr_event = [e for e in log if e.get("action") == "execute_transfer" and "status" in e][0]
        assert appr_event["status"] == "INTERCEPTED_APPROVAL_REQUIRED"
