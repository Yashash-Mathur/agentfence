import asyncio
import pytest
from chain.client.monad_client import MonadClient, load_contract_artifacts


def test_contract_artifacts_load_successfully():
    abi, bytecode = load_contract_artifacts()
    assert isinstance(abi, list)
    assert len(abi) > 0
    assert bytecode.startswith("6080") or len(bytecode) > 100
    # Confirm key functions exist in ABI
    names = [elem.get("name") for elem in abi if elem.get("type") == "function"]
    assert "anchorPolicy" in names
    assert "revokePolicy" in names
    assert "verifyCommitment" in names


@pytest.mark.asyncio
async def test_monad_client_initialization():
    client = MonadClient(rpc_url="https://testnet-rpc.monad.xyz", chain_id=10143)
    assert client.expected_chain_id == 10143
    assert client.rpc_url == "https://testnet-rpc.monad.xyz"
