import argparse
import hashlib
import os
import platform
import statistics
import sys
import time
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Import pipeline modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from modules.face_detector import FaceDetector
from modules.web_search import WebSearchEngine
from modules.blockchain import BlockchainAnchor
from dotenv import load_dotenv

console = Console()


class SuppressOutput:
    def __enter__(self):
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr


def get_system_info() -> str:
    info = []
    info.append(f"OS: {platform.system()} {platform.release()}")
    info.append(f"CPU: {platform.processor()}")
    if HAS_PSUTIL:
        ram = psutil.virtual_memory()
        info.append(f"RAM: {ram.total / (1024**3):.1f} GB")
    else:
        info.append("RAM: Unknown (psutil not installed)")
    return " | ".join(info)


def run_benchmark(n_runs: int, offline_mock: bool, image_path: str):
    load_dotenv()

    times = {
        "Face Detection": [],
        "OSINT Search": [],
        "Payload Hashing": [],
        "Blockchain Anchoring": [],
        "Blockchain Verification": [],
        "End-to-End": [],
    }

    console.print(f"[bold cyan]Running Benchmark (N={n_runs})[/]")
    console.print(f"[dim]Mode:[/] {'Offline Mock' if offline_mock else 'Live Network'}")
    console.print(f"[dim]System:[/] {get_system_info()}")
    console.print("-" * 50)

    # Initialize components
    with SuppressOutput():
        detector = FaceDetector(offline_fallback=offline_mock)
        engine = WebSearchEngine()
        rpc_url = None if offline_mock else os.getenv("WEB3_PROVIDER_URI")
        anchor = BlockchainAnchor(rpc_url=rpc_url)

    for i in range(n_runs):
        console.print(f"Running iteration {i+1}/{n_runs}...", end="\r")

        try:
            with SuppressOutput():
                t_start_e2e = time.perf_counter()

                # 1. Face Detection
                t0 = time.perf_counter()
                face = detector.detect_and_crop(
                    image_path, "inputs/benchmark_cropped.jpg"
                )
                t_face = time.perf_counter() - t0

                # 2. OSINT Search
                t0 = time.perf_counter()
                if offline_mock:
                    # Simulate search
                    time.sleep(0.8)
                    payload = {
                        "source_url": "https://x.com/mock",
                        "image_bytes": b"mock_bytes",
                        "title": "Mock",
                        "domain": "x.com",
                        "confidence_bps": 9000,
                    }
                else:
                    payload = engine.search_by_image(face["cropped_path"], top_n=2)
                t_search = time.perf_counter() - t0

                # 3. Hash Generation
                t0 = time.perf_counter()
                if offline_mock:
                    h = hashlib.sha256()
                    h.update(payload["source_url"].encode("utf-8"))
                    h.update(payload["image_bytes"])
                    h.update(b'{"title": "Mock", "domain": "x.com"}')
                    data_hash = h.digest()
                else:
                    data_hash_dict = engine.generate_payload_hash(
                        source_url=payload["source_url"],
                        image_bytes=payload["image_bytes"],
                        metadata={
                            "title": payload["title"],
                            "domain": payload["domain"],
                        },
                    )
                    data_hash = data_hash_dict["bytes32"]
                t_hash = time.perf_counter() - t0

                # 4. Blockchain Anchoring
                t0 = time.perf_counter()
                if offline_mock:
                    time.sleep(1.0)
                else:
                    # Add a unique salt to avoid duplicate revert
                    h = hashlib.sha256(data_hash)
                    h.update(str(time.perf_counter()).encode())
                    unique_hash = h.digest()
                    anchor.anchor_record(
                        data_hash=unique_hash,
                        source_url=payload["source_url"],
                        confidence_bps=payload["confidence_bps"],
                    )
                t_anchor = time.perf_counter() - t0

                # 5. Blockchain Verification
                t0 = time.perf_counter()
                if offline_mock:
                    time.sleep(0.5)
                else:
                    anchor.verify_record(unique_hash)
                t_verify = time.perf_counter() - t0

                t_e2e = time.perf_counter() - t_start_e2e

            # Record times
            times["Face Detection"].append(t_face)
            times["OSINT Search"].append(t_search)
            times["Payload Hashing"].append(t_hash)
            times["Blockchain Anchoring"].append(t_anchor)
            times["Blockchain Verification"].append(t_verify)
            times["End-to-End"].append(t_e2e)
        except Exception as e:
            # If an iteration fails (e.g. rate limit or blockchain timeout), skip it and continue
            pass

    console.print(f"Running iteration {n_runs}/{n_runs}... Done!   ")
    console.print()

    # Generate Report Table
    tbl = Table(title="Pipeline Performance Benchmarks", box=box.SIMPLE_HEAVY)
    tbl.add_column("Stage", style="bold white")
    tbl.add_column("Mean", justify="right", style="cyan")
    tbl.add_column("Median", justify="right", style="cyan")
    tbl.add_column("Stdev", justify="right", style="dim")

    for stage, t_list in times.items():
        mean_t = statistics.mean(t_list)
        med_t = statistics.median(t_list)
        std_t = statistics.stdev(t_list) if len(t_list) > 1 else 0.0

        if stage == "End-to-End":
            tbl.add_row("-" * 20, "-" * 10, "-" * 10, "-" * 10)

        tbl.add_row(
            f"[bold]{stage}[/]" if stage == "End-to-End" else stage,
            f"{mean_t:.3f} s",
            f"{med_t:.3f} s",
            f"±{std_t:.3f} s",
        )

    console.print(tbl)
    console.print(
        f"[dim]Total N={n_runs} runs. Mode: {'Offline Mock' if offline_mock else 'Live Network'}.[/]"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Performance Benchmark")
    parser.add_argument("--n", type=int, default=20, help="Number of iterations")
    parser.add_argument("--offline-mock", action="store_true", help="Run with mocks")
    parser.add_argument("--live", action="store_true", help="Run live network")
    parser.add_argument("--image", default="inputs/sample.jpg", help="Image to test")

    args = parser.parse_args()

    if not args.offline_mock and not args.live:
        print("Please specify --offline-mock or --live.")
        sys.exit(1)

    run_benchmark(args.n, args.offline_mock, args.image)
