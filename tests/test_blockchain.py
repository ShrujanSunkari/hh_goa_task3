import os
import pytest
from web3 import Web3
from eth_tester import EthereumTester, PyEVMBackend
from web3.middleware import ExtraDataToPOAMiddleware

# Helper to compile contract
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from deploy import bootstrap_solc, compile_contract


@pytest.fixture(scope="module")
def setup():
    # Setup in-memory Web3
    tester = EthereumTester(PyEVMBackend())
    w3 = Web3(Web3.EthereumTesterProvider(tester))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    # Compile
    bootstrap_solc()
    abi, bytecode = compile_contract()

    # Deploy
    deployer = w3.eth.accounts[0]
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = Contract.constructor().transact({"from": deployer, "gas": 3_000_000})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    contract = w3.eth.contract(address=receipt["contractAddress"], abi=abi)
    return w3, contract, deployer


def test_registrar_role(setup):
    w3, contract, deployer = setup
    REGISTRAR_ROLE = contract.functions.REGISTRAR_ROLE().call()
    assert contract.functions.hasRole(REGISTRAR_ROLE, deployer).call() is True


def test_non_registrar_cannot_register(setup):
    w3, contract, deployer = setup
    _, _, other_account = setup[0], setup[1], setup[0].eth.accounts[1]

    # other_account doesn't have REGISTRAR_ROLE
    data_hash = b"\x01" * 32
    with pytest.raises(Exception) as excinfo:
        contract.functions.registerRecord(
            data_hash, True, "https://test.com", 5000, b"\x00" * 32, "ipfs://test"
        ).transact({"from": other_account})

    assert "AccessControl" in str(excinfo.value) or "revert" in str(excinfo.value)


def test_grant_registrar_role(setup):
    w3, contract, deployer = setup
    other_account = w3.eth.accounts[2]

    REGISTRAR_ROLE = contract.functions.REGISTRAR_ROLE().call()

    # deployer is admin, grants role
    contract.functions.grantRegistrarRole(other_account).transact({"from": deployer})
    assert contract.functions.hasRole(REGISTRAR_ROLE, other_account).call() is True

    # other_account can now register
    data_hash = b"\x02" * 32
    tx = contract.functions.registerRecord(
        data_hash, True, "https://test.com", 5000, b"\x00" * 32, "ipfs://test"
    ).transact({"from": other_account})

    receipt = w3.eth.wait_for_transaction_receipt(tx)
    assert receipt["status"] == 1


def test_metadata_uri_stored(setup):
    w3, contract, deployer = setup

    data_hash = b"\x03" * 32
    contract.functions.registerRecord(
        data_hash, True, "https://linkedin.com", 9900, b"\x00" * 32, "ipfs://metadata"
    ).transact({"from": deployer})

    (
        exists,
        is_demo_mode,
        source_url,
        confidence_bps,
        payload_commitment,
        timestamp,
        metadata_uri,
    ) = contract.functions.verifyRecord(data_hash).call()

    assert exists is True
    assert source_url == "https://linkedin.com"
    assert metadata_uri == "ipfs://metadata"
