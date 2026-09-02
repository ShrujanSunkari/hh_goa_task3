#!/usr/bin/env python3
import os
import json
import shutil
import subprocess
from rich.console import Console

console = Console()


def run_cmd(cmd, description):
    console.print(f"[bold cyan]>[/bold cyan] {description}")
    console.print(f"  [dim]{' '.join(cmd)}[/dim]")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Command '{cmd[0]}' not found.")
        console.print(
            "This script requires [bold]circom[/bold] (Rust) and [bold]snarkjs[/bold] (Node.js)."
        )
        console.print(
            "Please ensure they are installed or run this in a Docker/WSL environment with Rust."
        )
        exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during execution:[/bold red]\n{e.stderr}")
        exit(1)


def main():
    console.print("[bold green]Zero-Knowledge Biometric Commitment Demo[/bold green]\n")

    # 1. Create a mock embedding (512-d array of integers for the circuit)
    # In reality, ArcFace floats are scaled to integers (e.g. multiplied by 10^6).
    embedding = [123456] * 512

    input_data = {"embedding": embedding}

    os.makedirs("proofs", exist_ok=True)
    input_file = "proofs/input.json"

    with open(input_file, "w") as f:
        json.dump(input_data, f)

    console.print(f"Created mock input with 512-d embedding at {input_file}")

    circuit_path = "circuits/embedding_commitment.circom"
    if not os.path.exists(circuit_path):
        console.print(
            f"[bold red]Error:[/bold red] Circuit not found at {circuit_path}"
        )
        exit(1)

    # Check if circom is installed
    if not shutil.which("circom"):
        console.print("\n[bold yellow]Environment Warning:[/bold yellow]")
        console.print(
            "The [bold]circom[/bold] compiler is not installed on this system."
        )
        console.print(
            "To run this ZK-SNARK demo end-to-end, you need the Rust toolchain to compile circom."
        )
        console.print("\nThe following steps *would* be executed:")
        console.print(
            "  1. Compile circuit: [dim]circom circuits/embedding_commitment.circom --r1cs --wasm --sym -o proofs/[/dim]"
        )
        console.print(
            "  2. Generate witness: [dim]node proofs/embedding_commitment_js/generate_witness.js proofs/embedding_commitment_js/embedding_commitment.wasm proofs/input.json proofs/witness.wtns[/dim]"
        )
        console.print(
            "  3. Trusted Setup (PTAU): [dim]snarkjs powersoftau new bn128 12 proofs/pot12_0000.ptau -v[/dim]"
        )
        console.print(
            "  4. Setup (ZKey): [dim]snarkjs groth16 setup proofs/embedding_commitment.r1cs proofs/pot12_0000.ptau proofs/circuit_0000.zkey[/dim]"
        )
        console.print(
            "  5. Generate Proof: [dim]snarkjs groth16 prove proofs/circuit_0000.zkey proofs/witness.wtns proofs/proof.json proofs/public.json[/dim]"
        )
        console.print(
            "  6. Verify Proof: [dim]snarkjs groth16 verify proofs/verification_key.json proofs/public.json proofs/proof.json[/dim]"
        )
        console.print(
            "\nAborting local execution. Please migrate this script to a Linux/WSL environment to run."
        )
        exit(0)

    # 2. Compile Circuit
    run_cmd(
        ["circom", circuit_path, "--r1cs", "--wasm", "--sym", "-o", "proofs/"],
        "Compiling Circom circuit...",
    )

    # 3. Generate Witness
    run_cmd(
        [
            "node",
            "proofs/embedding_commitment_js/generate_witness.js",
            "proofs/embedding_commitment_js/embedding_commitment.wasm",
            "proofs/input.json",
            "proofs/witness.wtns",
        ],
        "Generating witness...",
    )

    # 4. Dummy Trusted Setup (Powers of Tau)
    # WARNING: Do NOT use a local dummy setup in production!
    run_cmd(
        [
            "snarkjs",
            "powersoftau",
            "new",
            "bn128",
            "12",
            "proofs/pot12_0000.ptau",
            "-v",
        ],
        "Starting Powers of Tau (Dummy Setup)...",
    )
    run_cmd(
        [
            "snarkjs",
            "powersoftau",
            "contribute",
            "proofs/pot12_0000.ptau",
            "proofs/pot12_0001.ptau",
            "--name=First",
            "-v",
            "-e=dummy_entropy",
        ],
        "Contributing to Phase 1...",
    )
    run_cmd(
        [
            "snarkjs",
            "powersoftau",
            "prepare",
            "phase2",
            "proofs/pot12_0001.ptau",
            "proofs/pot12_final.ptau",
            "-v",
        ],
        "Preparing Phase 2...",
    )

    # 5. Circuit-Specific Setup
    run_cmd(
        [
            "snarkjs",
            "groth16",
            "setup",
            "proofs/embedding_commitment.r1cs",
            "proofs/pot12_final.ptau",
            "proofs/circuit_0000.zkey",
        ],
        "Running Groth16 Setup...",
    )
    run_cmd(
        [
            "snarkjs",
            "zkey",
            "contribute",
            "proofs/circuit_0000.zkey",
            "proofs/circuit_final.zkey",
            "--name=Second",
            "-v",
            "-e=dummy_entropy",
        ],
        "Contributing to ZKey...",
    )
    run_cmd(
        [
            "snarkjs",
            "zkey",
            "export",
            "verificationkey",
            "proofs/circuit_final.zkey",
            "proofs/verification_key.json",
        ],
        "Exporting Verification Key...",
    )

    # 6. Generate Proof
    run_cmd(
        [
            "snarkjs",
            "groth16",
            "prove",
            "proofs/circuit_final.zkey",
            "proofs/witness.wtns",
            "proofs/proof.json",
            "proofs/public.json",
        ],
        "Generating Groth16 Proof...",
    )

    # 7. Verify Proof
    run_cmd(
        [
            "snarkjs",
            "groth16",
            "verify",
            "proofs/verification_key.json",
            "proofs/public.json",
            "proofs/proof.json",
        ],
        "Verifying Proof locally...",
    )

    console.print(
        "\n[bold green]✅ Success![/bold green] Proof generated and verified successfully."
    )
    console.print("The `proofs/public.json` contains the public commitment hash.")
    console.print("The `proofs/proof.json` contains the zk-SNARK proof.")


if __name__ == "__main__":
    main()
