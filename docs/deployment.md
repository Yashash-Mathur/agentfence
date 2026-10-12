# Deploying AgentFencePolicy Smart Contract to Monad

This document outlines the deployment and live verification details for `AgentFencePolicy.sol` on the official **Monad Testnet**.

---

## 1. Official Monad Network Details

| Parameter | Value |
| :--- | :--- |
| **Network Name** | Monad Testnet |
| **Chain ID** | `10143` |
| **RPC Endpoint** | `https://testnet-rpc.monad.xyz` |
| **Block Explorer** | `https://testnet.monadexplorer.com` |
| **Faucet** | `https://faucet.monad.xyz` |
| **Currency Symbol** | `MON` |

---

## 2. Live Deployed Contract & Verification Details

The `AgentFencePolicy.sol` contract was compiled with `solc 0.8.37` and deployed directly to Monad Testnet:

- **Contract Address**: [`0x1D3Db94C310B5ecA586bBac035C8030c9cad6068`](https://testnet.monadexplorer.com/address/0x1D3Db94C310B5ecA586bBac035C8030c9cad6068)
- **Deployment Transaction Hash**: [`0x7a9ae4dda65ec7837ca36b144d7e9fc94cd14b3d68dca492cce31a1901244c66`](https://testnet.monadexplorer.com/tx/0x7a9ae4dda65ec7837ca36b144d7e9fc94cd14b3d68dca492cce31a1901244c66)
- **Deployment Block**: `70481784`
- **Initial Policy Anchor Tx**: [`0x81cc7f547be3860c42f47242197a328e4e95a6fc49129e63ef7d7c58dbe736fb`](https://testnet.monadexplorer.com/tx/0x81cc7f547be3860c42f47242197a328e4e95a6fc49129e63ef7d7c58dbe736fb)
- **Anchored Policy ID**: `demo-finance-agent` (Version 1)
- **Canonical Commitment Hash**: `0xe177af3b841f38aa44f05a9745570619d5e2139dcee9a646a07a620366b873af`
- **Anchor Block**: `70481801`

---

## 3. How to Deploy Your Own Instance

1. Ensure Python dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```
2. Obtain testnet `MON` from the faucet: [https://faucet.monad.xyz](https://faucet.monad.xyz).
3. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
4. Set your funded private key in `.env`:
   ```env
   MONAD_PRIVATE_KEY=0x<YOUR_PRIVATE_KEY>
   ```
5. Run the deployment & anchor script:
   ```bash
   python chain/deploy_and_anchor.py
   ```
