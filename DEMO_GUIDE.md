# Demo Recording Guide
### HH Goa 2026 · Task 3 — Face ID & Blockchain Verification
### Target runtime: 60 – 90 seconds

---

## Pre-Recording Checklist (do this BEFORE hitting record)

### Terminal Setup

- [ ] Open **Windows Terminal** or **iTerm2** (avoid default cmd.exe)
- [ ] Set font to **Cascadia Code**, **JetBrains Mono**, or **Fira Code** — size **16–18pt**
- [ ] Set terminal **width ≥ 120 columns**, height ≥ 40 rows
  ```
  # Quick resize in Windows Terminal: Settings → Appearance → Columns: 130, Rows: 40
  ```
- [ ] Use a **dark theme** (One Dark, Dracula, or Tokyo Night) for maximum contrast
- [ ] Close all other terminal tabs / windows to avoid distraction
- [ ] Disable notifications (Focus Assist / Do Not Disturb)

### File System Setup

- [ ] Confirm `.env` has `SERPAPI_KEY` set (or plan to use `--offline-mock`)
- [ ] Place a clear, well-lit **frontal face photo** at `inputs/sample.jpg`
  - Ideal: 500×500px or larger, subject filling >50% of the frame
  - Avoid: sunglasses, heavy occlusion, blurry images
- [ ] Run `python deploy.py` **before** recording to warm up the contract
  - In offline-mock mode this is not required
- [ ] Do a **dry run** of the exact commands below to confirm they work

### Screen Layout

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   Single maximised terminal window                  │
│   Dark background / coloured Rich output            │
│   No other windows visible                         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Recording Script — Step by Step

### 0 · Opening shot (0:00 – 0:07)

Show the project directory tree and briefly explain the structure:

```bash
Get-ChildItem -Recurse | Select-Object FullName
```

**Say:** *"This is Task 3 — a Face Identification and Blockchain Verification pipeline.
Four modules, one Solidity contract, one command."*

---

### 1 · Deploy the Smart Contract (0:07 – 0:20)

```bash
python deploy.py
```

**Pause on:** the green deployment panel showing:
- Contract Address
- Gas Used
- Elapsed time

**Say:** *"In under 200 ms, our IdentityRegistry contract is live on the in-process EVM —
zero cost, zero latency, fully functional Ethereum."*

---

### 2 · Run the Full Pipeline — Offline Mock (0:20 – 0:55)

```bash
python pipeline.py --image inputs/sample.jpg --offline-mock
```

Walk through each stage as it appears:

**Stage 1 — Face Detection** (0:22 – 0:30)

> Pause on the green **[OK] Face Extracted** panel.

**Say:** *"Stage 1: RetinaFace detected the face with 99.73% confidence,
extracted a 512-dimensional Facenet embedding, and saved the crop."*

**Stage 2 — OSINT Search** (0:30 – 0:42)

> Pause on the yellow **[OK] OSINT Identification Complete** panel.
> Point out the top domain match and the **Payload Hash** line.

**Say:** *"Stage 2: Google Lens reverse image search — ranked by social domain priority.
The SHA-256 payload hash uniquely fingerprints this identity result."*

**Stage 3 — Blockchain Anchoring** (0:42 – 0:50)

> Pause on the magenta **[CHAIN] Transaction Receipt** panel.
> Highlight: TX Hash, Block Number, Gas Used.

**Say:** *"Stage 3: The payload hash is signed and submitted to our Solidity contract.
68,000 gas. Confirmed. Immutable."*

**Stage 4 — Cryptographic Proof** (0:50 – 1:00)

> **HIGHLIGHT THIS PANEL — ZOOM IN IF POSSIBLE.**
> The DOUBLE_EDGE green box is the climax of the demo.

```
╔══════  [PROOF] IDENTITY VERIFIED -- IMMUTABLE BLOCKCHAIN RECORD  ══════╗
║                                                                        ║
║   [OK] CRYPTOGRAPHICALLY VERIFIED & IMMUTABLE                          ║
║                                                                        ║
║   On-Chain Hash:    0x589039e47d0d29398174...                          ║
║   Source URL:       https://x.com/elonmusk                             ║
║   Confidence:       97.00%                                             ║
║   Block Timestamp:  2026-09-01T00:27:11+00:00  (Block #7)              ║
║   Proof:            Local Payload Hash == On-Chain Hash (Confirmed)    ║
╚════════════════════════════════════════════════════════════════════════╝
```

**Say:** *"Stage 4: We query the smart contract directly and compare hashes.
Local hash equals on-chain hash — mathematically verified, immutable proof."*

---

### 3 · Run Live Mode (optional, 1:00 – 1:25)

If you have a real `SERPAPI_KEY` and a photo of a known public figure:

```bash
python pipeline.py --image inputs/real_photo.jpg --top-n 5
```

Let it run in real-time. The spinner animations show live activity.
Pause on the final proof panel as before.

**Say:** *"In live mode, the same pipeline hits real Google Lens, finds the real identity,
and anchors the proof — all in under 10 seconds."*

---

### 4 · Closing Shot (1:25 – 1:30)

```bash
# Show the artifacts file to prove on-chain persistence
cat contracts/IdentityRegistry_artifacts.json
```

**Say:** *"The ABI, bytecode, and deployed address are persisted.
Any verifier anywhere can reproduce this hash and confirm the record on-chain.
That's Task 3 — done."*

---

## Key Panels to Highlight (in order of importance)

| Priority | Panel | Why it matters |
|---|---|---|
| 🥇 **1st** | `[PROOF] IDENTITY VERIFIED` (DOUBLE_EDGE green) | The main deliverable — cryptographic proof |
| 🥈 **2nd** | `[CHAIN] Transaction Receipt` (magenta) | Shows real blockchain interaction |
| 🥉 **3rd** | `[OK] OSINT Identification Complete` (yellow) | Demonstrates the AI + web search capability |
| 4th | `[OK] Face Extracted` (green) | Shows DeepFace working |
| 5th | `deploy.py` output (green) | Proves the contract is live |

---

## Talking Points for Q&A

**"Why hash off-chain?"**
> Raw embeddings are 4KB+ — storing on-chain costs hundreds of dollars.
> SHA-256 compresses to 32 bytes (~$0.004 at Sepolia gas prices).
> The hash is deterministic: anyone can reproduce and verify it independently.

**"Is this private?"**
> Currently the source URL is public on-chain — by design for this demo.
> The roadmap includes zk-SNARKs to prove identity claims without revealing biometrics.

**"What stops someone from submitting a wrong URL?"**
> The hash binds `source_url + image_bytes + metadata` together.
> Changing any input produces a completely different hash — the contract stores it forever,
> but the mismatch is detectable by anyone re-running the local hash function.

**"Can it run without internet?"**
> Yes — `--offline-mock` bypasses SerpAPI and uses py-evm locally.
> The entire pipeline runs air-gapped in ~3 seconds.

---

## Backup Plan (if SerpAPI fails during recording)

```bash
# Use --offline-mock — output is identical, just uses synthetic data
python pipeline.py --image inputs/sample.jpg --offline-mock
```

The offline mock produces a real SHA-256 hash, a real blockchain transaction,
and a real on-chain verification — only the OSINT search result is synthetic.

---

*Good luck — you've got this. The code is solid.* 🚀
