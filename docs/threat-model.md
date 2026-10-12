# AgentFence Threat Model & Security Boundary Specification

## 1. System Overview & Core Philosophy
**AgentFence** is a deterministic security gateway and accountability layer for AI agent execution.
Its primary objective: **Do not merely observe what an AI agent does; strictly restrict what it is permitted to execute through the protected boundary.**

The core philosophy separates probabilistic generation (LLM decision-making) from deterministic enforcement (policy verification, atomic quotas, state anchoring).

---

## 2. Trust Boundaries

```
[ Untrusted Zone ]          [ Semi-Trusted Zone ]       [ Protected Zone ]
+-------------------+      +---------------------+     +--------------------+
|                   |      |                     |     |                    |
|  AI Agent Loop    | ---> |  AgentFence Gateway | --> |  Protected Tools & |
|  (LLM Prompting,  | HTTP |  (Policy Engine,    |     |  Privileged        |
|   SDK Client)     |      |   Atomic Quotas,    |     |  Credentials       |
|                   |      |   Audit Logger)     |     |                    |
+-------------------+      +----------+----------+     +--------------------+
                                      |
                                      v
                           +---------------------+
                           |   Monad Testnet     |
                           | (State Anchoring &  |
                           |  Policy Commitment) |
                           +---------------------+
```

### Boundary 1: Untrusted Agent to Gateway (Network API)
- The AI Agent executes in an environment that may be susceptible to prompt injection, hallucination, or adversarial jailbreaks.
- The Agent **NEVER** receives direct credentials (API keys, database tokens, private signing keys) for protected tools.
- All interactions must go through structured, strictly validated HTTP requests.

### Boundary 2: Gateway to Protected Tools (Execution Boundary)
- Protected tools reside behind the gateway.
- Tools are invoked **ONLY** if:
  1. The target tool is registered and explicitly permitted by the active policy.
  2. Input arguments adhere strictly to declared schema constraints.
  3. The request quota has not been exceeded (evaluated via atomic transactional reservation).
  4. The action does not require unresolved human-in-the-loop approval.
  5. The active policy has not been revoked or superseded.

### Boundary 3: Gateway to Monad Blockchain (Accountability Boundary)
- Routine tool calls run at high speed off-chain.
- Policy versions, cryptographic commitments (SHA-256 / Keccak-256 hashes), and revocation states are anchored to Monad smart contracts.
- Independent verifiers can audit whether an executed action was authorized under a legitimate, unrevoked policy committed on-chain.

---

## 3. Threat Classification & In-Scope Defenses

| Threat ID | Threat Name | Description | AgentFence Mitigation |
| :--- | :--- | :--- | :--- |
| **TH-01** | Tool Hijacking / Unauthorized Invocation | Attacker induces LLM to call privileged tools (e.g. `delete_database`, `transfer_funds`). | **Default-Deny Policy Engine**: Tools not explicitly in the active allowlist are rejected immediately prior to execution. |
| **TH-02** | Parameter Tampering / Argument Injection | LLM attempts shell injection, path traversal, or out-of-bound arguments in permitted tools. | **Strict Pydantic Enforcer**: Runtime validation using frozen schemas, regex constraints, and explicit type boundaries (`extra="forbid"`). |
| **TH-03** | Quota Exhaustion / Resource Flooding | Agent loops infinitely or generates high-volume denial of service attacks. | **Atomic SQLite ACID Quota Reservations**: Uses `BEGIN IMMEDIATE` transactions and row-level checks to prevent race conditions. |
| **TH-04** | Action Replay / Outdated Policy Exploitation | Adversary attempts to use older, permissive policy versions that have been superseded. | **Strict Version & Monad Anchoring**: Each request evaluates against active, unrevoked policy version; revocation status verifiable against smart contract. |
| **TH-05** | Sensitive Action Bypass | Sensitive actions requiring human approval executed autonomously. | **Approval Intercept Flow**: Status marked as `PENDING_APPROVAL` with distinct authorization token required for execution. |
| **TH-06** | Audit Log Tampering / Historical Revisionism | Malicious operator or compromise attempts to alter off-chain policy definitions retroactively. | **Canonical Cryptographic Anchoring**: Policy hashes committed to Monad testnet; verifier flags discrepancies instantly. |

---

## 4. Explicitly Out-of-Scope (Non-Goals for MVP)

1. **OS / Kernel Sandboxing**: AgentFence does not stop an agent script from calling `os.system` locally if the agent runs on an unconstrained machine. AgentFence controls access to services and tools routed through the gateway.
2. **LLM Truthfulness / Hallucination Detection**: AgentFence does not grade whether an LLM's thought process is logically sound; it enforces deterministic operational boundaries.
3. **Arbitrary Subprocess / Outbound Network Egress**: If the host environment allows the agent arbitrary network access, AgentFence cannot stop calls that bypass the SDK/gateway.
4. **Zero-Knowledge Proofs & Custom Crypto**: Standard EVM commitments (Keccak256 / SHA256) are used; no speculative cryptographic systems are claimed.

---

## 5. Failure Modes & Graceful Degradation

- **RPC Downtime / Latency Spike**:
  - The gateway caches verified active policy state with timestamps.
  - If policy freshness verification fails and failsafe mode is enabled, the gateway denies sensitive tool execution rather than operating in an untrusted state (Fail-Closed).
- **Database Lock / Contention**:
  - SQLite WAL mode + `busy_timeout=10000` + transaction retries with jittered backoff.
  - Rejection with HTTP 503 if lock timeout is exceeded, ensuring atomic invariants remain intact.
- **Circuit Breakers**:
  - Outbound tool executions use explicit connection and read timeouts (default 5.0s), preventing hung connections from exhausting gateway worker threads.
