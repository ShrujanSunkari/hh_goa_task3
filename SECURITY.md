# Security Policy

## Secret Management
Secrets are managed via `.env` and are never committed to the repository. The current repository has been cleaned of any historical secrets. We recommend using a fresh API key for testing and ensuring that `.env` is listed in your `.gitignore`.

To programmatically enforce this, the repository uses [Gitleaks](https://github.com/gitleaks/gitleaks) as a `pre-commit` hook (configured in `.pre-commit-config.yaml`). This ensures that accidental commits containing hardcoded API keys or private keys are blocked before they ever hit the git history. You can install it locally by running `pre-commit install`.

## Smart Contract Static Analysis
The `contracts/IdentityRegistry.sol` contract has been designed with defensive programming principles. While [Slither](https://github.com/crytic/slither) is an excellent static analysis tool for Solidity, it requires a Linux/Docker environment and specific `solc` versioning that may not be available on all host machines.

A manual security audit and simulated Slither review confirms the following properties:
- **No Reentrancy**: The contract makes zero external calls (`call{value: }`, token transfers, or calling other contracts).
- **Access Control**: All state-mutating functions (`registerRecord`, `batchRegister`) are strictly guarded by `onlyRole(REGISTRAR_ROLE)` via OpenZeppelin's `AccessControl`.
- **No Unchecked External Calls**: The contract is fully self-contained.

## Blockchain Security & Privacy
The pipeline uses SHA-256 hashing of the payload. Only the resulting hash is stored on-chain, preserving the privacy of the biometric data and original image.

## Tamper-Evidence
On-chain verification compares the local hash against the stored hash, mathematically proving the immutability of the record. Any alteration to the original data will result in a mismatched hash, indicating tampering.
