# AgentFence — Envio Indexer & Data Pipeline

This directory contains the **Envio HyperIndex** indexer and **HyperSync** data pipeline for the **AgentFence** smart contract on the **Monad Testnet**.

---

## 🎯 Purpose

When AI security policies are anchored or revoked on Monad, off-chain gateways and verifiers need low-latency, queryable access to policy records without polling full nodes directly.

The Envio indexer provides:
- **Instant GraphQL API**: Query active policies and commitment hashes by `policyId`.
- **Historical Audit Trail**: Track every `PolicyAnchored` and `PolicyRevoked` event with block numbers and transaction hashes.
- **Fast Resync**: Leverages Envio HyperSync for ultra-high-speed indexing on EVM-compatible chains like Monad.

---

## 📁 Repository Structure

```
indexer/
├── config.yaml            # Envio HyperIndex configuration (networks, contract, events)
├── schema.graphql         # GraphQL entity schema (Policy, PolicyAnchorEvent, PolicyRevocationEvent)
├── abis/
│   └── AgentFencePolicy.json  # AgentFence contract ABI
├── src/
│   └── EventHandlers.ts   # TypeScript event handlers processing Monad events
├── hypersync_client.py    # Python HyperSync / RPC streaming client pipeline
├── package.json           # Envio dependencies and scripts
├── tsconfig.json          # TypeScript build configuration
└── README.md              # Documentation and execution guide
```

---

## ⚙️ Configuration Details

- **Target Chain**: Monad Testnet (`Chain ID: 10143`)
- **Contract Address**: `0x1D3Db94C310B5ecA586bBac035C8030c9cad6068`
- **Start Block**: `70481700` (contract deployment at block `70481784`)
- **Tracked Events**:
  - `PolicyAnchored(bytes32 indexed policyKey, string policyId, uint64 indexed version, bytes32 commitmentHash, uint64 timestamp)`
  - `PolicyRevoked(bytes32 indexed policyKey, string policyId, uint64 indexed version, uint64 timestamp)`

---

## 🚀 Option 1: Running the Python HyperSync Data Pipeline

For immediate local verification and data ingestion without Docker:

```bash
python indexer/hypersync_client.py
```

**Output:**
```text
======================================================================
[AgentFence] Envio / HyperSync Event Data Pipeline
Network:  Monad Testnet (Chain ID 10143)
Contract: 0x1D3Db94C310B5ecA586bBac035C8030c9cad6068
RPC URL:  https://testnet-rpc.monad.xyz
======================================================================
Current Monad Block: 70761313
Indexing events from block 70481700 to 70482500...
[+] Found 1 PolicyAnchored event(s)
   [Anchor] Policy:  'demo-finance-agent' (v1)
            Hash:    0xe177af3b841f38aa44f05a9745570619d5e2139dcee9a646a07a620366b873af
            Tx:      https://testnet.monadexplorer.com/tx/0x81cc7f547be3860c42f47242197a328e4e95a6fc49129e63ef7d7c58dbe736fb
            Block:   70481801
[+] Found 0 PolicyRevoked event(s)
======================================================================
Pipeline complete: 1 on-chain event(s) indexed.
======================================================================
```

---

## ⚡ Option 2: Running with Envio CLI (Local Dev & Docker)

### Prerequisites
- Node.js >= 18
- Docker & Docker Compose
- pnpm or npm

### Steps
1. Install Envio globally:
   ```bash
   npm i -g envio
   ```
2. Navigate to the indexer directory:
   ```bash
   cd indexer
   ```
3. Generate indexer code:
   ```bash
   envio codegen
   ```
4. Start local development indexer:
   ```bash
   envio dev
   ```
5. Open GraphQL playground at `http://localhost:8080/v1/graphql`.

### Example GraphQL Queries

#### Get Active Policy by ID
```graphql
query GetActivePolicy {
  Policy(where: { policyId: { _eq: "demo-finance-agent" } }) {
    policyId
    activeVersion
    commitmentHash
    isRevoked
    anchoredAt
    lastUpdatedTx
  }
}
```

#### Get Policy History
```graphql
query GetPolicyHistory {
  PolicyAnchorEvent(order_by: { blockNumber: desc }) {
    policyId
    version
    commitmentHash
    blockNumber
    transactionHash
  }
}
```

---

## ☁️ Option 3: Deploying to Envio Cloud

1. Log in to the [Envio Hosted Service](https://envio.dev).
2. Connect your GitHub repository (`https://github.com/Yashash-Mathur/agentfence`).
3. Set the root directory to `indexer/`.
4. Deploy — Envio Cloud automatically compiles `config.yaml`, `schema.graphql`, and `EventHandlers.ts` to host your high-performance GraphQL endpoint.
