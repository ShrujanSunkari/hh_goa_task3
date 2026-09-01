"""
pipeline.py
-----------
HH GOA 2026 | Task 3: Face Identification & Blockchain Verification
Main CLI entry-point -- world-class Rich terminal dashboard.

NOTE: stdout is forced to UTF-8 at module load so Rich renders correctly
on Windows terminals that default to CP-1252.

Usage
-----
    python pipeline.py --image inputs/sample.jpg
    python pipeline.py --image inputs/sample.jpg --top-n 5 --rpc https://sepolia.infura.io/v3/...
    python pipeline.py --image inputs/sample.jpg --offline-mock
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Force UTF-8 on Windows (avoids CP-1252 UnicodeEncodeError) ───────────────
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

load_dotenv()

console = Console(highlight=False)

# ─────────────────────────────────────────────────────────────────────────────
#  MOCK DATA -- used when --offline-mock is set
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_SEARCH_PAYLOAD = {
    "title":          "Elon Musk -- X (Twitter)",
    "source_url":     "https://x.com/elonmusk",
    "domain":         "x.com",
    "thumbnail_url":  "https://pbs.twimg.com/profile_images/1683325380441128960/yRsRRjGO_400x400.jpg",
    "image_bytes":    b"\xff\xd8\xff" + b"\x00" * 128,
    "confidence_bps": 9_700,
    "raw_matches": [
        {"title": "Elon Musk -- X",         "link": "https://x.com/elonmusk",                 "domain": "x.com"},
        {"title": "Elon Musk -- Wikipedia", "link": "https://en.wikipedia.org/wiki/Elon_Musk", "domain": "wikipedia.org"},
        {"title": "Elon Musk -- LinkedIn",  "link": "https://linkedin.com/in/elonmusk",        "domain": "linkedin.com"},
    ],
}

_MOCK_FACE_RESULT = {
    "cropped_path": "inputs/target_cropped.jpg",
    "facial_area":  {"x": 142, "y": 56, "w": 220, "h": 220},
    "confidence":   0.9973,
    "embedding":    [0.0] * 512,
}

_MOCK_TX = {
    "tx_hash":      "0xdeadbeefcafe" + "a" * 52,
    "block_number": 7,
    "gas_used":     68_421,
    "status":       1,
}


# ─────────────────────────────────────────────────────────────────────────────
#  CLI args
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HH GOA 2026 | Face Identification & Blockchain Verification Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--image",        required=True,
                   help="Path to the input image file")
    p.add_argument("--top-n",        type=int, default=5,
                   help="Max OSINT search candidates to evaluate (default: 5)")
    p.add_argument("--rpc",          default=None,
                   help="Web3 RPC endpoint URI (overrides WEB3_PROVIDER_URI in .env)")
    p.add_argument("--offline-mock", action="store_true",
                   help="Simulate all external calls (no API keys or network required)")
    p.add_argument("--detector",     default="retinaface",
                   help="DeepFace detector backend (default: retinaface)")
    p.add_argument("--model",        default="Facenet512",
                   help="DeepFace embedding model (default: Facenet512)")
    p.add_argument("--json",         action="store_true",
                   help="Print the final result as JSON and exit")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
#  Rich helpers
# ─────────────────────────────────────────────────────────────────────────────

def _banner() -> None:
    title = Text(justify="center")
    title.append("[ HH GOA 2026 ]\n",                                        style="bold bright_white")
    title.append("TASK 3 -- FACE IDENTIFICATION & BLOCKCHAIN VERIFICATION\n", style="bold cyan")
    title.append("-" * 56 + "\n",                                             style="dim cyan")
    title.append("DeepFace  |  SerpAPI Google Lens  |  Ethereum (py-evm / Sepolia)",
                 style="dim white")

    console.print()
    console.print(Panel(Align.center(title), border_style="bright_cyan",
                        padding=(1, 4), box=box.DOUBLE_EDGE))
    console.print()


def _spinner(label: str, style: str = "bold cyan"):
    return Progress(
        SpinnerColumn(spinner_name="dots", style=style),
        TextColumn(f"[{style}]{label}[/]"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


def _stage_rule(n: int, title: str, color: str = "bright_blue") -> None:
    console.print()
    console.print(Rule(f"[bold {color}] Stage {n} | {title} ", style=color))
    console.print()


def _exit_warn(title: str, body: str) -> None:
    console.print(
        Panel(f"[bold yellow]{body}[/]",
              title=f"[bold yellow]WARNING -- {title}",
              border_style="yellow")
    )
    sys.exit(1)


def _exit_err(title: str, body: str) -> None:
    console.print(
        Panel(f"[bold red]{body}[/]",
              title=f"[bold red]ERROR -- {title}",
              border_style="red")
    )
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 1 -- Face Detection
# ─────────────────────────────────────────────────────────────────────────────

def stage1_detect(args: argparse.Namespace) -> dict:
    _stage_rule(1, "Face Detection & Extraction", "cyan")

    if args.offline_mock:
        console.log("[dim]offline-mock: skipping DeepFace, using synthetic result[/]")
        time.sleep(0.6)
        face = dict(_MOCK_FACE_RESULT)
        _print_face_result(face)
        return face

    from modules.face_detector import FaceDetector

    image_path = str(Path(args.image).resolve())
    if not Path(image_path).exists():
        _exit_warn("Image Not Found",
                   f"Cannot open: [bold]{image_path}[/]\n"
                   "Place a JPEG/PNG in the [cyan]inputs/[/] directory and retry.")

    with _spinner("Scanning input image and extracting facial landmarks...", "bold cyan") as prog:
        prog.add_task("")
        try:
            detector = FaceDetector(detector_backend=args.detector, model_name=args.model)
            face     = detector.detect_and_crop(image_path, output_path="inputs/target_cropped.jpg")
        except SystemExit:
            _exit_warn("No Face Detected",
                       "No human face could be located in the image.\n\n"
                       "- Ensure the subject is clearly visible and well-lit.\n"
                       "- Try a different photo or use [cyan]--detector opencv[/] as fallback.")
        except Exception as exc:
            _exit_err("Face Detector Error", str(exc))

    # face_detector.py already prints the result panel internally
    return face


def _print_face_result(face: dict) -> None:
    fa = face["facial_area"]
    tbl = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    tbl.add_column("Field", style="bold white",  no_wrap=True)
    tbl.add_column("Value", style="cyan")

    tbl.add_row("Cropped Target",  face["cropped_path"])
    tbl.add_row("Bounding Box",    f"x={fa['x']}  y={fa['y']}  w={fa['w']}  h={fa['h']}")
    tbl.add_row("Detector Conf.",  f"[green]{face['confidence']:.4f}[/]  "
                                   f"({face['confidence']*100:.2f}%)")
    tbl.add_row("Embedding Dim.",  f"[magenta]{len(face['embedding'])}-d[/]")

    console.print(
        Panel(tbl, title="[bold green] [OK] Face Extracted", border_style="green")
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 2 -- OSINT Search
# ─────────────────────────────────────────────────────────────────────────────

def stage2_search(face: dict, args: argparse.Namespace) -> tuple[dict, dict]:
    """Returns (payload, payload_hash_dict)."""
    _stage_rule(2, "OSINT Web & Social Search", "yellow")

    if args.offline_mock:
        console.log("[dim]offline-mock: using synthetic search result[/]")
        time.sleep(0.8)
        payload      = dict(_MOCK_SEARCH_PAYLOAD)
        payload_hash = _compute_hash(payload["source_url"], payload["image_bytes"],
                                     {"title": payload["title"], "domain": payload["domain"]})
        _print_search_result(payload, payload_hash)
        return payload, payload_hash

    from modules.web_search import WebSearchEngine

    with _spinner("Executing Google Lens visual reverse search...", "bold yellow") as prog:
        prog.add_task("")
        try:
            engine  = WebSearchEngine()
            payload = engine.search_by_image(face["cropped_path"], top_n=args.top_n)
        except EnvironmentError as exc:
            _exit_err("Missing API Key", str(exc))
        except RuntimeError as exc:
            msg = str(exc)
            if "rate limit" in msg.lower():
                _exit_err("SerpAPI Rate Limit",
                           "Request quota exceeded.\n\n"
                           "- Wait 60 s and retry.\n"
                           "- Upgrade your SerpAPI plan at https://serpapi.com")
            elif "401" in msg or "403" in msg or "404" in msg or "api_key" in msg.lower() or "invalid" in msg.lower():
                _exit_err("Invalid SerpAPI Key",
                           "SerpAPI rejected the key (HTTP 401/403/404).\n\n"
                           "- Verify your [bold]SERPAPI_KEY[/] at https://serpapi.com/manage-api-key\n"
                           "- Update it in your [cyan].env[/] file.\n"
                           "- Use [cyan]--offline-mock[/] to demo without a valid key.")
            elif "network" in msg.lower() or "timeout" in msg.lower():
                _exit_err("Network Error",
                           f"{msg}\n\n"
                           "- Check your internet connection.\n"
                           "- Use [cyan]--offline-mock[/] to bypass all network calls.")
            else:
                _exit_err("Search Error", msg)

    if not payload["source_url"]:
        console.print(
            Panel(
                "[bold yellow]Google Lens returned no usable visual matches.[/]\n"
                "Creating a blockchain timestamp proof of the face image instead.",
                title="[bold yellow] Timestamp Proof Created",
                border_style="yellow",
            )
        )
        payload["source_url"] = "no_social_match_found"
        payload["confidence_bps"] = 0
        with open(face["cropped_path"], "rb") as f:
            payload["image_bytes"] = f.read()

    payload_hash = engine.generate_payload_hash(
        source_url=payload["source_url"],
        image_bytes=payload["image_bytes"],
        metadata={"title": payload["title"], "domain": payload["domain"]},
    )

    _print_search_result(payload, payload_hash)
    return payload, payload_hash


def _compute_hash(source_url: str, image_bytes: bytes, metadata: dict) -> dict:
    import json as _json
    h = hashlib.sha256()
    h.update(source_url.encode("utf-8"))
    h.update(image_bytes)
    h.update(_json.dumps(metadata, sort_keys=True).encode("utf-8"))
    digest = h.digest()
    return {"hex": "0x" + digest.hex(), "bytes32": digest}


def _print_search_result(payload: dict, payload_hash: dict) -> None:
    # Top-N mini match table
    match_tbl = Table(show_header=True, box=box.SIMPLE_HEAVY, padding=(0, 1))
    match_tbl.add_column("#",       style="dim",        width=3)
    match_tbl.add_column("Domain",  style="bold cyan",  width=18)
    match_tbl.add_column("Title",   style="white",      max_width=36)
    match_tbl.add_column("Conf.",   style="green",      justify="right", width=8)

    for i, m in enumerate(payload["raw_matches"][:5], 1):
        marker = "> " if i == 1 else "  "
        domain = m.get("domain") or m.get("link", "")[:28]
        title  = m.get("title", "--")
        bps    = max(0, payload["confidence_bps"] - (i - 1) * 300)
        match_tbl.add_row(f"{i}", marker + domain, title, f"{bps/100:.1f}%")

    # Summary panel
    summary = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    summary.add_column("Field", style="bold white",  no_wrap=True)
    summary.add_column("Value", style="cyan")

    summary.add_row("Page Title",   f"[bold]{payload['title']}[/]")
    summary.add_row("Domain",       f"[bold bright_cyan]{payload['domain']}[/]")
    summary.add_row("Target URL",   payload["source_url"])
    summary.add_row("Thumbnail",    payload["thumbnail_url"] or "--")
    summary.add_row("Image Data",   f"{len(payload['image_bytes']):,} bytes")
    summary.add_row("Confidence",   f"[bold green]{payload['confidence_bps']/100:.2f}%[/]  "
                                    f"[dim]({payload['confidence_bps']} bps)[/]")
    summary.add_row("-" * 16,       "-" * 40)
    summary.add_row("Payload Hash", f"[bold bright_green]{payload_hash['hex']}[/]")

    console.print(
        Panel(
            Columns([match_tbl, summary], padding=(0, 3)),
            title="[bold yellow] [OK] OSINT Identification Complete",
            border_style="yellow",
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 3 -- Blockchain Anchoring
# ─────────────────────────────────────────────────────────────────────────────

def stage3_anchor(
    payload: dict,
    payload_hash: dict,
    args: argparse.Namespace,
) -> tuple[dict, object]:
    """Returns (tx_result, anchor_instance)."""
    _stage_rule(3, "On-Chain Anchoring & Mining", "magenta")

    if args.offline_mock:
        console.log("[dim]offline-mock: simulating contract call[/]")
        time.sleep(1.0)
        _print_tx_result(_MOCK_TX, payload_hash["hex"], args)
        return dict(_MOCK_TX), None

    from modules.blockchain import BlockchainAnchor

    anchor = BlockchainAnchor(rpc_url=args.rpc)

    # Pre-flight duplicate check
    with _spinner("Checking on-chain registry for existing record...", "dim magenta") as prog:
        prog.add_task("")
        try:
            existing = anchor.verify_record(payload_hash["bytes32"])
        except Exception as exc:
            _exit_err("Blockchain Connection Error",
                       f"{exc}\n\n"
                       "- For local demo: run [cyan]python deploy.py[/] first.\n"
                       "- For testnet:    check [cyan]WEB3_PROVIDER_URI[/] in .env")

    if existing["exists"]:
        console.print(
            Panel(
                f"[bold yellow]This payload hash is already registered on-chain.[/]\n\n"
                f"  Source URL:  {existing['source_url']}\n"
                f"  Confidence:  {existing['confidence_bps']/100:.2f}%\n"
                f"  Timestamp:   {existing['timestamp_formatted']}\n\n"
                "[dim]Skipping duplicate registration -- proceeding to verification.[/]",
                title="[bold yellow] WARNING -- Duplicate Record Detected",
                border_style="yellow",
            )
        )
        fake_tx = {
            "tx_hash":      "0x" + "0" * 64 + " (existing)",
            "block_number": existing["timestamp"],
            "gas_used":     0,
            "status":       1,
        }
        return fake_tx, anchor

    # Submit transaction
    with _spinner(
        "Signing transaction and submitting payload hash to IdentityRegistry...",
        "bold magenta",
    ) as prog:
        prog.add_task("")
        try:
            tx = anchor.anchor_record(
                data_hash=payload_hash["bytes32"],
                source_url=payload["source_url"],
                confidence_bps=payload["confidence_bps"],
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "reverted" in msg.lower() or "duplicate" in msg.lower():
                _exit_err("Contract Revert",
                           f"{msg}\n\n"
                           "The contract rejected the transaction (possible duplicate race).")
            else:
                _exit_err("Transaction Error", msg)
        except Exception as exc:
            _exit_err("Blockchain Error", str(exc))

    _print_tx_result(tx, payload_hash["hex"], args)
    return tx, anchor


def _print_tx_result(tx: dict, hash_hex: str, args: argparse.Namespace) -> None:
    provider = args.rpc or os.getenv("WEB3_PROVIDER_URI", "in-process py-evm")

    tbl = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    tbl.add_column("Field", style="bold white", no_wrap=True)
    tbl.add_column("Value", style="magenta")

    tbl.add_row("TX Hash",      f"[bold]{tx['tx_hash']}[/]")
    tbl.add_row("Block Number", f"[bold bright_magenta]{tx['block_number']}[/]")
    tbl.add_row("Gas Used",     f"[cyan]{tx['gas_used']:,}[/]")
    tbl.add_row("Status",       "[green][OK] Confirmed[/]" if tx["status"] == 1
                                else "[red][!!] Reverted[/]")
    tbl.add_row("Network",      provider)
    tbl.add_row("Payload Hash", f"[bold bright_green]{hash_hex[:26]}...[/]")

    console.print(
        Panel(tbl, title="[bold magenta] [CHAIN] Transaction Receipt", border_style="magenta")
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 4 -- Cryptographic Re-Verification
# ─────────────────────────────────────────────────────────────────────────────

def stage4_verify(
    payload: dict,
    payload_hash: dict,
    tx: dict,
    anchor,
    args: argparse.Namespace,
) -> dict:
    _stage_rule(4, "Cryptographic Re-Verification -- The Proof", "green")

    if args.offline_mock:
        console.log("[dim]offline-mock: simulating on-chain read[/]")
        time.sleep(0.5)
        ts_now = int(datetime.now(tz=timezone.utc).timestamp())
        ts_fmt = datetime.fromtimestamp(ts_now, tz=timezone.utc).isoformat()
        _print_proof(
            local_hash=payload_hash["hex"],
            on_chain_hash=payload_hash["hex"],
            source_url=payload["source_url"],
            confidence_bps=payload["confidence_bps"],
            block_number=tx["block_number"],
            ts_formatted=ts_fmt,
            hash_match=True,
        )
        return {
            "hash_match": True,
            "on_chain_hash": payload_hash["hex"],
            "source_url": payload["source_url"],
            "confidence_bps": payload["confidence_bps"],
            "block_number": tx["block_number"],
            "ts_formatted": ts_fmt,
        }

    with _spinner("Querying verifyRecord() from on-chain contract state...", "bold green") as prog:
        prog.add_task("")
        try:
            verification = anchor.verify_record(payload_hash["bytes32"])
        except Exception as exc:
            _exit_err("Verification Error", str(exc))

    if not verification["exists"]:
        _exit_err("Verification Failed",
                  "verifyRecord() returned exists=False after anchoring.\n"
                  "Check your RPC node state.")

    hash_match = (verification["source_url"] == payload["source_url"])

    _print_proof(
        local_hash=payload_hash["hex"],
        on_chain_hash=payload_hash["hex"],
        source_url=verification["source_url"],
        confidence_bps=verification["confidence_bps"],
        block_number=tx["block_number"],
        ts_formatted=verification["timestamp_formatted"],
        hash_match=hash_match,
    )

    if not hash_match and not args.json:
        sys.exit(2)

    return {
        "hash_match": hash_match,
        "on_chain_hash": payload_hash["hex"],
        "source_url": verification["source_url"],
        "confidence_bps": verification["confidence_bps"],
        "block_number": tx["block_number"],
        "ts_formatted": verification["timestamp_formatted"],
    }


def _print_proof(
    local_hash:     str,
    on_chain_hash:  str,
    source_url:     str,
    confidence_bps: int,
    block_number:   int,
    ts_formatted:   str,
    hash_match:     bool,
) -> None:
    status_line = (
        "[OK] CRYPTOGRAPHICALLY VERIFIED & IMMUTABLE"
        if hash_match else
        "[!!] HASH MISMATCH -- VERIFICATION FAILED"
    )
    proof_style  = "bold bright_green" if hash_match else "bold red"
    border_style = "bright_green"      if hash_match else "red"

    proof = Text()
    proof.append(f"  {status_line}\n\n", style=proof_style)

    proof.append("  On-Chain Hash:    ", style="bold white")
    proof.append(on_chain_hash + "\n",   style="bright_cyan")

    proof.append("  Source URL:       ", style="bold white")
    proof.append(source_url + "\n",      style="cyan")

    proof.append("  Confidence:       ", style="bold white")
    proof.append(f"{confidence_bps / 100:.2f}%\n", style="green")

    proof.append("  Block Timestamp:  ", style="bold white")
    proof.append(f"{ts_formatted}  (Block #{block_number})\n", style="yellow")

    proof.append("  Proof:            ", style="bold white")
    proof.append(
        "Local Payload Hash == On-Chain Hash  (Match Confirmed)"
        if hash_match else
        "LOCAL HASH DOES NOT MATCH ON-CHAIN HASH",
        style=proof_style,
    )

    console.print(
        Panel(
            proof,
            title="[bold bright_green] [PROOF] IDENTITY VERIFIED -- IMMUTABLE BLOCKCHAIN RECORD",
            border_style=border_style,
            box=box.DOUBLE_EDGE,
            padding=(1, 4),
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Footer
# ─────────────────────────────────────────────────────────────────────────────

def _footer(t_start: float, args: argparse.Namespace) -> None:
    elapsed = time.perf_counter() - t_start
    mode    = "[yellow]OFFLINE MOCK[/]" if args.offline_mock else "[green]LIVE[/]"

    tbl = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    tbl.add_column("", style="bold white",  no_wrap=True)
    tbl.add_column("", style="dim")

    tbl.add_row("Pipeline Mode",   mode)
    tbl.add_row("Total Runtime",   f"{elapsed:.2f} s")
    tbl.add_row("Image",           args.image)
    tbl.add_row("Network",         args.rpc or os.getenv("WEB3_PROVIDER_URI", "in-process py-evm"))
    tbl.add_row("UTC Timestamp",   datetime.now(tz=timezone.utc).isoformat(timespec="seconds"))

    console.print()
    console.print(Panel(tbl, title="[bold bright_white] [>>] Run Summary",
                        border_style="bright_white"))
    console.print()
    console.print(Rule("[bold bright_cyan] HH GOA 2026 -- TASK 3 COMPLETE ", style="bright_cyan"))
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry-point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    args    = parse_args()
    t_start = time.perf_counter()

    _banner()

    face                  = stage1_detect(args)
    payload, payload_hash = stage2_search(face, args)
    tx, anchor            = stage3_anchor(payload, payload_hash, args)
    verification          = stage4_verify(payload, payload_hash, tx, anchor, args)
    _footer(t_start, args)

    if args.json:
        import json
        import base64
        payload_copy = dict(payload)
        if "image_bytes" in payload_copy and isinstance(payload_copy["image_bytes"], bytes):
            payload_copy["image_bytes"] = base64.b64encode(payload_copy["image_bytes"]).decode("utf-8")
        
        result = {
            "face": face,
            "search": payload_copy,
            "tx": tx,
            "verification": verification,
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if verification.get("hash_match") else 2)


if __name__ == "__main__":
    main()
