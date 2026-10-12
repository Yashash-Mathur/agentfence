// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AgentFencePolicy
 * @dev Anchors AI Agent Security Policies on Monad.
 * Supports:
 * - Deterministic policy versioning with monotonic sequence checks.
 * - Domain-separated policy commitment hashes.
 * - Explicit emergency revocation state.
 * - Gas-optimized, parallel-execution friendly storage partitioning.
 */
contract AgentFencePolicy {
    // Domain separator for cryptographic commitments
    bytes32 public constant COMMITMENT_DOMAIN = keccak256("AgentFence.Policy.v1");

    // Owner / Administrator of the policy contract
    address public immutable owner;

    struct PolicyRecord {
        uint64 version;
        bytes32 commitmentHash;
        uint64 anchoredAt;
        bool isRevoked;
    }

    // Partitioned storage by policyId string hash to prevent parallel-execution contention
    mapping(bytes32 => PolicyRecord) public policies;

    // Events emitted for off-chain indexers and independent verification
    event PolicyAnchored(
        bytes32 indexed policyKey,
        string policyId,
        uint64 indexed version,
        bytes32 commitmentHash,
        uint64 timestamp
    );

    event PolicyRevoked(
        bytes32 indexed policyKey,
        string policyId,
        uint64 indexed version,
        uint64 timestamp
    );

    error Unauthorized();
    error InvalidPolicyId();
    error VersionMustIncrease(uint64 currentVersion, uint64 submittedVersion);
    error ZeroCommitmentHash();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Computes storage key for a policyId.
     */
    function getPolicyKey(string calldata policyId) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(policyId));
    }

    /**
     * @notice Anchors a new version and cryptographic commitment for a policy.
     * Enforces strictly increasing version numbers to block reordering attacks.
     */
    function anchorPolicy(
        string calldata policyId,
        uint64 version,
        bytes32 commitmentHash
    ) external onlyOwner {
        if (bytes(policyId).length == 0) revert InvalidPolicyId();
        if (commitmentHash == bytes32(0)) revert ZeroCommitmentHash();

        bytes32 key = getPolicyKey(policyId);
        PolicyRecord storage record = policies[key];

        if (version <= record.version) {
            revert VersionMustIncrease(record.version, version);
        }

        record.version = version;
        record.commitmentHash = commitmentHash;
        record.anchoredAt = uint64(block.timestamp);
        record.isRevoked = false;

        emit PolicyAnchored(key, policyId, version, commitmentHash, uint64(block.timestamp));
    }

    /**
     * @notice Explicitly marks a policy as revoked in emergency scenarios.
     */
    function revokePolicy(string calldata policyId) external onlyOwner {
        bytes32 key = getPolicyKey(policyId);
        PolicyRecord storage record = policies[key];

        record.isRevoked = true;

        emit PolicyRevoked(key, policyId, record.version, uint64(block.timestamp));
    }

    /**
     * @notice Verifies if a given policy commitment hash matches the active on-chain state.
     */
    function verifyCommitment(
        string calldata policyId,
        bytes32 expectedHash
    ) external view returns (bool isValid, bool isRevoked, uint64 activeVersion) {
        bytes32 key = getPolicyKey(policyId);
        PolicyRecord storage record = policies[key];

        isValid = (record.commitmentHash == expectedHash && expectedHash != bytes32(0));
        isRevoked = record.isRevoked;
        activeVersion = record.version;
    }
}
