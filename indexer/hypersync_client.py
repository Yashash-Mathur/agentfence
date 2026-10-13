"""
AgentFence — Envio HyperSync / Monad Event Data Pipeline
--------------------------------------------------------
Streams and indexes AgentFencePolicy smart contract events from Monad Testnet
(Chain ID 10143) into structured audit records.

Supports chunked log batching to comply with Monad RPC limits and
Envio HyperSync stream formats.
"""

import asyncio
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

# Ensure stdout handles UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

MONAD_RPC_URL = os.getenv("MONAD_RPC_URL", "https://testnet-rpc.monad.xyz")
CONTRACT_ADDRESS = os.getenv(
    "AGENTFENCE_CONTRACT_ADDRESS",
    "0x1D3Db94C310B5ecA586bBac035C8030c9cad6068",
)
START_BLOCK = int(os.getenv("INDEXER_START_BLOCK", "70481750"))
BATCH_SIZE = int(os.getenv("INDEXER_BATCH_SIZE", "100"))

ABI_PATH = Path(__file__).parent / "abis" / "AgentFencePolicy.json"


def load_abi() -> list:
    with open(ABI_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def get_logs_chunked(contract, event_name: str, start: int, end: int, batch_size: int = BATCH_SIZE):
    all_logs = []
    event_obj = getattr(contract.events, event_name)
    current_start = start

    while current_start <= end:
        current_end = min(current_start + batch_size - 1, end)
        try:
            logs = await event_obj.get_logs(from_block=current_start, to_block=current_end)
            if logs:
                all_logs.extend(logs)
        except Exception as e:
            # If batch still too large, step down
            if batch_size > 50:
                return await get_logs_chunked(contract, event_name, start, end, batch_size=50)
            print(f"    [!] Error at blocks {current_start}-{current_end}: {e}")
        current_start = current_end + 1

    return all_logs


async def run_pipeline(scan_recent_only: bool = False) -> List[Dict[str, Any]]:
    print("=" * 70)
    print("[AgentFence] Envio / HyperSync Event Data Pipeline")
    print(f"Network:  Monad Testnet (Chain ID 10143)")
    print(f"Contract: {CONTRACT_ADDRESS}")
    print(f"RPC URL:  {MONAD_RPC_URL}")
    print("=" * 70)

    w3 = AsyncWeb3(AsyncHTTPProvider(MONAD_RPC_URL, request_kwargs={"timeout": 15}))
    if not await w3.is_connected():
        print("[!] Could not connect to Monad RPC.")
        return []

    latest_block = await w3.eth.block_number
    print(f"Current Monad Block: {latest_block}")

    scan_end = latest_block if scan_recent_only else int(os.getenv("INDEXER_END_BLOCK", "70481900"))
    print(f"Indexing events from block {START_BLOCK} to {scan_end}...")

    abi = load_abi()
    contract = w3.eth.contract(
        address=AsyncWeb3.to_checksum_address(CONTRACT_ADDRESS),
        abi=abi,
    )

    events_collected: List[Dict[str, Any]] = []

    try:
        # Query PolicyAnchored events
        anchored_logs = await get_logs_chunked(contract, "PolicyAnchored", START_BLOCK, scan_end)
        print(f"[+] Found {len(anchored_logs)} PolicyAnchored event(s)")

        for log in anchored_logs:
            args = log.args
            event_data = {
                "event_type": "PolicyAnchored",
                "policy_id": args.get("policyId"),
                "version": args.get("version"),
                "commitment_hash": args.get("commitmentHash").hex() if hasattr(args.get("commitmentHash"), "hex") else str(args.get("commitmentHash")),
                "policy_key": args.get("policyKey").hex() if hasattr(args.get("policyKey"), "hex") else str(args.get("policyKey")),
                "timestamp": args.get("timestamp"),
                "block_number": log.blockNumber,
                "tx_hash": log.transactionHash.hex(),
            }
            events_collected.append(event_data)
            print(f"   [Anchor] Policy:  '{event_data['policy_id']}' (v{event_data['version']})")
            print(f"            Hash:    {event_data['commitment_hash']}")
            print(f"            Tx:      https://testnet.monadexplorer.com/tx/{event_data['tx_hash']}")
            print(f"            Block:   {event_data['block_number']}")

        # Query PolicyRevoked events
        revoked_logs = await get_logs_chunked(contract, "PolicyRevoked", START_BLOCK, scan_end)
        print(f"[+] Found {len(revoked_logs)} PolicyRevoked event(s)")

        for log in revoked_logs:
            args = log.args
            event_data = {
                "event_type": "PolicyRevoked",
                "policy_id": args.get("policyId"),
                "version": args.get("version"),
                "policy_key": args.get("policyKey").hex() if hasattr(args.get("policyKey"), "hex") else str(args.get("policyKey")),
                "timestamp": args.get("timestamp"),
                "block_number": log.blockNumber,
                "tx_hash": log.transactionHash.hex(),
            }
            events_collected.append(event_data)
            print(f"   [Revoked] Policy: '{event_data['policy_id']}' (v{event_data['version']})")
            print(f"             Tx:     https://testnet.monadexplorer.com/tx/{event_data['tx_hash']}")

    except Exception as exc:
        print(f"[!] Event query exception: {exc}")

    print("=" * 70)
    print(f"Pipeline complete: {len(events_collected)} on-chain event(s) indexed.")
    print("=" * 70)
    return events_collected


if __name__ == "__main__":
    asyncio.run(run_pipeline())
