# AgentFence Limitations & Threat Model Disclosures

## 1. What AgentFence Enforces
- **Default-Deny Policy Execution**: Protects all sensitive tools registered behind the gateway boundary. Unregistered or unauthorized tools are blocked deterministically.
- **Strict Parameter Constraints**: Input parameters undergo rigorous Pydantic v2 type checking, regex enforcement, and length validation.
- **Atomic Quota Accounting**: Uses SQLite WAL-mode `BEGIN IMMEDIATE` transactions to prevent resource over-allocation during concurrent bursts.
- **Human-in-the-Loop Interception**: Designated sensitive actions (e.g. fund transfers, permission elevation) are intercepted and marked as `PENDING_APPROVAL`.
- **Cryptographic State Anchoring on Monad**: Policies are canonicalized (RFC-8785) and hashed (Keccak-256). The resulting commitment is anchored to the Monad EVM blockchain (`AgentFencePolicy.sol`), making retroactive tampering independently detectable.

---

## 2. What AgentFence Does NOT Guarantee (Honest Limitations)
1. **OS-Level Process Isolation**: If an AI agent has direct terminal access to the host operating system, it can invoke unauthorized commands directly on the host. AgentFence protects the tool execution gateway, not arbitrary local host processes.
2. **LLM Hallucinations & Truthfulness**: AgentFence does not evaluate whether an LLM prompt is logically true. It deterministically bounds the actions the agent can perform.
3. **Out-of-Band Network Access**: If the host environment allows the agent arbitrary internet access without proxying through the gateway, unmonitored HTTP requests cannot be intercepted.
4. **Blockchain Guarantees vs. Off-Chain Truth**: Committing a policy hash to Monad proves the exact policy bytes in effect at that block; it does not prove that an external actor behaved honestly outside the gateway boundary.
5. **Multi-Host Concurrency**: The MVP utilizes local SQLite WAL mode. Running multiple distributed gateway instances requires migrating the persistence layer to a distributed ACID database (e.g., PostgreSQL).
