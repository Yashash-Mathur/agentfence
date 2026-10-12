import pytest
from gateway.policy.schema import ArgumentRule, QuotaConfig, SecurityPolicy, ToolPolicy
from verifier.verifier import EvidenceVerifier, compute_canonical_policy_commitment


@pytest.fixture
def policy_for_verification() -> SecurityPolicy:
    return SecurityPolicy(
        policy_id="verifiable-agent-pol",
        version=1,
        description="Verifiable Policy for Testing",
        quota=QuotaConfig(max_requests_per_window=50, window_seconds=3600),
        allowed_tools=(
            ToolPolicy(
                tool_name="read_safe_document",
                allowed=True,
                argument_rules=(
                    ArgumentRule(name="path", data_type="string", required=True),
                ),
            ),
        ),
    )


def test_canonical_commitment_deterministic(policy_for_verification):
    # Two independent commitment hashes on the same object must produce identical strings
    h1 = compute_canonical_policy_commitment(policy_for_verification)
    h2 = compute_canonical_policy_commitment(policy_for_verification)
    assert h1 == h2
    assert h1.startswith("0x")
    assert len(h1) == 66  # 32 bytes hex with 0x


def test_verifier_accepts_valid_commitment(policy_for_verification):
    valid_hash = compute_canonical_policy_commitment(policy_for_verification)
    is_valid, computed = EvidenceVerifier.verify_policy_commitment(
        policy_for_verification, valid_hash
    )
    assert is_valid is True
    assert computed == valid_hash


def test_verifier_rejects_tampered_policy(policy_for_verification):
    original_hash = compute_canonical_policy_commitment(policy_for_verification)

    # Malicious actor tampers with quota or permissions
    tampered_policy = policy_for_verification.model_copy(
        update={"quota": QuotaConfig(max_requests_per_window=999999, window_seconds=3600)}
    )

    is_valid, computed = EvidenceVerifier.verify_policy_commitment(
        tampered_policy, original_hash
    )
    assert is_valid is False
    assert computed != original_hash
