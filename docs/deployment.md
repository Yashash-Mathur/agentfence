# Deploying AgentFencePolicy Smart Contract to Monad

This document outlines the deployment and verification procedure for `AgentFencePolicy.sol` on the official **Monad Testnet**.

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

## 2. Prerequisites

1. Ensure Python dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```
2. Obtain testnet `MON` from the official faucet: [https://faucet.monad.xyz](https://faucet.monad.xyz).
3. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
4. Add your funded Monad testnet private key to `.env`:
   ```env
   MONAD_PRIVATE_KEY=0x<YOUR_PRIVATE_KEY>
   ```

---

## 3. Automated Deployment via MonadClient

Deploy `AgentFencePolicy.sol` using the Python Monad client:

```python
import asyncio
import os
from dotenv import load_dotenv
from chain.client.monad_client import MonadClient

load_dotenv()

async def main():
    pk = os.getenv("MONAD_PRIVATE_KEY")
    client = MonadClient(private_key=pk)
    
    # 1. Confirm RPC connectivity
    conn_info = await client.verify_connection()
    print("Connected to Monad:", conn_info)

    # 2. Deploy smart contract
    receipt = await client.deploy_contract()
    print("Contract deployed successfully!")
    print(f"Contract Address: {receipt['contract_address']}")
    print(f"Transaction Hash: {receipt['tx_hash']}")

asyncio.run(main())
```

Once deployed, copy the resulting contract address into your `.env` file under `AGENTFENCE_CONTRACT_ADDRESS`.
