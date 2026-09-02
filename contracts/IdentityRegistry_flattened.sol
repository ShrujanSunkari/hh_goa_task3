// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// File: @openzeppelin/contracts/access/IAccessControl.sol

/**
 * @dev External interface of AccessControl declared to support ERC-165 detection.
 */
interface IAccessControl {
    error AccessControlUnauthorizedAccount(address account, bytes32 neededRole);
    error AccessControlBadConfirmation();

    event RoleAdminChanged(bytes32 indexed role, bytes32 indexed previousAdminRole, bytes32 indexed newAdminRole);
    event RoleGranted(bytes32 indexed role, address indexed account, address indexed sender);
    event RoleRevoked(bytes32 indexed role, address indexed account, address indexed sender);

    function hasRole(bytes32 role, address account) external view returns (bool);
    function getRoleAdmin(bytes32 role) external view returns (bytes32);
    function grantRole(bytes32 role, address account) external;
    function revokeRole(bytes32 role, address account) external;
    function renounceRole(bytes32 role, address callerConfirmation) external;
}

// File: @openzeppelin/contracts/utils/Context.sol

abstract contract Context {
    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }

    function _msgData() internal view virtual returns (bytes calldata) {
        return msg.data;
    }

    function _contextSuffixLength() internal view virtual returns (uint256) {
        return 0;
    }
}

// File: @openzeppelin/contracts/utils/introspection/IERC165.sol

interface IERC165 {
    function supportsInterface(bytes4 interfaceId) external view returns (bool);
}

// File: @openzeppelin/contracts/utils/introspection/ERC165.sol

abstract contract ERC165 is IERC165 {
    function supportsInterface(bytes4 interfaceId) public view virtual returns (bool) {
        return interfaceId == type(IERC165).interfaceId;
    }
}

// File: @openzeppelin/contracts/access/AccessControl.sol

abstract contract AccessControl is Context, IAccessControl, ERC165 {
    struct RoleData {
        mapping(address account => bool) hasRole;
        bytes32 adminRole;
    }

    mapping(bytes32 role => RoleData) private _roles;

    bytes32 public constant DEFAULT_ADMIN_ROLE = 0x00;

    modifier onlyRole(bytes32 role) {
        _checkRole(role);
        _;
    }

    function supportsInterface(bytes4 interfaceId) public view virtual override returns (bool) {
        return interfaceId == type(IAccessControl).interfaceId || super.supportsInterface(interfaceId);
    }

    function hasRole(bytes32 role, address account) public view virtual returns (bool) {
        return _roles[role].hasRole[account];
    }

    function _checkRole(bytes32 role) internal view virtual {
        _checkRole(role, _msgSender());
    }

    function _checkRole(bytes32 role, address account) internal view virtual {
        if (!hasRole(role, account)) {
            revert AccessControlUnauthorizedAccount(account, role);
        }
    }

    function getRoleAdmin(bytes32 role) public view virtual returns (bytes32) {
        return _roles[role].adminRole;
    }

    function grantRole(bytes32 role, address account) public virtual onlyRole(getRoleAdmin(role)) {
        _grantRole(role, account);
    }

    function revokeRole(bytes32 role, address account) public virtual onlyRole(getRoleAdmin(role)) {
        _revokeRole(role, account);
    }

    function renounceRole(bytes32 role, address callerConfirmation) public virtual {
        if (callerConfirmation != _msgSender()) {
            revert AccessControlBadConfirmation();
        }
        _revokeRole(role, callerConfirmation);
    }

    function _setRoleAdmin(bytes32 role, bytes32 adminRole) internal virtual {
        bytes32 previousAdminRole = getRoleAdmin(role);
        _roles[role].adminRole = adminRole;
        emit RoleAdminChanged(role, previousAdminRole, adminRole);
    }

    function _grantRole(bytes32 role, address account) internal virtual returns (bool) {
        if (!hasRole(role, account)) {
            _roles[role].hasRole[account] = true;
            emit RoleGranted(role, account, _msgSender());
            return true;
        } else {
            return false;
        }
    }

    function _revokeRole(bytes32 role, address account) internal virtual returns (bool) {
        if (hasRole(role, account)) {
            _roles[role].hasRole[account] = false;
            emit RoleRevoked(role, account, _msgSender());
            return true;
        } else {
            return false;
        }
    }
}

// File: IdentityRegistry.sol

/**
 * @title  IdentityRegistry
 * @notice Immutable on-chain ledger anchoring face-identification results.
 *
 *  Each record is keyed by a bytes32 SHA-256 fingerprint of the matched
 *  social payload (embedding + source URL).  Duplicate submissions are
 *  rejected, making the ledger append-only and tamper-evident.
 *
 *  Confidence is stored in basis-points (0 - 10 000) so uint16 suffices
 *  and no floating-point conversions are needed on-chain.
 */
contract IdentityRegistry is AccessControl {

    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    constructor() {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(REGISTRAR_ROLE, msg.sender);
    }

    function grantRegistrarRole(address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        grantRole(REGISTRAR_ROLE, account);
    }

    struct Record {
        bytes32 dataHash;
        string  sourceUrl;
        uint16  confidenceBps;
        uint256 timestamp;
        bool    exists;
        string  metadataURI;
    }

    mapping(bytes32 => Record) public records;

    event RecordRegistered(
        bytes32 indexed dataHash,
        string          sourceUrl,
        uint16          confidenceBps,
        uint256         timestamp
    );

    function registerRecord(
        bytes32        dataHash,
        string calldata sourceUrl,
        uint16         confidenceBps,
        string calldata metadataURI
    ) external onlyRole(REGISTRAR_ROLE) {
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

    function batchRegister(
        bytes32[] calldata dataHashes,
        string[] calldata sourceUrls,
        uint16[] calldata confidenceBpsArray,
        string[] calldata metadataURIs
    ) external onlyRole(REGISTRAR_ROLE) {
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
                continue;
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

    function verifyRecord(bytes32 dataHash)
        external
        view
        returns (
            bool    exists,
            string  memory sourceUrl,
            uint16  confidenceBps,
            uint256 timestamp,
            string  memory metadataURI
        )
    {
        Record storage r = records[dataHash];
        return (r.exists, r.sourceUrl, r.confidenceBps, r.timestamp, r.metadataURI);
    }
}
