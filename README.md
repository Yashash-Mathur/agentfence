# 🛡️ AgentFence

> **Deterministic Security & Accountability Gateway for AI Agents — Anchored on Monad**
>
> Built for the **Monad Metropolis Hackathon** (Track: *Trust, Identity & AI Infrastructure*).

---

## 1. What is AgentFence?

AgentFence is a lightweight, deterministic security and accountability layer for autonomous AI agents.

The core principle:
**Do not merely observe what an AI agent does. Restrict what it is permitted to execute through a protected boundary.**

### Key Capabilities
- **Default-Deny Policy Enforcement**: Tools not explicitly registered in the active policy allowlist are blocked before execution.
- **Strict Parameter Constraints**: Pure-function validation using Pydantic v2 frozen models (type bounds, regex patterns, allowed values).
- **Atomic Concurrency Quotas**: High-throughput request quotas utilizing SQLite WAL-mode `BEGIN IMMEDIATE` transactions to prevent race-condition over-allocation.
- **Human-in-the-Loop Interception**: Designated sensitive actions (e.g., financial transfers, privilege escalation) are intercepted as `PENDING_APPROVAL`.
- **Cryptographic State Anchoring on Monad**: Canonical policy commitments (`keccak256`) and version histories are anchored to `AgentFencePolicy.sol` on the Monad EVM testnet.
- **Independent Evidence Verifier**: Anyone can verify whether an off-chain policy or audit log matches the unrevoked commitment on-chain.

---

## 2. Architecture

```
+-------------------+      +-----------------------------------------+
|  AI Agent Loop    | ---> |         AgentFence Gateway              |
|  (Python SDK)     | HTTP |  - Policy Engine (Pydantic v2 Frozen)   |
+-------------------+      |  - Atomic Quota Manager (SQLite WAL)    |
                           |  - Controlled Tool Executor             |
                           +--------------------+--------------------+
                                                |
                                                v
                               +---------------------------------+
                               |    Monad Testnet Blockchain     |
                               |      AgentFencePolicy.sol       |
                               | (Chain ID 10143, EVM Anchoring) |
                               +---------------------------------+
```

---

## 3. Quick Start & Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ (for compiling Solidity via npx)

### 1. Installation
Clone the repository and install dependencies:
```bash
git clone <YOUR_REPO_URL>
cd agentfence
pip install -r requirements.txt
```

### 2. Configure Environment
Copy the sample environment file:
```bash
cp .env.example .env
```

### 3. Run Gateway
Start the AgentFence gateway on port 8000:
```bash
python -m uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --reload
```
Access the interactive dashboard at [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## 4. Running the Tests

The test suite validates policy enforcement, atomic concurrency, security bypasses, and blockchain clients:
```bash
python -m pytest tests/ -v
```
All 17 tests run in under 3 seconds:
- `tests/unit/test_policy_engine.py`: 8 tests (allow, deny, regex, types, revocation, etc.)
- `tests/unit/test_verifier.py`: 3 tests (canonical hashing, verification, tamper rejection)
- `tests/unit/test_monad_client.py`: 2 tests (ABI loading, Web3 client initialization)
- `tests/concurrency/test_quota_concurrent.py`: 1 test (20 simultaneous burst reservations, 0 over-allocation)
- `tests/security/test_bypass_attempts.py`: 1 test (path traversal, parameter smuggling, type confusion)
- `tests/integration/test_gateway_flow.py`: 1 test (end-to-end API lifecycle)
- `tests/integration/test_demo_agent.py`: 1 test (autonomous demo agent execution)

---

## 5. Monad Testnet Integration

- **Network**: Monad Testnet
- **Chain ID**: `10143`
- **RPC URL**: `https://testnet-rpc.monad.xyz`
- **Contract**: `chain/contracts/AgentFencePolicy.sol`

Detailed instructions are documented in [`docs/deployment.md`](docs/deployment.md).

---

## 6. Honest Limitations & Threat Model

Please read our honest disclosures in [`docs/limitations.md`](docs/limitations.md) and [`docs/threat-model.md`](docs/threat-model.md).
- AgentFence protects actions routed through its gateway. It is not an OS-level kernel sandbox.
- Committing a policy hash on Monad proves the exact policy in effect; it does not guarantee truthfulness of external web requests.

---

## 7. AI Disclosure & Originality

This project was built during the Monad Metropolis Hackathon. AI pair programming assistance was used for rapid boilerplate generation, documentation drafting, and test-case structuring under strict human design, review, and verification.

---

## 8. License

MIT License. See [LICENSE](LICENSE) for details.
