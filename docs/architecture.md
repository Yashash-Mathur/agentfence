# AgentFence Architecture & Verification Model

## 1. Modular Architecture Overview

AgentFence consists of 8 core subsystems designed for high resilience, deterministic evaluation, and verifiable anchoring:

```
+-----------------------------------------------------------------------+
|                              Client SDK                               |
|       - Python SDK: Structured requests, typed responses, clean errors |
+-----------------------------------^-----------------------------------+
                                    | HTTP / JSON (X-Request-ID, Latency)
+-----------------------------------v-----------------------------------+
|                        FastAPI Resilient Gateway                      |
|  - Middleware (Diagnostics, Tracing, Rate Limiting)                   |
|  - Policy Engine (Pydantic v2 Frozen Enforcer, Pure Function)         |
|  - Atomic Quota & Concurrency Manager (SQLite WAL, BEGIN IMMEDIATE)   |
|  - Controlled Tool Executor (Safe sandboxed demonstration tools)      |
|  - Audit Logger & Event Persistence                                   |
+-------------------+-------------------------------+-------------------+
                    |                               |
                    v                               v
+-------------------------------+   +-----------------------------------+
|    Off-Chain SQLite Storage   |   |     Blockchain Integration Layer  |
|  - WAL mode, PRAGMA timeouts  |   |  - Web3.py Async Engine           |
|  - STRICT schema tables       |   |  - Monad Smart Contract Client    |
|  - Audit trail & Reservations |   |  - Event verification & Reorg safe|
+-------------------------------+   +-----------------+-----------------+
                                                      | RPC (Chain ID 10143)
                                                      v
                                    +-----------------------------------+
                                    |      Monad Testnet Blockchain     |
                                    |  - AgentFencePolicy.sol           |
                                    |  - Immutable policy commitments   |
                                    |  - Versioning & Revocation State  |
+-----------------------------------+-----------------------------------+
|               Independent Evidence & Policy Verifier                  |
|  - Canonical JSON serialization (RFC 8785)                            |
|  - Keccak-256 / SHA-256 commitment comparison against Monad contract  |
+-----------------------------------------------------------------------+
```

---

## 2. Policy Pipeline & Evaluation Flow

1. **Request Ingestion**: Agent submits action `{ tool_name, arguments, request_id }`.
2. **Context Assembly**:
   - Gateway loads current active policy.
   - Evaluates active state & checks on-chain revocation flag if stale.
3. **Deterministic Verification (Pure Function)**:
   - Tool Allowlist Check: Is `tool_name` registered and permitted?
   - Parameter Schema Check: Do `arguments` adhere to constraints?
   - Quota Check: Does current reservation exceed quota limit?
   - Approval Gate: Does action require manual approval?
4. **Execution Decision**:
   - `DENIED`: Log violation with deterministic error code, return HTTP 403.
   - `PENDING_APPROVAL`: Return approval ticket, halt execution.
   - `ALLOWED`: Atomically increment quota, execute tool, persist audit receipt.
5. **Post-Execution Output**:
   - Structured JSON response containing `execution_id`, `status`, `result`, and `diagnostic_headers`.

---

## 3. Blockchain Anchoring & Verification Model

### Why Monad?
Monad's high-throughput, parallel EVM architecture enables real-time verification and frequent policy commitment updates without prohibitive latency or gas expenses.

### What is Anchored On-Chain?
- **Policy Version**: Monotonically increasing `uint64`.
- **Policy Commitment**: `bytes32` cryptographic hash of canonical policy definition.
- **Revocation Status**: Boolean flag set by policy owner.
- **Timestamp & Operator Address**: Emitted via indexed events.

### What Verification Proves vs What it Does NOT Prove
- **Proves**: The exact policy bytes in effect were committed by the authorized policy owner on Monad at a specific block, without subsequent tampering.
- **Does NOT Prove**: It does not prove that an unmonitored external network call made by an agent script was honest. It guarantees integrity within the protected gateway boundary.
