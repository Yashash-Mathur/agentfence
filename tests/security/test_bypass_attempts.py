import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from gateway.main import app
from gateway.policy.schema import ArgumentRule, QuotaConfig, SecurityPolicy, ToolPolicy
from storage.database import init_schema

TEST_DB = "test_security_harden.db"


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
async def test_bypass_attempts_and_malformed_arguments():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register standard policy
        policy = SecurityPolicy(
            policy_id="hardened-agent",
            version=1,
            description="Hardened Security Policy",
            quota=QuotaConfig(max_requests_per_window=5, window_seconds=60),
            allowed_tools=(
                ToolPolicy(
                    tool_name="read_safe_document",
                    allowed=True,
                    argument_rules=(
                        ArgumentRule(
                            name="path",
                            data_type="string",
                            required=True,
                            regex_pattern=r"^/safe/[a-zA-Z0-9_\-\.]+$",
                        ),
                    ),
                ),
            ),
        )
        await client.post("/policies", json={"policy": policy.model_dump(mode="json")})

        # 1. Path traversal injection
        pt_resp = await client.post(
            "/actions/execute",
            json={
                "policy_id": "hardened-agent",
                "tool_name": "read_safe_document",
                "arguments": {"path": "../../../etc/shadow"},
            },
        )
        assert pt_resp.status_code == 200
        pt_data = pt_resp.json()
        assert pt_data["decision"] == "DENIED"
        assert any(v["code"] == "ARGUMENT_PATTERN_MISMATCH" for v in pt_data["violations"])

        # 2. Argument injection / parameter smuggling
        smuggle_resp = await client.post(
            "/actions/execute",
            json={
                "policy_id": "hardened-agent",
                "tool_name": "read_safe_document",
                "arguments": {
                    "path": "/safe/valid.txt",
                    "admin_override": True,  # Unexpected argument
                },
            },
        )
        assert smuggle_resp.status_code == 200
        smuggle_data = smuggle_resp.json()
        assert smuggle_data["decision"] == "DENIED"
        assert any(v["code"] == "UNEXPECTED_ARGUMENT" for v in smuggle_data["violations"])

        # 3. Type confusion attack (passing integer for string path)
        type_resp = await client.post(
            "/actions/execute",
            json={
                "policy_id": "hardened-agent",
                "tool_name": "read_safe_document",
                "arguments": {"path": 12345},
            },
        )
        assert type_resp.status_code == 200
        type_data = type_resp.json()
        assert type_data["decision"] == "DENIED"
        assert any(v["code"] == "ARGUMENT_TYPE_MISMATCH" for v in type_data["violations"])

        # 4. Non-existent tool call
        fake_tool_resp = await client.post(
            "/actions/execute",
            json={
                "policy_id": "hardened-agent",
                "tool_name": "exec_arbitrary_shell",
                "arguments": {"command": "rm -rf /"},
            },
        )
        assert fake_tool_resp.status_code == 200
        fake_data = fake_tool_resp.json()
        assert fake_data["decision"] == "DENIED"
        assert any(v["code"] == "TOOL_NOT_REGISTERED" for v in fake_data["violations"])
