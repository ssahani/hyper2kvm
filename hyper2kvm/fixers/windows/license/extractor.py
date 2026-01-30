"""Windows license information extraction.

Extracts Windows product keys, license type, and activation state from
offline registry hives for preservation during VM migration.
"""

import logging
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class LicenseType(Enum):
    """Windows license types."""

    RETAIL = "Retail"
    OEM = "OEM"
    MAK = "MAK"  # Multiple Activation Key
    KMS = "KMS"  # Key Management Service
    VOLUME = "Volume"
    UNKNOWN = "Unknown"


@dataclass
class LicenseInfo:
    """Windows license information."""

    product_key: Optional[str] = None
    license_type: LicenseType = LicenseType.UNKNOWN
    product_id: Optional[str] = None
    kms_server: Optional[str] = None
    kms_port: Optional[int] = None
    activation_status: Optional[str] = None
    licensed_product_name: Optional[str] = None
    edition: Optional[str] = None
    is_activated: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "product_key": self.product_key,
            "license_type": self.license_type.value,
            "product_id": self.product_id,
            "kms_server": self.kms_server,
            "kms_port": self.kms_port,
            "activation_status": self.activation_status,
            "licensed_product_name": self.licensed_product_name,
            "edition": self.edition,
            "is_activated": self.is_activated,
        }


def extract_license_info(guestfs, root: str) -> LicenseInfo:
    """Extract Windows license information from offline registry.

    Args:
        guestfs: GuestFS instance with mounted filesystem
        root: Root path of Windows installation

    Returns:
        LicenseInfo object with extracted license data

    Raises:
        RuntimeError: If registry hives cannot be accessed
    """
    import tempfile
    from pathlib import Path
    from ..registry.io import download_and_open_hive, detect_windows_hive

    logger.info("Extracting Windows license information")

    license_info = LicenseInfo()

    try:
        # Locate SOFTWARE hive
        software_path = detect_windows_hive(guestfs, root, "SOFTWARE")
        if not software_path:
            logger.warning("SOFTWARE hive not found")
            return license_info

        # Download and open hive
        from ..registry.encoding import _close_best_effort

        with tempfile.TemporaryDirectory() as tmpdir:
            local_hive = Path(tmpdir) / "SOFTWARE"
            hive = download_and_open_hive(logger, guestfs, software_path, local_hive, write=False)

            try:
                # Extract license data from registry
                license_data = _read_license_registry_values(hive)

                # Decode product key
                license_info.product_key = decode_product_key(license_data)

                # Extract product ID
                license_info.product_id = license_data.get("ProductId")

                # Extract edition
                license_info.edition = license_data.get("EditionID")
                license_info.licensed_product_name = license_data.get("ProductName")

                # Detect license type
                license_info.license_type = detect_license_type(license_data)

                # Extract KMS information if applicable
                if license_info.license_type == LicenseType.KMS:
                    license_info.kms_server = license_data.get("KeyManagementServiceName")
                    kms_port_str = license_data.get("KeyManagementServicePort")
                    if kms_port_str:
                        try:
                            license_info.kms_port = int(kms_port_str)
                        except (ValueError, TypeError):
                            license_info.kms_port = 1688  # Default KMS port

                # Determine activation status
                license_info.activation_status = _determine_activation_status(license_data)
                license_info.is_activated = license_info.activation_status == "Licensed"

                logger.info(
                    f"Extracted license info: type={license_info.license_type.value}, "
                    f"edition={license_info.edition}, activated={license_info.is_activated}"
                )
            finally:
                _close_best_effort(hive)

    except Exception as e:
        logger.error(f"Failed to extract license information: {e}")
        logger.debug("License extraction error", exc_info=True)

    return license_info


def _read_license_registry_values(hive) -> dict:
    """Read license-related registry values from SOFTWARE hive.

    Args:
        hive: Opened SOFTWARE registry hive

    Returns:
        Dictionary of extracted registry values
    """
    from ..registry.encoding import read_registry_value

    keys_to_read = {
        # Windows 8+ encrypted product key
        "DigitalProductId4": r"Microsoft\Windows NT\CurrentVersion",
        # Windows 7 and earlier product key
        "DigitalProductId": r"Microsoft\Windows NT\CurrentVersion",
        # Product ID
        "ProductId": r"Microsoft\Windows NT\CurrentVersion",
        # Edition information
        "EditionID": r"Microsoft\Windows NT\CurrentVersion",
        "ProductName": r"Microsoft\Windows NT\CurrentVersion",
        # KMS information
        "KeyManagementServiceName": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        "KeyManagementServicePort": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        # Activation information (limited offline access)
        "VLActivationInterval": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        "VLRenewalInterval": r"Microsoft\Windows NT\CurrentVersion\SoftwareProtectionPlatform",
        # License channel
        "Channel": r"Microsoft\Windows NT\CurrentVersion",
    }

    license_data = {}

    for value_name, key_path in keys_to_read.items():
        try:
            value = read_registry_value(hive, key_path, value_name)
            if value is not None:
                license_data[value_name] = value
        except Exception as e:
            logger.debug(f"Could not read {key_path}\\{value_name}: {e}")
            continue

    return license_data


def decode_product_key(license_data: dict) -> Optional[str]:
    """Decode Windows product key from DigitalProductId.

    Implements Microsoft's product key encoding algorithm for both
    Windows 7 (DigitalProductId) and Windows 8+ (DigitalProductId4).

    Args:
        license_data: Dictionary containing DigitalProductId binary data

    Returns:
        Formatted product key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX) or None

    Note:
        Windows 8+ uses a different encoding scheme than Windows 7.
        This function handles both variants.
    """
    # Try Windows 8+ format first
    dpid4 = license_data.get("DigitalProductId4")
    if dpid4:
        try:
            return _decode_dpid4(dpid4)
        except Exception as e:
            logger.debug(f"Failed to decode DigitalProductId4: {e}")

    # Fall back to Windows 7 format
    dpid = license_data.get("DigitalProductId")
    if dpid:
        try:
            return _decode_dpid(dpid)
        except Exception as e:
            logger.debug(f"Failed to decode DigitalProductId: {e}")

    return None


def _decode_dpid4(dpid_bytes: bytes) -> str:
    """Decode Windows 8+ DigitalProductId4.

    Windows 8+ uses a modified base-24 encoding with a 3-byte header.

    Args:
        dpid_bytes: Binary DigitalProductId4 data

    Returns:
        Formatted 25-character product key
    """
    if len(dpid_bytes) < 0x328:  # Minimum required size
        raise ValueError("DigitalProductId4 too short")

    # Key data starts at offset 0x328 (808 decimal)
    key_offset = 0x328
    key_length = 15  # 15 bytes encode to 25 characters

    if len(dpid_bytes) < key_offset + key_length:
        raise ValueError("DigitalProductId4 truncated")

    # Extract key bytes
    key_bytes = bytearray(dpid_bytes[key_offset : key_offset + key_length])

    # Character set for base-24 encoding (Windows 8+ variant)
    chars = "BCDFGHJKMPQRTVWXY2346789"

    # Windows 8+ includes an 'N' check digit
    # Byte at offset 0x8 (8) indicates if 'N' should be injected
    contains_n = (dpid_bytes[key_offset + 8] >> 3) & 1

    decoded_chars = []

    # Decode 25 characters
    for i in range(25):
        char_index = 0

        # Process bytes in reverse
        for j in range(14, -1, -1):
            char_index = (char_index << 8) | key_bytes[j]
            key_bytes[j] = char_index // 24
            char_index %= 24

        decoded_chars.append(chars[char_index])

    # Reverse to get correct order
    decoded_chars.reverse()

    # Insert 'N' if required (Windows 8+ retail vs OEM indicator)
    if contains_n:
        n_pos = (dpid_bytes[key_offset + 8] & 0x07) % 24
        decoded_chars.insert(n_pos, 'N')

    product_key = ''.join(decoded_chars)

    # Format as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
    return _format_product_key(product_key)


def _decode_dpid(dpid_bytes: bytes) -> str:
    """Decode Windows 7 and earlier DigitalProductId.

    Windows 7 uses standard base-24 encoding starting at offset 52.

    Args:
        dpid_bytes: Binary DigitalProductId data

    Returns:
        Formatted 25-character product key
    """
    if len(dpid_bytes) < 67:  # Minimum: 52 offset + 15 bytes
        raise ValueError("DigitalProductId too short")

    # Key data starts at offset 52
    key_offset = 52
    key_length = 15

    if len(dpid_bytes) < key_offset + key_length:
        raise ValueError("DigitalProductId truncated")

    # Extract key bytes
    key_bytes = bytearray(dpid_bytes[key_offset : key_offset + key_length])

    # Character set for base-24 encoding (Windows 7 variant)
    chars = "BCDFGHJKMPQRTVWXY2346789"

    decoded_chars = []

    # Decode 25 characters
    for i in range(25):
        char_index = 0

        # Process bytes in reverse
        for j in range(14, -1, -1):
            char_index = (char_index << 8) | key_bytes[j]
            key_bytes[j] = char_index // 24
            char_index %= 24

        decoded_chars.append(chars[char_index])

    # Reverse to get correct order
    decoded_chars.reverse()

    product_key = ''.join(decoded_chars)

    # Format as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
    return _format_product_key(product_key)


def _format_product_key(key: str) -> str:
    """Format product key with dashes.

    Args:
        key: 25-character product key

    Returns:
        Formatted key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX)
    """
    if len(key) != 25:
        # Pad or truncate to 25 characters
        key = key.ljust(25, 'X')[:25]

    return f"{key[0:5]}-{key[5:10]}-{key[10:15]}-{key[15:20]}-{key[20:25]}"


def detect_license_type(license_data: dict) -> LicenseType:
    """Detect Windows license type from registry data.

    Args:
        license_data: Dictionary of registry values

    Returns:
        Detected LicenseType
    """
    # Check for KMS activation
    if license_data.get("KeyManagementServiceName"):
        return LicenseType.KMS

    # Check channel indicator (Windows 10+)
    channel = license_data.get("Channel", "").lower()
    if "retail" in channel:
        return LicenseType.RETAIL
    if "oem" in channel:
        return LicenseType.OEM
    if "volume" in channel:
        return LicenseType.VOLUME

    # Check for Volume Licensing indicators
    if license_data.get("VLActivationInterval") or license_data.get("VLRenewalInterval"):
        # Could be MAK or KMS
        if license_data.get("KeyManagementServiceName"):
            return LicenseType.KMS
        return LicenseType.MAK

    # Check Product ID format for OEM indicator
    product_id = license_data.get("ProductId", "")
    if product_id:
        # OEM product IDs typically have different patterns
        # Format: XXXXX-OEM-XXXXXXX-XXXXX or similar
        if "OEM" in product_id.upper():
            return LicenseType.OEM

    # Default to unknown
    return LicenseType.UNKNOWN


def _determine_activation_status(license_data: dict) -> str:
    """Determine activation status from registry data.

    Note: Full activation status requires online SPP service access.
    This provides a best-effort offline approximation.

    Args:
        license_data: Dictionary of registry values

    Returns:
        Activation status string
    """
    # KMS licenses are typically activated if server is configured
    if license_data.get("KeyManagementServiceName"):
        return "Licensed (KMS)"

    # Check for volume licensing intervals (indicates activation)
    if license_data.get("VLActivationInterval"):
        return "Licensed (Volume)"

    # Without online SPP access, we can't definitively determine status
    return "Unknown (Offline)"
