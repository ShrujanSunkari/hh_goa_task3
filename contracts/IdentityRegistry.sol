// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

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
contract IdentityRegistry is Ownable {

    constructor() Ownable(msg.sender) {}

    // ─────────────────────────────────────────────────────────────────────────
    //  Types
    // ─────────────────────────────────────────────────────────────────────────

    struct Record {
        bytes32 dataHash;       // SHA-256 of (embedding || sourceUrl)
        string  sourceUrl;      // URL of the identified social post / page
        uint16  confidenceBps;  // match confidence, 0-10 000  (÷100 = %)
        uint256 timestamp;      // block.timestamp at registration time
        bool    exists;         // guard against duplicate registration
        string  metadataURI;    // metadata URI
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
     * @param sourceUrl     URL of the identified social content.
     * @param confidenceBps Detection/search confidence in basis-points.
     * @param timestamp     Block timestamp at registration.
     */
    event RecordRegistered(
        bytes32 indexed dataHash,
        string          sourceUrl,
        uint16          confidenceBps,
        uint256         timestamp
    );

    // ─────────────────────────────────────────────────────────────────────────
    //  External functions
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Anchor a new face-identification result on-chain.
     *
     * @param dataHash      bytes32 SHA-256 of the detection payload.
     * @param sourceUrl     Social post URL returned by the OSINT step.
     * @param confidenceBps Confidence score in basis-points (0 – 10 000).
     *
     * Reverts if:
     *   - `records[dataHash].exists` is already true  (duplicate).
     *   - `confidenceBps` exceeds 10 000.
     *   - `dataHash` is zero (likely a programming error in the caller).
     */
    function registerRecord(
        bytes32        dataHash,
        string calldata sourceUrl,
        uint16         confidenceBps,
        string calldata metadataURI
    ) external onlyOwner {
        require(dataHash != bytes32(0),            "IdentityRegistry: zero dataHash");
        require(!records[dataHash].exists,          "IdentityRegistry: duplicate record");
        require(confidenceBps <= 10_000,            "IdentityRegistry: confidenceBps > 100%");

        uint256 ts = block.timestamp;

        records[dataHash] = Record({
            dataHash:      dataHash,
            sourceUrl:     sourceUrl,
            confidenceBps: confidenceBps,
            timestamp:     ts,
            exists:        true,
            metadataURI:   metadataURI
        });

        emit RecordRegistered(dataHash, sourceUrl, confidenceBps, ts);
    }

    /**
     * @notice Anchor multiple face-identification results on-chain in a single transaction.
     */
    function batchRegister(
        bytes32[] calldata dataHashes,
        string[] calldata sourceUrls,
        uint16[] calldata confidenceBpsArray,
        string[] calldata metadataURIs
    ) external onlyOwner {
        require(
            dataHashes.length == sourceUrls.length &&
            dataHashes.length == confidenceBpsArray.length &&
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
                dataHash:      dataHash,
                sourceUrl:     sourceUrls[i],
                confidenceBps: confidenceBpsArray[i],
                timestamp:     ts,
                exists:        true,
                metadataURI:   metadataURIs[i]
            });

            emit RecordRegistered(dataHash, sourceUrls[i], confidenceBpsArray[i], ts);
        }
    }

    /**
     * @notice Look up a previously registered record.
     *
     * @param  dataHash  The bytes32 key to query.
     * @return exists        Whether a record with this hash has been registered.
     * @return sourceUrl     The social URL stored at registration time.
     * @return confidenceBps Confidence score in basis-points.
     * @return timestamp     Block timestamp at registration.
     */
    function verifyRecord(bytes32 dataHash)
        external
        view
        returns (
            bool    exists,
            string  memory sourceUrl,
            uint16  confidenceBps,
            uint256 timestamp
        )
    {
        Record storage r = records[dataHash];
        return (r.exists, r.sourceUrl, r.confidenceBps, r.timestamp);
    }
}
