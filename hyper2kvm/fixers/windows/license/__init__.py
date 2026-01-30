"""Windows license management module.

Provides functionality for extracting and preserving Windows license information
during VM migration, including product keys, activation state, and license type.
"""

from .extractor import (
    extract_license_info,
    decode_product_key,
    detect_license_type,
    LicenseInfo,
    LicenseType,
)

__all__ = [
    "extract_license_info",
    "decode_product_key",
    "detect_license_type",
    "LicenseInfo",
    "LicenseType",
]
