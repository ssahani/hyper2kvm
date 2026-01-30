"""Windows Active Directory integration module.

Provides functionality for extracting domain membership information and
automating domain rejoin after VM migration.
"""

from .extractor import extract_domain_info, DomainInfo
from .rejoin import (
    stage_domain_rejoin_script,
    DomainRejoinMethod,
    get_rejoin_command,
)

__all__ = [
    "extract_domain_info",
    "DomainInfo",
    "stage_domain_rejoin_script",
    "DomainRejoinMethod",
    "get_rejoin_command",
]
