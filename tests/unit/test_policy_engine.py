import pytest
from gateway.policy.schema import (
    ArgumentRule,
    QuotaConfig,
    SecurityPolicy,
    ToolPolicy,
)
from gateway.policy.engine import PolicyEngine


@pytest.fixture
def sample_policy() -> SecurityPolicy:
    return SecurityPolicy(
        policy_id="test-policy-1",
        version=1,
        description="Test policy for policy engine",
        is_revoked=False,
        quota=QuotaConfig(max_requests_per_window=10, window_seconds=60),
        allowed_tools=(
            ToolPolicy(
                tool_name="read_file",
                allowed=True,
                requires_approval=False,
                argument_rules=(
                    ArgumentRule(
                        name="path",
                        data_type="string",
                        required=True,
                        max_length=100,
                        regex_pattern=r"^/safe/[a-zA-Z0-9_\-\.]+$",
                    ),
                ),
            ),
            ToolPolicy(
                tool_name="send_payout",
                allowed=True,
                requires_approval=True,
                argument_rules=(
                    ArgumentRule(
                        name="recipient",
                        data_type="string",
                        required=True,
                        regex_pattern=r"^0x[a-fA-F0-9]{40}$",
                    ),
                    ArgumentRule(
                        name="amount_mon",
                        data_type="float",
                        required=True,
                        min_value=0.01,
                        max_value=10.0,
                    ),
                ),
            ),
            ToolPolicy(
                tool_name="dangerous_format_disk",
                allowed=False,
                requires_approval=False,
            ),
        ),
    )


def test_allowed_action_succeeds(sample_policy):
    result = PolicyEngine.evaluate(
        sample_policy,
        tool_name="read_file",
        arguments={"path": "/safe/data.json"},
    )
    assert result.authorized is True
    assert result.requires_approval is False
    assert len(result.violations) == 0
    assert result.action_fingerprint is not None


def test_unknown_tool_rejected_default_deny(sample_policy):
    result = PolicyEngine.evaluate(
        sample_policy,
        tool_name="exec_system_bash",
        arguments={"cmd": "whoami"},
    )
    assert result.authorized is False
    assert any(v.code == "TOOL_NOT_REGISTERED" for v in result.violations)


def test_explicitly_disallowed_tool_rejected(sample_policy):
    result = PolicyEngine.evaluate(
        sample_policy,
        tool_name="dangerous_format_disk",
        arguments={},
    )
    assert result.authorized is False
    assert any(v.code == "TOOL_EXPLICITLY_DISALLOWED" for v in result.violations)


def test_missing_required_argument_rejected(sample_policy):
    result = PolicyEngine.evaluate(
        sample_policy,
        tool_name="read_file",
        arguments={},
    )
    assert result.authorized is False
    assert any(v.code == "ARGUMENT_MISSING" for v in result.violations)


def test_argument_regex_violation_rejected(sample_policy):
    # Path traversal attempt
    result = PolicyEngine.evaluate(
        sample_policy,
        tool_name="read_file",
        arguments={"path": "/etc/passwd"},
    )
    assert result.authorized is False
    assert any(v.code == "ARGUMENT_PATTERN_MISMATCH" for v in result.violations)


def test_argument_bounds_violation_rejected(sample_policy):
    # Payout too high
    result = PolicyEngine.evaluate(
        sample_policy,
        tool_name="send_payout",
        arguments={
            "recipient": "0x1111111111111111111111111111111111111111",
            "amount_mon": 500.0,
        },
    )
    assert result.authorized is False
    assert any(v.code == "ARGUMENT_VALUE_TOO_HIGH" for v in result.violations)


def test_approval_required_action_flagged(sample_policy):
    result = PolicyEngine.evaluate(
        sample_policy,
        tool_name="send_payout",
        arguments={
            "recipient": "0x1111111111111111111111111111111111111111",
            "amount_mon": 1.5,
        },
    )
    assert result.authorized is True
    assert result.requires_approval is True
    assert len(result.violations) == 0


def test_revoked_policy_rejects_all(sample_policy):
    revoked = sample_policy.model_copy(update={"is_revoked": True})
    result = PolicyEngine.evaluate(
        revoked,
        tool_name="read_file",
        arguments={"path": "/safe/data.json"},
    )
    assert result.authorized is False
    assert any(v.code == "POLICY_REVOKED" for v in result.violations)
