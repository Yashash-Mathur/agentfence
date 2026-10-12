import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from eth_account import Account
from web3 import AsyncWeb3
from web3.exceptions import ContractLogicError, TransactionNotFound
from web3.providers import AsyncHTTPProvider

# Official Monad Testnet Defaults
DEFAULT_MONAD_RPC = os.getenv("MONAD_RPC_URL", "https://testnet-rpc.monad.xyz")
DEFAULT_MONAD_CHAIN_ID = int(os.getenv("MONAD_CHAIN_ID", "10143"))

ABI_PATH = Path(__file__).parent.parent / "contracts" / "build" / "chain_contracts_AgentFencePolicy_sol_AgentFencePolicy.abi"
BIN_PATH = Path(__file__).parent.parent / "contracts" / "build" / "chain_contracts_AgentFencePolicy_sol_AgentFencePolicy.bin"


def load_contract_artifacts() -> Tuple[list, str]:
    if not ABI_PATH.exists() or not BIN_PATH.exists():
        raise FileNotFoundError("Contract artifacts not found. Please compile AgentFencePolicy.sol first.")
    with open(ABI_PATH, "r", encoding="utf-8") as f:
        abi = json.load(f)
    with open(BIN_PATH, "r", encoding="utf-8") as f:
        bytecode = f.read().strip()
    return abi, bytecode


class MonadClient:
    """
    Asynchronous Monad Blockchain Client.
    Connects to the official Monad EVM testnet for policy state anchoring and verification.
    """

    def __init__(
        self,
        rpc_url: str = DEFAULT_MONAD_RPC,
        chain_id: int = DEFAULT_MONAD_CHAIN_ID,
        private_key: Optional[str] = None,
        contract_address: Optional[str] = None,
    ):
        self.rpc_url = rpc_url
        self.expected_chain_id = chain_id
        self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url, request_kwargs={"timeout": 10}))
        self.private_key = private_key
        self.account = Account.from_key(private_key) if private_key else None
        self.contract_address = contract_address
        self.abi, self.bytecode = load_contract_artifacts()
        self.contract = None

        if self.contract_address:
            self.contract = self.w3.eth.contract(
                address=AsyncWeb3.to_checksum_address(self.contract_address),
                abi=self.abi,
            )

    async def verify_connection(self) -> Dict[str, Any]:
        """Checks RPC connectivity and confirms Monad network identity."""
        actual_chain_id = await self.w3.eth.chain_id
        block_number = await self.w3.eth.block_number
        is_connected = await self.w3.is_connected()

        return {
            "is_connected": is_connected,
            "chain_id": actual_chain_id,
            "chain_id_matches": actual_chain_id == self.expected_chain_id,
            "latest_block": block_number,
            "rpc_url": self.rpc_url,
        }

    async def deploy_contract(self) -> Dict[str, Any]:
        """Deploys AgentFencePolicy.sol to the configured Monad network."""
        if not self.account:
            raise ValueError("Private key required to deploy smart contract.")

        deployer_addr = self.account.address
        nonce = await self.w3.eth.get_transaction_count(deployer_addr)
        gas_price = await self.w3.eth.gas_price

        factory = self.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        construct_tx = await factory.constructor().build_transaction({
            "from": deployer_addr,
            "nonce": nonce,
            "gasPrice": gas_price,
            "chainId": self.expected_chain_id,
        })

        # Estimate gas
        gas_est = await self.w3.eth.estimate_gas(construct_tx)
        construct_tx["gas"] = int(gas_est * 1.2)

        signed_tx = self.account.sign_transaction(construct_tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        self.contract_address = receipt.contractAddress
        self.contract = self.w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(self.contract_address),
            abi=self.abi,
        )

        return {
            "contract_address": receipt.contractAddress,
            "tx_hash": tx_hash.hex(),
            "block_number": receipt.blockNumber,
            "status": receipt.status,
        }

    async def anchor_policy(
        self,
        policy_id: str,
        version: int,
        commitment_hash: str,
    ) -> Dict[str, Any]:
        """Submits a transaction to anchor a policy version and commitment hash on-chain."""
        if not self.account or not self.contract:
            raise ValueError("Account and deployed contract required to anchor policy.")

        # Ensure commitment_hash is bytes32
        hash_bytes = bytes.fromhex(commitment_hash.removeprefix("0x"))

        nonce = await self.w3.eth.get_transaction_count(self.account.address)
        gas_price = await self.w3.eth.gas_price

        tx = await self.contract.functions.anchorPolicy(
            policy_id,
            version,
            hash_bytes,
        ).build_transaction({
            "from": self.account.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "chainId": self.expected_chain_id,
        })

        gas_est = await self.w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas_est * 1.2)

        signed_tx = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return {
            "tx_hash": tx_hash.hex(),
            "block_number": receipt.blockNumber,
            "status": receipt.status,
            "policy_id": policy_id,
            "version": version,
            "commitment_hash": commitment_hash,
        }

    async def verify_on_chain_commitment(
        self,
        policy_id: str,
        expected_hash: str,
    ) -> Dict[str, Any]:
        """Reads Monad contract state to verify whether an expected hash is currently valid."""
        if not self.contract:
            raise ValueError("Contract instance not initialized.")

        hash_bytes = bytes.fromhex(expected_hash.removeprefix("0x"))
        is_valid, is_revoked, active_version = await self.contract.functions.verifyCommitment(
            policy_id, hash_bytes
        ).call()

        return {
            "policy_id": policy_id,
            "expected_hash": expected_hash,
            "is_valid": is_valid,
            "is_revoked": is_revoked,
            "active_version": active_version,
        }
