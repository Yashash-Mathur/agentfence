import hashlib
import json
from typing import Any, Dict, Tuple
from eth_utils import keccak
from gateway.policy.schema import SecurityPolicy


def serialize_canonical_policy(policy: SecurityPolicy) -> bytes:
    """
    Serializes a SecurityPolicy to RFC-8785 style canonical JSON.
    - Sorted dictionary keys.
    - Compact separators (no superfluous whitespace).
    - UTF-8 encoding.
    Ensures identical byte sequence across languages and implementations.
    """
    data = policy.model_dump(mode="json")
    canonical_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return canonical_str.encode("utf-8")


def compute_canonical_policy_commitment(policy: SecurityPolicy) -> str:
    """
    Computes a canonical Keccak-256 commitment hash (bytes32 hex).
    Compatible with EVM smart contracts.
    """
    canonical_bytes = serialize_canonical_policy(policy)
    digest = keccak(canonical_bytes)
    return "0x" + digest.hex()


class EvidenceVerifier:
    """
    Independent Evidence & Policy Verifier.
    Enables auditors or third parties to verify whether an off-chain policy definition
    matches an on-chain cryptographic commitment anchored to Monad.
    """

    @staticmethod
    def verify_policy_commitment(
        policy: SecurityPolicy,
        expected_commitment_hash: str,
    ) -> Tuple[bool, str]:
        """
        Verifies whether the computed hash of the policy matches expected_commitment_hash.
        Returns: (is_valid, computed_hash)
        """
        computed = compute_canonical_policy_commitment(policy)
        # Normalize hex strings
        norm_expected = expected_commitment_hash.lower()
        if not norm_expected.startswith("0x"):
            norm_expected = "0x" + norm_expected
        is_valid = computed.lower() == norm_expected
        return is_valid, computed
