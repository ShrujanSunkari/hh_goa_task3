# HH Goa 2026 - Task 3 Submission Checklist

Use this checklist for a 60-second sanity check before submitting to the judges.

## Core Hackathon Requirements

- [x] **"Build a pipeline that takes a face scan as input."**
  - **Evidence:** `pipeline.py` (CLI entry point). `modules/face_detector.py` integrates DeepFace/ArcFace to extract 512-d L2-normalized biometric embeddings (`FaceDetector.detect_and_crop`).
  - **Fallback:** OpenCV Haar Cascade (128-d fallback) remains for strict offline environments.

- [x] **"Perform a genuine web/social media search to find a matching post (no hardcoded results)."**
  - **Evidence:** `modules/web_search.py` performs a live `requests.post` to SerpAPI Google Lens (`WebSearchEngine.search_by_image`). It falls back to Bing and Yandex, parses live JSON responses, and uses priority-domain scoring to rank matches dynamically.
  - **Test:** `tests/test_web_search.py` proves this logic using `pytest` without hardcoding outputs in the core module.

- [x] **"Upload a hash/fingerprint of the discovered data to a blockchain..."**
  - **Evidence:** `modules/blockchain.py` computes a `hashlib.sha256()` fingerprint of `(source_url || thumbnail_bytes || metadata)` and calls `registerRecord` on the `IdentityRegistry.sol` smart contract via Web3.py.
  - **Live Proof:** Check `scripts/anchor_demo_record.py` and `README.md` for the live Sepolia transaction hash.

- [x] **"...and re-verify it on-chain."**
  - **Evidence:** Stage 4 in `pipeline.py` calls `BlockchainAnchor.verify_record(payload_hash)`, which queries the contract and strictly asserts `require(exists)` and `Local Hash == On-Chain Hash`.

- [x] **"Provide a GitHub repository with a README covering setup, blockchain used, and known limitations."**
  - **Evidence:** `README.md` includes explicit sections for **Quickstart Guide** (setup), **Live on Sepolia** / **Blockchain Security Model** (blockchain used), and **Engineering Maturity & Known Limitations** (rate limits, gas, privacy).

- [x] **"No website required; focus on the pipeline."**
  - **Evidence:** Done. The UX is delivered via a beautifully styled `rich` CLI interface rather than a web frontend.

## Advanced & Differentiating Features

- [x] **Security Hardening**: `.github/workflows/ci.yml` runs `pip-audit`. Dependabot is configured. Pre-commit hooks (`gitleaks`) are configured to block secrets. `IdentityRegistry.sol` mitigates reentrancy by design.
- [x] **Performance Benchmarks**: Documented end-to-end timing statistics using `scripts/benchmark.py`.
- [x] **ZK-SNARK Prototype**: `circuits/embedding_commitment.circom` and `scripts/zk_commit_demo.py` provide a concrete path toward fully private biometric commitments.

## Final Submission Actions
1. **GitHub Link:** Verify repository visibility is Public.
2. **Screen Recording:** Record a 2-3 minute video walking through `DEMO_GUIDE.md` and upload it as required.

Good luck! You've built a robust, verified, and beautifully engineered pipeline.
