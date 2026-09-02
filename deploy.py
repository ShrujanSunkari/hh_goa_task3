"""
deploy.py
---------
Compile & deploy IdentityRegistry.sol, then persist the artifact.

Usage
-----
    python deploy.py [--rpc <uri>]    # defaults to in-process py-evm

Outputs
-------
  contracts/IdentityRegistry_artifacts.json
      {
        "abi":              [...],
        "bytecode":         "0x...",
        "deployed_address": "0x..."
      }

  .env  — CONTRACT_ADDRESS key is written/updated automatically.

Requirements (beyond requirements.txt)
---------------------------------------
    pip install py-solc-x
"""

from __future__ import annotations

import io
import sys

# Force UTF-8 on Windows CP-1252 terminals
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv, set_key
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
console = Console(highlight=False)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
SOL_FILE = ROOT / "contracts" / "IdentityRegistry.sol"
ARTIFACT_FILE = ROOT / "contracts" / "IdentityRegistry_artifacts.json"
ENV_FILE = ROOT / ".env"

SOLC_VERSION = "0.8.24"


# ─────────────────────────────────────────────────────────────────────────────
#  1. Compiler bootstrap
# ─────────────────────────────────────────────────────────────────────────────


def bootstrap_solc() -> None:
    """Auto-install py-solc-x + solc binary if not already present."""
    try:
        import solcx
    except ImportError:
        console.log("[yellow]py-solc-x not found — installing …[/]")
        import subprocess, sys

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "py-solc-x"]
        )
        import solcx  # noqa: F811 — re-import after install

    installed = solcx.get_installed_solc_versions()
    from packaging.version import Version  # bundled with pip

    target = Version(SOLC_VERSION)
    if not any(Version(str(v)) == target for v in installed):
        console.log(f"[cyan]Installing solc {SOLC_VERSION} …[/]")
        solcx.install_solc(SOLC_VERSION, show_progress=True)
    else:
        console.log(f"[green]solc {SOLC_VERSION} already installed[/] -- [OK]")

    solcx.set_solc_version(SOLC_VERSION)


# ─────────────────────────────────────────────────────────────────────────────
#  2. Compilation
# ─────────────────────────────────────────────────────────────────────────────


def compile_contract() -> tuple[list, str]:
    """
    Compile IdentityRegistry.sol.

    Returns
    -------
    (abi, bytecode)  where bytecode is a hex string without 0x prefix.
    """
    import solcx

    console.log(f"[cyan]Compiling[/] {SOL_FILE} ...")
    source = SOL_FILE.read_text(encoding="utf-8")

    compiled = solcx.compile_files(
        [SOL_FILE],
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        import_remappings=["@openzeppelin=node_modules/@openzeppelin"],
        optimize=True,
        optimize_runs=200
    )

    # The compiled dict key looks like "contracts/IdentityRegistry.sol:IdentityRegistry" or absolute path
    contract_key = next(k for k in compiled if "IdentityRegistry" in k)
    interface = compiled[contract_key]
    abi = interface["abi"]
    bytecode = interface["bin"]

    console.log(
        f"[green]Compiled [OK][/]  "
        f"ABI entries: [magenta]{len(abi)}[/]  "
        f"Bytecode size: [magenta]{len(bytecode)//2} bytes[/]"
    )
    return abi, bytecode


# ─────────────────────────────────────────────────────────────────────────────
#  3. Web3 provider
# ─────────────────────────────────────────────────────────────────────────────


def build_w3(network: str) -> object:
    """
    Return a connected Web3 instance.

    Priority
    --------
    1. --network sepolia -> WEB3_PROVIDER_URI env var
    2. --network local -> In-process py-evm (EthereumTesterProvider)
    """
    from web3 import Web3

    if network == "sepolia":
        uri = os.getenv("WEB3_PROVIDER_URI")
        if not uri:
            raise ValueError("WEB3_PROVIDER_URI is required for sepolia network")
    else:
        uri = "evm://"

    if uri.startswith("evm://"):
        try:
            from eth_tester import EthereumTester, PyEVMBackend
            from web3.middleware import ExtraDataToPOAMiddleware

            tester = EthereumTester(PyEVMBackend())
            w3 = Web3(Web3.EthereumTesterProvider(tester))
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            console.log(
                "[green]Provider[/] → in-process [bold]py-evm[/] (zero-cost demo mode)"
            )
        except ImportError:
            console.log(
                "[yellow]eth-tester / py-evm not installed. "
                "Falling back to Hardhat localhost at http://127.0.0.1:8545[/]"
            )
            w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
    else:
        w3 = Web3(Web3.HTTPProvider(uri))
        console.log(f"[green]Provider[/] → [cyan]{uri}[/]")

    if not w3.is_connected():
        raise ConnectionError(
            f"Cannot connect to Web3 provider '{uri}'.\n"
            "  • For local demo: pip install eth-tester py-evm\n"
            "  • For testnet:    set WEB3_PROVIDER_URI in .env"
        )

    console.log(
        f"[green]Connected [OK][/]  chainId=[cyan]{w3.eth.chain_id}[/]  "
        f"blockNumber=[cyan]{w3.eth.block_number}[/]"
    )
    return w3


# ─────────────────────────────────────────────────────────────────────────────
#  4. Deployment
# ─────────────────────────────────────────────────────────────────────────────


def deploy_contract(w3: object, abi: list, bytecode: str) -> dict:
    """
    Deploy IdentityRegistry and return a result dict with address + gas info.
    """
    from web3 import Web3

    raw_key = os.getenv("PRIVATE_KEY", "").strip().lstrip("0x")
    # Only use PRIVATE_KEY if it looks like a real 64-char hex string
    import re as _re

    private_key = raw_key if (_re.fullmatch(r"[0-9a-fA-F]{64}", raw_key)) else ""

    # Ignore PRIVATE_KEY if running on the local in-process tester (which doesn't fund it)
    if "EthereumTesterProvider" in str(type(w3.provider)):
        private_key = ""

    if private_key:
        acct = w3.eth.account.from_key(private_key)
        deployer = acct.address
        console.log(f"[cyan]Deployer[/] -> [bold]{deployer}[/] (from PRIVATE_KEY)")
    else:
        deployer = w3.eth.accounts[0]
        console.log(
            f"[yellow]PRIVATE_KEY not set -- using auto-generated unlocked account: "
            f"[bold]{deployer}[/][/]"
        )

    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_kwargs: dict = {
        "from": deployer,
        "gas": 3000000,
        "gasPrice": int(w3.eth.gas_price * 1.5),
    }

    t0 = time.perf_counter()

    if private_key:
        nonce = w3.eth.get_transaction_count(deployer)
        tx = Contract.constructor().build_transaction({**tx_kwargs, "nonce": nonce})
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    else:
        tx_hash = Contract.constructor().transact(tx_kwargs)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    elapsed = time.perf_counter() - t0

    address = receipt["contractAddress"]
    gas_used = receipt["gasUsed"]
    block_num = receipt["blockNumber"]
    tx_hex = tx_hash.hex()

    return {
        "deployed_address": address,
        "tx_hash": tx_hex,
        "gas_used": gas_used,
        "block_number": block_num,
        "elapsed_ms": round(elapsed * 1000, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  5. Persist artifact
# ─────────────────────────────────────────────────────────────────────────────


def persist_artifact(abi: list, bytecode: str, deploy_result: dict) -> None:
    """Write contracts/IdentityRegistry_artifacts.json."""
    artifact = {
        "abi": abi,
        "bytecode": "0x" + bytecode,
        "deployed_address": deploy_result["deployed_address"],
    }
    ARTIFACT_FILE.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    console.log(f"[green]Artifact saved →[/] {ARTIFACT_FILE}")

    # Update / create .env
    if not ENV_FILE.exists():
        ENV_FILE.touch()
    set_key(str(ENV_FILE), "CONTRACT_ADDRESS", deploy_result["deployed_address"])
    console.log(
        f"[green].env updated →[/] CONTRACT_ADDRESS={deploy_result['deployed_address']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  7. CLI summary
# ─────────────────────────────────────────────────────────────────────────────


def print_summary(deploy_result: dict) -> None:
    """Print the final deployment summary table."""
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="bold white", no_wrap=True)
    tbl.add_column("Value", style="cyan")

    rows = [
        ("Contract Address", deploy_result["deployed_address"]),
        ("Transaction Hash", deploy_result["tx_hash"]),
        ("Block Number", str(deploy_result["block_number"])),
        ("Gas Used", f"{deploy_result['gas_used']:,}"),
        ("Elapsed", f"{deploy_result['elapsed_ms']} ms"),
        ("Artifact", str(ARTIFACT_FILE)),
    ]
    for k, v in rows:
        tbl.add_row(k, v)

    console.print(
        Panel(
            tbl,
            title="[bold green] [>>] IdentityRegistry -- Deployed Successfully",
            border_style="green",
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
#  8. Entry-point
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Deploy IdentityRegistry.sol")
    p.add_argument(
        "--network",
        choices=["local", "sepolia"],
        default="local",
        help="Network to deploy to (local or sepolia).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    console.rule(f"[bold blue]Phase 2 -- Contract Deployment ({args.network})")

    bootstrap_solc()
    abi, bytecode = compile_contract()
    w3 = build_w3(network=args.network)
    deploy_result = deploy_contract(w3, abi, bytecode)
    persist_artifact(abi, bytecode, deploy_result)
    print_summary(deploy_result)

    console.rule("[bold green]Done -- Deployment Complete")


if __name__ == "__main__":
    main()
