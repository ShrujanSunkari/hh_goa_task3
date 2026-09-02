"""
scripts/anchor_demo_record.py
-----------------------------
Executes a real on-chain transaction to anchor a payload hash on Sepolia,
waits for the receipt, and immediately verifies it via a view call.
"""

import sys
import os
from pathlib import Path
import hashlib

# Add project root to sys.path so modules can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from modules.blockchain import BlockchainAnchor

console = Console()


def main():
    load_dotenv()
    console.rule("[bold cyan]Sepolia Testnet Anchoring Demo")

    # Initialize the BlockchainAnchor
    try:
        anchor = BlockchainAnchor()
    except Exception as e:
        console.log(f"[bold red]Failed to initialize BlockchainAnchor: {e}[/]")
        sys.exit(1)

    # Generate a demo payload
    demo_text = os.urandom(16) + b" - HH Goa 2026 Sepolia Live Proof"
    payload_hash = hashlib.sha256(demo_text).digest()
    source_url = "https://github.com/ShrujanSunkari/hh_goa_task3"
    confidence_bps = 10000

    console.print(f"  [white]Demo Payload:[/]      [cyan]Randomized Demo Payload[/]")
    console.print(f"  [white]Payload Hash (b32):[/] [yellow]0x{payload_hash.hex()}[/]")
    console.print()

    # 1. Anchor the record
    try:
        tx_result = anchor.anchor_record(
            data_hash=payload_hash, source_url=source_url, confidence_bps=confidence_bps
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        console.log(f"[bold red]Anchoring transaction failed:[/] {e}")
        console.log(
            "Ensure your .env has a valid PRIVATE_KEY with Sepolia ETH and a working Infura RPC."
        )
        sys.exit(1)

    tx_hash = tx_result["tx_hash"]
    block_num = tx_result["block_number"]

    console.print()
    console.print(
        Panel(
            f"Transaction confirmed in Block: [bold]{block_num}[/]\n"
            f"View on Etherscan: [bright_cyan]https://sepolia.etherscan.io/tx/{tx_hash}[/]",
            title="[bold green]Live Sepolia Proof",
            border_style="green",
        )
    )
    console.print()

    # 2. Verify the record
    try:
        verify_result = anchor.verify_record(data_hash=payload_hash)
    except Exception as e:
        console.log(f"[bold red]Verification call failed:[/] {e}")
        sys.exit(1)

    if verify_result["exists"] and verify_result["source_url"] == source_url:
        console.log(
            "[bold bright_green]SUCCESS: On-chain proof matches local payload perfectly.[/]"
        )
    else:
        console.log(
            "[bold red]FAILURE: On-chain proof does not match local payload.[/]"
        )


if __name__ == "__main__":
    main()
