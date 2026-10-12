import asyncio
import os
import re
from dotenv import load_dotenv
from chain.client.monad_client import MonadClient
from gateway.policy.schema import ArgumentRule, QuotaConfig, SecurityPolicy, ToolPolicy
from verifier.verifier import compute_canonical_policy_commitment

load_dotenv()


async def deploy_and_anchor():
    pk = os.getenv("MONAD_PRIVATE_KEY")
    if not pk:
        raise ValueError("MONAD_PRIVATE_KEY is missing from .env")
    if not pk.startswith("0x"):
        pk = "0x" + pk

    print("[1/4] Connecting to Monad Testnet...")
    client = MonadClient(private_key=pk)
    conn_info = await client.verify_connection()
    print(f"      Connected: {conn_info['is_connected']} | Chain ID: {conn_info['chain_id']} | Latest Block: {conn_info['latest_block']}")

    print("\n[2/4] Deploying AgentFencePolicy.sol to Monad...")
    deploy_receipt = await client.deploy_contract()
    contract_address = deploy_receipt["contract_address"]
    tx_hash = deploy_receipt["tx_hash"]
    block_num = deploy_receipt["block_number"]
    print(f"      Contract Deployed: {contract_address}")
    print(f"      Tx Hash: {tx_hash}")
    print(f"      Block Number: {block_num}")

    print("\n[3/4] Creating Canonical Demo Policy & Anchoring State...")
    demo_policy = SecurityPolicy(
        policy_id="demo-finance-agent",
        version=1,
        description="Production Autonomous Finance Agent Boundary",
        quota=QuotaConfig(max_requests_per_window=100, window_seconds=3600),
        allowed_tools=(
            ToolPolicy(
                tool_name="read_safe_document",
                allowed=True,
                argument_rules=(
                    ArgumentRule(name="path", data_type="string", required=True),
                ),
            ),
            ToolPolicy(
                tool_name="execute_transfer",
                allowed=True,
                requires_approval=True,
                argument_rules=(
                    ArgumentRule(name="recipient", data_type="string", required=True),
                    ArgumentRule(name="amount_mon", data_type="float", required=True),
                ),
            ),
        ),
    )

    commitment_hash = compute_canonical_policy_commitment(demo_policy)
    print(f"      Canonical Commitment Hash: {commitment_hash}")

    anchor_receipt = await client.anchor_policy(
        policy_id=demo_policy.policy_id,
        version=demo_policy.version,
        commitment_hash=commitment_hash,
    )
    print(f"      Policy Anchored Successfully!")
    print(f"      Anchor Tx Hash: {anchor_receipt['tx_hash']}")
    print(f"      Block Number: {anchor_receipt['block_number']}")

    print("\n[4/4] Verifying On-Chain State from Monad...")
    verification = await client.verify_on_chain_commitment(
        policy_id=demo_policy.policy_id,
        expected_hash=commitment_hash,
    )
    print(f"      Verification Result:")
    print(f"      - Is Valid: {verification['is_valid']}")
    print(f"      - Is Revoked: {verification['is_revoked']}")
    print(f"      - Active Version: {verification['active_version']}")

    # Update .env file with deployed contract address safely
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "AGENTFENCE_CONTRACT_ADDRESS=" in content:
            content = re.sub(
                r"AGENTFENCE_CONTRACT_ADDRESS=.*",
                f"AGENTFENCE_CONTRACT_ADDRESS={contract_address}",
                content,
            )
        else:
            content += f"\nAGENTFENCE_CONTRACT_ADDRESS={contract_address}\n"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n[OK] Updated .env with AGENTFENCE_CONTRACT_ADDRESS={contract_address}")

    return {
        "contract_address": contract_address,
        "deploy_tx": tx_hash,
        "anchor_tx": anchor_receipt["tx_hash"],
        "commitment_hash": commitment_hash,
    }

if __name__ == "__main__":
    asyncio.run(deploy_and_anchor())
