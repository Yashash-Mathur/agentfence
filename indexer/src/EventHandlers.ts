// ==============================================================================
// Envio Event Handlers for AgentFencePolicy
// Processes PolicyAnchored and PolicyRevoked events from Monad Testnet.
// ==============================================================================

import {
  AgentFencePolicy,
  Policy,
  PolicyAnchorEvent,
  PolicyRevocationEvent,
} from "generated";

// Handler for PolicyAnchored events
AgentFencePolicy.PolicyAnchored.handler(async ({ event, context }) => {
  const policyKey = event.params.policyKey.toString();
  const policyId = event.params.policyId;
  const version = BigInt(event.params.version.toString());
  const commitmentHash = event.params.commitmentHash.toString();
  const timestamp = BigInt(event.params.timestamp.toString());
  const blockNumber = BigInt(event.block.number);
  const txHash = event.transaction.hash;

  // 1. Create or update the aggregate Policy entity
  const policyEntity: Policy = {
    id: policyKey,
    policyId: policyId,
    activeVersion: version,
    commitmentHash: commitmentHash,
    isRevoked: false,
    anchoredAt: timestamp,
    lastUpdatedBlock: blockNumber,
    lastUpdatedTx: txHash,
  };
  context.Policy.set(policyEntity);

  // 2. Record historical audit event
  const eventId = `${txHash}-${event.logIndex}`;
  const anchorEvent: PolicyAnchorEvent = {
    id: eventId,
    policyKey: policyKey,
    policyId: policyId,
    version: version,
    commitmentHash: commitmentHash,
    timestamp: timestamp,
    blockNumber: blockNumber,
    transactionHash: txHash,
  };
  context.PolicyAnchorEvent.set(anchorEvent);

  context.log.info(
    `[AgentFence] Anchored policy '${policyId}' v${version} on Monad. Hash: ${commitmentHash}`
  );
});

// Handler for PolicyRevoked events
AgentFencePolicy.PolicyRevoked.handler(async ({ event, context }) => {
  const policyKey = event.params.policyKey.toString();
  const policyId = event.params.policyId;
  const version = BigInt(event.params.version.toString());
  const timestamp = BigInt(event.params.timestamp.toString());
  const blockNumber = BigInt(event.block.number);
  const txHash = event.transaction.hash;

  // 1. Fetch and update the active Policy entity
  const existingPolicy = await context.Policy.get(policyKey);
  if (existingPolicy) {
    const updatedPolicy: Policy = {
      ...existingPolicy,
      isRevoked: true,
      lastUpdatedBlock: blockNumber,
      lastUpdatedTx: txHash,
    };
    context.Policy.set(updatedPolicy);
  }

  // 2. Record historical revocation audit event
  const eventId = `${txHash}-${event.logIndex}`;
  const revocationEvent: PolicyRevocationEvent = {
    id: eventId,
    policyKey: policyKey,
    policyId: policyId,
    version: version,
    timestamp: timestamp,
    blockNumber: blockNumber,
    transactionHash: txHash,
  };
  context.PolicyRevocationEvent.set(revocationEvent);

  context.log.warn(
    `[AgentFence] REVOKED policy '${policyId}' v${version} on Monad! Tx: ${txHash}`
  );
});
