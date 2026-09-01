"""
blockchain.py
-------------
Stage 3 of the pipeline: anchor OSINT results on the IdentityRegistry contract.

Public surface
--------------
    BlockchainAnchor(artifacts_path=..., rpc_url=None)
        .anchor_record(data_hash, source_url, confidence_bps) -> dict
        .verify_record(data_hash)                              -> dict

anchor_record return schema
---------------------------
    {
        "tx_hash":      str,   # "0x..."
        "block_number": int,
        "gas_used":     int,
        "status":       int    # 1 = success, 0 = reverted
    }

verify_record return schema
----------------------------
    {
        "exists":               bool,
        "source_url":           str,
        "confidence_bps":       int,
        "timestamp":            int,   # Unix epoch seconds
        "timestamp_formatted":  str    # ISO-8601 UTC
    }
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_DEFAULT_ARTIFACTS = "contracts/IdentityRegistry_artifacts.json"


# ─────────────────────────────────────────────────────────────────────────────
#  Main class
# ─────────────────────────────────────────────────────────────────────────────

class BlockchainAnchor:
    """
    High-level interface for writing and reading IdentityRegistry records.

    Parameters
    ----------
    artifacts_path : Path to the JSON file produced by ``deploy.py``.
                     Contains ``abi``, ``bytecode``, and ``deployed_address``.
    rpc_url        : Optional Web3 RPC endpoint.  Overrides
                     ``WEB3_PROVIDER_URI`` env var.  If neither is set the
                     class uses the in-process py-evm tester backend.
    """

    def __init__(
        self,
        artifacts_path: str = _DEFAULT_ARTIFACTS,
        rpc_url:        Optional[str] = None,
    ) -> None:
        self._artifacts_path = Path(artifacts_path)
        self._rpc_override   = rpc_url
        self._w3             = None   # lazy
        self._contract       = None   # lazy

    # ─────────────────────────────────────────────────────────────────────────
    #  Public: anchor_record
    # ─────────────────────────────────────────────────────────────────────────

    def anchor_record(
        self,
        data_hash:      Union[bytes, str],
        source_url:     str,
        confidence_bps: int,
    ) -> Dict:
        """
        Call ``registerRecord`` on the deployed contract and return tx metadata.

        Parameters
        ----------
        data_hash      : 32-byte ``bytes`` object  **or** "0x..." hex string.
        source_url     : Social / OSINT URL of the matched identity.
        confidence_bps : Confidence score, 0 – 10 000.

        Returns
        -------
        dict — tx_hash, block_number, gas_used, status

        Raises
        ------
        ValueError   if data_hash is not 32 bytes.
        RuntimeError if the transaction reverts.
        """
        b32 = _coerce_bytes32(data_hash)
        self._ensure_ready()

        w3       = self._w3
        contract = self._contract
        import re as _re
        _raw = os.getenv("PRIVATE_KEY", "").strip().lstrip("0x")
        private_key = _raw if _re.fullmatch(r"[0-9a-fA-F]{64}", _raw) else ""

        console.log(
            f"[bold cyan]BlockchainAnchor[/] → anchoring record "
            f"[green]{b32.hex()[:16]}…[/]"
        )

        tx_kwargs: Dict = {
            "gas":      300_000,
            "gasPrice": w3.eth.gas_price,
        }

        if private_key:
            acct    = w3.eth.account.from_key(private_key)
            sender  = acct.address
            nonce   = w3.eth.get_transaction_count(sender)
            tx = contract.functions.registerRecord(
                b32, source_url, confidence_bps
            ).build_transaction({**tx_kwargs, "from": sender, "nonce": nonce})
            signed   = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash  = w3.eth.send_raw_transaction(signed.raw_transaction)
        else:
            sender = w3.eth.accounts[0]
            tx_hash = contract.functions.registerRecord(
                b32, source_url, confidence_bps
            ).transact({**tx_kwargs, "from": sender})

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        result: Dict = {
            "tx_hash":      tx_hash.hex(),
            "block_number": receipt["blockNumber"],
            "gas_used":     receipt["gasUsed"],
            "status":       receipt["status"],
        }

        if receipt["status"] == 0:
            raise RuntimeError(
                f"Transaction reverted.  "
                f"Possible duplicate — call verify_record first.\n"
                f"tx_hash: {result['tx_hash']}"
            )

        _print_anchor(result, b32.hex(), source_url, confidence_bps)
        return result

    # ─────────────────────────────────────────────────────────────────────────
    #  Public: verify_record
    # ─────────────────────────────────────────────────────────────────────────

    def verify_record(self, data_hash: Union[bytes, str]) -> Dict:
        """
        Call the ``verifyRecord`` view function and return a structured result.

        Parameters
        ----------
        data_hash : 32-byte ``bytes`` object  **or** "0x..." hex string.

        Returns
        -------
        dict — exists, source_url, confidence_bps, timestamp,
               timestamp_formatted (ISO-8601 UTC)
        """
        b32 = _coerce_bytes32(data_hash)
        self._ensure_ready()

        console.log(
            f"[bold cyan]BlockchainAnchor[/] → verifying "
            f"[yellow]{b32.hex()[:16]}…[/]"
        )

        exists, source_url, confidence_bps, timestamp = (
            self._contract.functions.verifyRecord(b32).call()
        )

        ts_fmt = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            if timestamp > 0
            else "—"
        )

        result: Dict = {
            "exists":               exists,
            "source_url":           source_url,
            "confidence_bps":       confidence_bps,
            "timestamp":            timestamp,
            "timestamp_formatted":  ts_fmt,
        }

        _print_verify(result, b32.hex())
        return result

    # ─────────────────────────────────────────────────────────────────────────
    #  Private: lazy initialisation
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_ready(self) -> None:
        if self._w3 is None:
            self._w3 = _build_w3(self._rpc_override)
        if self._contract is None:
            self._contract = _load_contract(self._w3, self._artifacts_path)

    # ─────────────────────────────────────────────────────────────────────────
    #  Context manager (optional — lets users use `with BlockchainAnchor()`)
    # ─────────────────────────────────────────────────────────────────────────

    def __enter__(self) -> "BlockchainAnchor":
        self._ensure_ready()
        return self

    def __exit__(self, *_) -> None:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Private: Web3 / contract helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_w3(rpc_override: Optional[str]):
    """Return a connected Web3 instance."""
    from web3 import Web3

    uri = rpc_override or os.getenv("WEB3_PROVIDER_URI", "evm://")

    if uri.startswith("evm://"):
        try:
            from eth_tester import EthereumTester, PyEVMBackend
            from web3.middleware import ExtraDataToPOAMiddleware

            tester = EthereumTester(PyEVMBackend())
            w3 = Web3(Web3.EthereumTesterProvider(tester))
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            console.log(
                "[green]BlockchainAnchor[/] → in-process [bold]py-evm[/] "
                "(zero-cost demo mode)"
            )
        except ImportError:
            console.log(
                "[yellow]eth-tester not installed — trying localhost:8545[/]"
            )
            w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
    else:
        w3 = Web3(Web3.HTTPProvider(uri))
        console.log(f"[green]BlockchainAnchor[/] → provider [cyan]{uri}[/]")

    if not w3.is_connected():
        raise ConnectionError(
            f"Cannot connect to Web3 provider '{uri}'.\n"
            "  • For local demo:  pip install eth-tester py-evm\n"
            "  • For testnet:     set WEB3_PROVIDER_URI in .env"
        )

    console.log(
        f"[green]Connected ✓[/]  chainId=[cyan]{w3.eth.chain_id}[/]  "
        f"block=[cyan]{w3.eth.block_number}[/]"
    )
    return w3


def _load_contract(w3, artifacts_path: Path):
    """
    Bind the deployed IdentityRegistry contract.

    For in-process py-evm (fresh chain, block=0) the contract is
    re-deployed automatically from the artifact bytecode — no separate
    deploy.py run is needed.  For persistent chains (HTTP RPC) the
    pre-deployed address from the artifact / CONTRACT_ADDRESS env var is used.
    """
    if not artifacts_path.exists():
        raise FileNotFoundError(
            f"Artifact file not found: {artifacts_path}\n"
            "Run [bold cyan]python deploy.py[/] first."
        )

    artifact = json.loads(artifacts_path.read_text(encoding="utf-8"))
    abi      = artifact["abi"]
    bytecode = artifact.get("bytecode", "")
    address  = artifact.get("deployed_address") or os.getenv("CONTRACT_ADDRESS", "")

    # ── Auto-deploy on fresh in-process evm:// chain ──────────────────────────
    # py-evm starts at block 0.  The address saved by deploy.py points to a
    # *different* ephemeral chain that no longer exists, so we must re-deploy.
    is_fresh_evm = (w3.eth.block_number == 0 and
                    w3.eth.chain_id == 131277322940537)  # py-evm default chain ID

    if is_fresh_evm and bytecode:
        console.log(
            "[yellow]Fresh py-evm chain detected — auto-deploying contract...[/]"
        )
        deployer = w3.eth.accounts[0]
        Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash  = Contract.constructor().transact({"from": deployer, "gas": 1_500_000})
        receipt  = w3.eth.wait_for_transaction_receipt(tx_hash)
        address  = receipt["contractAddress"]
        console.log(
            f"[green]Auto-deployed[/] IdentityRegistry @ [cyan]{address}[/]"
        )

    if not address:
        raise EnvironmentError(
            "Contract address missing from artifact and CONTRACT_ADDRESS env var.\n"
            "Run [bold cyan]python deploy.py[/] to deploy and auto-populate."
        )

    checksum = w3.to_checksum_address(address)
    contract = w3.eth.contract(address=checksum, abi=abi)
    console.log(
        f"[green]Contract loaded[/]  IdentityRegistry @ [cyan]{checksum}[/]"
    )
    return contract



def _coerce_bytes32(value: Union[bytes, str]) -> bytes:
    """Normalise input to a 32-byte ``bytes`` object."""
    if isinstance(value, bytes):
        if len(value) != 32:
            raise ValueError(
                f"data_hash must be exactly 32 bytes, got {len(value)}."
            )
        return value

    if isinstance(value, str):
        hex_str = value.removeprefix("0x")
        if len(hex_str) != 64:
            raise ValueError(
                f"data_hash hex must be 64 hex chars (32 bytes), "
                f"got {len(hex_str)} chars."
            )
        return bytes.fromhex(hex_str)

    raise TypeError(f"data_hash must be bytes or str, got {type(value).__name__}.")


# ─────────────────────────────────────────────────────────────────────────────
#  Private: rich output helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_anchor(
    result: Dict, hash_hex: str, source_url: str, confidence_bps: int
) -> None:
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key",   style="bold white", no_wrap=True)
    tbl.add_column("Value", style="cyan")

    tbl.add_row("Payload hash",  hash_hex[:16] + "…")
    tbl.add_row("Source URL",    source_url or "—")
    tbl.add_row("Confidence",    f"{confidence_bps} bps ({confidence_bps/100:.1f}%)")
    tbl.add_row("TX hash",       result["tx_hash"][:20] + "…")
    tbl.add_row("Block number",  str(result["block_number"]))
    tbl.add_row("Gas used",      f"{result['gas_used']:,}")
    tbl.add_row("Status",        "✅ Success" if result["status"] == 1 else "❌ Reverted")

    console.print(
        Panel(tbl, title="⛓  Record Anchored On-Chain", border_style="green")
    )


def _print_verify(result: Dict, hash_hex: str) -> None:
    border = "green" if result["exists"] else "yellow"
    icon   = "✅" if result["exists"] else "❌"

    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key",   style="bold white", no_wrap=True)
    tbl.add_column("Value", style="cyan")

    tbl.add_row("Hash",       hash_hex[:16] + "…")
    tbl.add_row("Exists",     str(result["exists"]))
    tbl.add_row("Source URL", result["source_url"] or "—")
    tbl.add_row("Confidence", f"{result['confidence_bps']} bps "
                              f"({result['confidence_bps']/100:.1f}%)")
    tbl.add_row("Timestamp",  result["timestamp_formatted"])

    console.print(
        Panel(
            tbl,
            title=f"{icon}  Verification Result",
            border_style=border,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Smoke test  (python modules/blockchain.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    console.rule("[bold blue]BlockchainAnchor — Smoke Test")
    console.log("[dim]Using in-process py-evm + fresh contract deploy …[/]")

    # ── 1. Compile & deploy a fresh contract for the smoke test ──────────────
    try:
        import solcx  # noqa: F401
    except ImportError:
        console.print(
            "[bold red]py-solc-x not installed.[/]  "
            "Run [cyan]pip install py-solc-x[/] first."
        )
        sys.exit(1)

    # Inline mini-deploy so the smoke test is self-contained
    from deploy import bootstrap_solc, compile_contract, build_w3, persist_artifact

    bootstrap_solc()
    abi, bytecode = compile_contract()
    w3 = build_w3()

    from web3 import Web3
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash  = Contract.constructor().transact({"from": w3.eth.accounts[0], "gas": 1_500_000})
    receipt  = w3.eth.wait_for_transaction_receipt(tx_hash)
    address  = receipt["contractAddress"]

    # Persist so BlockchainAnchor can load it
    import json as _json
    artifact_path = Path("contracts/IdentityRegistry_artifacts.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        _json.dumps({"abi": abi, "bytecode": "0x" + bytecode, "deployed_address": address}, indent=2),
        encoding="utf-8",
    )
    console.log(f"[green]Smoke-test contract deployed @ {address}[/]")

    # ── 2. Build a dummy 32-byte hash ─────────────────────────────────────────
    import hashlib
    test_hash: bytes = hashlib.sha256(b"smoke-test-payload").digest()
    test_url  = "https://linkedin.com/in/smoke-test"
    test_bps  = 9_500

    # ── 3. Anchor ─────────────────────────────────────────────────────────────
    # Use the same w3 + contract by monkey-patching via artifacts file
    anchor = BlockchainAnchor(artifacts_path=str(artifact_path))
    # Directly inject the already-connected w3 to avoid reconnect
    anchor._w3       = w3
    anchor._contract = w3.eth.contract(
        address=w3.to_checksum_address(address), abi=abi
    )

    result = anchor.anchor_record(test_hash, test_url, test_bps)
    assert result["status"] == 1, "anchor_record should succeed"

    # ── 4. Verify ─────────────────────────────────────────────────────────────
    verification = anchor.verify_record(test_hash)
    assert verification["exists"],                   "record should exist"
    assert verification["source_url"] == test_url,   "source_url mismatch"
    assert verification["confidence_bps"] == test_bps, "confidence_bps mismatch"

    # ── 5. Duplicate rejection test ───────────────────────────────────────────
    try:
        anchor.anchor_record(test_hash, test_url, test_bps)
        console.log("[bold red]FAIL — duplicate should have reverted![/]")
        sys.exit(1)
    except RuntimeError as exc:
        console.log(f"[green]✓ Duplicate correctly rejected:[/] {exc}")

    console.rule("[bold green]All smoke tests passed ✓")
