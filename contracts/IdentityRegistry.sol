// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title  IdentityRegistry
 * @notice Immutable on-chain ledger anchoring face-identification results.
 *
 *  Each record is keyed by a bytes32 SHA-256 fingerprint of the matched
 *  social payload (embedding + source URL).  Duplicate submissions are
 *  rejected, making the ledger append-only and tamper-evident.
 *
 *  Confidence is stored in basis-points (0 – 10 000) so uint16 suffices
 *  and no floating-point conversions are needed on-chain.
 */
contract IdentityRegistry is AccessControl {

    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    constructor() {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(REGISTRAR_ROLE, msg.sender);
    }

    /**
     * @notice Grants the REGISTRAR_ROLE to a new account.
     * @param account The address to receive the role.
     */
    function grantRegistrarRole(address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        grantRole(REGISTRAR_ROLE, account);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Types
    // ─────────────────────────────────────────────────────────────────────────

    struct Record {
        bytes32 dataHash;       // SHA-256 of (embedding || sourceUrl)
        bool    isDemoMode;     // If true, sourceUrl and confidenceBps are stored in plaintext
        string  sourceUrl;      // Plaintext URL (if demo) or empty (if privacy)
        uint16  confidenceBps;  // Plaintext confidence (if demo) or 0 (if privacy)
        bytes32 payloadCommitment; // keccak256(sourceUrl, confidenceBps) if privacy mode
        uint256 timestamp;      // block.timestamp at registration time
        bool    exists;         // guard against duplicate registration
        string  metadataURI;    // metadata URI (IPFS)
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  State
    // ─────────────────────────────────────────────────────────────────────────

    /// @notice Primary record store, keyed by dataHash.
    mapping(bytes32 => Record) public records;

    // ─────────────────────────────────────────────────────────────────────────
    //  Events
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Emitted every time a new record is anchored.
     * @param dataHash      SHA-256 fingerprint of the payload.
     * @param isDemoMode    Whether the record is stored in plaintext demo mode.
     * @param timestamp     Block timestamp at registration.
     */
    event RecordRegistered(
        bytes32 indexed dataHash,
        bool            isDemoMode,
        uint256         timestamp
    );

    // ─────────────────────────────────────────────────────────────────────────
    //  External functions
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Anchor a new face-identification result on-chain.
     *
     * @param dataHash      bytes32 SHA-256 of the detection payload.
     * @param isDemoMode    True if storing plaintext, false if storing hashes.
     * @param sourceUrl     Social post URL (empty if privacy mode).
     * @param confidenceBps Confidence score (0 if privacy mode).
     * @param payloadCommitment Cryptographic commitment of the payload (0x0 if demo).
     * @param metadataURI   Off-chain pointer (e.g. IPFS) for encrypted metadata.
     *
     * Reverts if:
     *   - `records[dataHash].exists` is already true  (duplicate).
     *   - `confidenceBps` exceeds 10 000.
     *   - `dataHash` is zero.
     */
    function registerRecord(
        bytes32        dataHash,
        bool           isDemoMode,
        string calldata sourceUrl,
        uint16         confidenceBps,
        bytes32        payloadCommitment,
        string calldata metadataURI
    ) external onlyRole(REGISTRAR_ROLE) {
        require(dataHash != bytes32(0),            "IdentityRegistry: zero dataHash");
        require(!records[dataHash].exists,          "IdentityRegistry: duplicate record");
        require(confidenceBps <= 10_000,            "IdentityRegistry: confidenceBps > 100%");

        uint256 ts = block.timestamp;

        records[dataHash] = Record({
            dataHash:          dataHash,
            isDemoMode:        isDemoMode,
            sourceUrl:         sourceUrl,
            confidenceBps:     confidenceBps,
            payloadCommitment: payloadCommitment,
            timestamp:         ts,
            exists:            true,
            metadataURI:       metadataURI
        });

        emit RecordRegistered(dataHash, isDemoMode, ts);
    }

    /**
     * @notice Anchor multiple face-identification results on-chain in a single transaction.
     */
    function batchRegister(
        bytes32[] calldata dataHashes,
        bool[] calldata isDemoModes,
        string[] calldata sourceUrls,
        uint16[] calldata confidenceBpsArray,
        bytes32[] calldata payloadCommitments,
        string[] calldata metadataURIs
    ) external onlyRole(REGISTRAR_ROLE) {
        require(
            dataHashes.length == isDemoModes.length &&
            dataHashes.length == sourceUrls.length &&
            dataHashes.length == confidenceBpsArray.length &&
            dataHashes.length == payloadCommitments.length &&
            dataHashes.length == metadataURIs.length,
            "IdentityRegistry: arrays length mismatch"
        );

        for (uint256 i = 0; i < dataHashes.length; i++) {
            bytes32 dataHash = dataHashes[i];
            require(dataHash != bytes32(0), "IdentityRegistry: zero dataHash");
            if (records[dataHash].exists) {
                continue; // skip duplicates in batch
            }
            require(confidenceBpsArray[i] <= 10_000, "IdentityRegistry: confidenceBps > 100%");

            uint256 ts = block.timestamp;

            records[dataHash] = Record({
                dataHash:          dataHash,
                isDemoMode:        isDemoModes[i],
                sourceUrl:         sourceUrls[i],
                confidenceBps:     confidenceBpsArray[i],
                payloadCommitment: payloadCommitments[i],
                timestamp:         ts,
                exists:            true,
                metadataURI:       metadataURIs[i]
            });

            emit RecordRegistered(dataHash, isDemoModes[i], ts);
        }
    }

    /**
     * @notice Look up a previously registered record.
     *
     * @param  dataHash  The bytes32 key to query.
     * @return exists        Whether a record with this hash has been registered.
     * @return isDemoMode    Whether the record is stored in plaintext demo mode.
     * @return sourceUrl     The social URL (if demo mode).
     * @return confidenceBps Confidence score (if demo mode).
     * @return payloadCommitment The hash commitment (if privacy mode).
     * @return timestamp     Block timestamp at registration.
     * @return metadataURI   Off-chain pointer to encrypted data.
     */
    function verifyRecord(bytes32 dataHash)
        external
        view
        returns (
            bool    exists,
            bool    isDemoMode,
            string  memory sourceUrl,
            uint16  confidenceBps,
            bytes32 payloadCommitment,
            uint256 timestamp,
            string  memory metadataURI
        )
    {
        Record storage r = records[dataHash];
        return (r.exists, r.isDemoMode, r.sourceUrl, r.confidenceBps, r.payloadCommitment, r.timestamp, r.metadataURI);
    }
}
