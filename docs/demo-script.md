# AgentFence: Official 3-Minute Demo Video Script & Walkthrough

This script is designed for recording the mandatory 3-minute hackathon video for the **Monad Metropolis Hackathon** (*Track: Trust, Identity & AI Infrastructure*).

---

## Video Outline & Timing (Total: 3:00)

| Timestamp | Phase | Screen Focus | Speaker Narrative |
| :--- | :--- | :--- | :--- |
| **0:00 - 0:35** | **The Problem & Core Philosophy** | Architecture diagram or slides | "Autonomous AI agents can hallucinate or suffer prompt injection. Traditional observability only watches them after they act. AgentFence is a deterministic security gateway and accountability layer anchored on Monad. Our rule: Don't merely observe what an AI agent does; restrict what it is permitted to execute through a protected boundary." |
| **0:35 - 1:15** | **Live Gateway Dashboard & Monad Anchor** | Browser at `http://127.0.0.1:8000` | "Here is the live AgentFence Dashboard. You can see our active policy `demo-finance-agent` with its canonical Keccak-256 commitment hash. Above, we are integrated live with Monad Testnet at contract `0x1D3Db...` — showing the deployment and policy anchor transactions directly on Monad Explorer." |
| **1:15 - 2:05** | **Running the Demo Agent Scenario** | Click **"▶ Run Demo Agent"** | "Let's click 'Run Demo Agent'. In real time, the agent attempts five actions: <br>1. **Allowed**: Reading a safe document succeeds within latency limits.<br>2. **Allowed**: Sending a team alert succeeds.<br>3. **Blocked (Default-Deny)**: A prompt injection attempts to wipe the database (`drop_production_database`). Denied before execution!<br>4. **Blocked**: Arbitrary shell execution (`exec_arbitrary_shell`) is blocked.<br>5. **Approval Gate**: Requesting a 2.5 MON treasury transfer is intercepted as `PENDING_APPROVAL` for human review." |
| **2:05 - 2:35** | **Independent Verification & Concurrency** | Show Terminal & Monad Explorer | "Notice the live audit log updating in SQLite WAL mode with atomic quota accounting. Now let's run our independent verifier script: it computes the RFC-8785 canonical hash and matches it against Monad's on-chain state. Tampering with even 1 byte of the policy immediately fails verification." |
| **2:35 - 3:00** | **Conclusion & Hackathon Criteria** | GitHub Repo & Test Suite | "All 18 automated tests pass across unit, concurrency, security bypasses, and blockchain clients. The code is 100% open-source on GitHub under the MIT license, with full testnet contract transactions verified on Monad. Thank you!" |

---

## Commands for Demo Preparation

1. **Launch the Gateway:**
   ```bash
   python -m uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --reload
   ```
2. **Open the Dashboard:**
   Visit [http://127.0.0.1:8000](http://127.0.0.1:8000).
3. **Run the Test Suite (Terminal):**
   ```bash
   python -m pytest tests/ -v
   ```
4. **Monad Explorer Link:**
   [https://testnet.monadexplorer.com/address/0x1D3Db94C310B5ecA586bBac035C8030c9cad6068](https://testnet.monadexplorer.com/address/0x1D3Db94C310B5ecA586bBac035C8030c9cad6068)
