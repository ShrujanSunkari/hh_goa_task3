# Security Policy

## Secret Management
Secrets are loaded via `.env` and never committed to the repository. We recommend using a fresh API key for testing and ensuring that `.env` is listed in your `.gitignore`.

## Blockchain Security & Privacy
The pipeline uses SHA-256 hashing of the payload. Only the resulting hash is stored on-chain, preserving the privacy of the biometric data and original image.

## Tamper-Evidence
On-chain verification compares the local hash against the stored hash, mathematically proving the immutability of the record. Any alteration to the original data will result in a mismatched hash, indicating tampering.
