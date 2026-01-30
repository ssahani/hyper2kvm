"""Active Directory membership information extraction.

Extracts domain membership metadata from offline Windows registry for
preservation and automated domain rejoin after VM migration.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DomainInfo:
    """Active Directory domain membership information."""

    is_domain_joined: bool = False
    domain_name: Optional[str] = None
    computer_name: Optional[str] = None
    dns_domain: Optional[str] = None
    last_dc: Optional[str] = None
    workgroup: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "is_domain_joined": self.is_domain_joined,
            "domain_name": self.domain_name,
            "computer_name": self.computer_name,
            "dns_domain": self.dns_domain,
            "last_dc": self.last_dc,
            "workgroup": self.workgroup,
        }


def extract_domain_info(guestfs, root: str) -> DomainInfo:
    """Extract Active Directory membership information from offline registry.

    Args:
        guestfs: GuestFS instance with mounted filesystem
        root: Root path of Windows installation

    Returns:
        DomainInfo object with extracted domain data

    Raises:
        RuntimeError: If registry hives cannot be accessed
    """
    from ..registry.io import download_and_open_hive
    from ..virtio.paths import detect_windows_hive

    logger.info("Extracting Active Directory domain information")

    domain_info = DomainInfo()

    try:
        # Locate SYSTEM hive for computer name and domain info
        system_path = detect_windows_hive(guestfs, root, "SYSTEM")
        if not system_path:
            logger.warning("SYSTEM hive not found")
            return domain_info

        system_hive = download_and_open_hive(guestfs, system_path)

        # Determine current control set
        from ..registry.encoding import read_registry_value

        try:
            current_cs = read_registry_value(
                system_hive, "Select", "Current", default=1
            )
            controlset = f"ControlSet{current_cs:03d}"
        except Exception:
            controlset = "ControlSet001"  # Default

        logger.debug(f"Using {controlset} for domain info extraction")

        # Extract computer name
        computer_name_path = f"{controlset}\\Control\\ComputerName\\ComputerName"
        try:
            domain_info.computer_name = read_registry_value(
                system_hive, computer_name_path, "ComputerName"
            )
            logger.debug(f"Computer name: {domain_info.computer_name}")
        except Exception as e:
            logger.debug(f"Could not read computer name: {e}")

        # Extract domain/workgroup information
        tcpip_params_path = f"{controlset}\\Services\\Tcpip\\Parameters"
        try:
            # Check for domain membership
            domain = read_registry_value(system_hive, tcpip_params_path, "Domain")
            if domain:
                domain_info.domain_name = domain
                domain_info.is_domain_joined = True
                logger.info(f"Domain-joined: {domain}")
            else:
                # Not domain-joined, check workgroup
                workgroup = read_registry_value(
                    system_hive, tcpip_params_path, "NV Domain"
                )
                if workgroup:
                    domain_info.workgroup = workgroup
                    logger.info(f"Workgroup: {workgroup}")
        except Exception as e:
            logger.debug(f"Could not read domain/workgroup: {e}")

        # Try to get DNS domain (more reliable for domain-joined systems)
        try:
            dns_domain = read_registry_value(
                system_hive, tcpip_params_path, "DhcpDomain"
            )
            if not dns_domain:
                dns_domain = read_registry_value(
                    system_hive, tcpip_params_path, "Domain"
                )

            if dns_domain and dns_domain != domain_info.workgroup:
                domain_info.dns_domain = dns_domain
                logger.debug(f"DNS domain: {dns_domain}")
        except Exception as e:
            logger.debug(f"Could not read DNS domain: {e}")

        # Try SOFTWARE hive for Group Policy information (contains DC info)
        try:
            software_path = detect_windows_hive(guestfs, root, "SOFTWARE")
            if software_path:
                software_hive = download_and_open_hive(guestfs, software_path)

                # Extract last known domain controller from Group Policy history
                gp_history_path = r"Microsoft\Windows\CurrentVersion\Group Policy\History"
                try:
                    dc_name = read_registry_value(
                        software_hive, gp_history_path, "DCName"
                    )
                    if dc_name:
                        domain_info.last_dc = dc_name
                        logger.debug(f"Last DC: {dc_name}")
                except Exception as e:
                    logger.debug(f"Could not read DC name: {e}")

                # Verify DNS domain from GP history if not found earlier
                if not domain_info.dns_domain:
                    try:
                        network_name = read_registry_value(
                            software_hive, gp_history_path, "NetworkName"
                        )
                        if network_name:
                            domain_info.dns_domain = network_name
                            logger.debug(f"DNS domain from GP: {network_name}")
                    except Exception as e:
                        logger.debug(f"Could not read GP network name: {e}")

        except Exception as e:
            logger.debug(f"Could not access SOFTWARE hive for GP info: {e}")

        # Final determination of domain join status
        if domain_info.domain_name and domain_info.dns_domain:
            domain_info.is_domain_joined = True
        elif domain_info.workgroup:
            domain_info.is_domain_joined = False

        logger.info(
            f"Domain info extracted: domain_joined={domain_info.is_domain_joined}, "
            f"domain={domain_info.domain_name or domain_info.workgroup}"
        )

    except Exception as e:
        logger.error(f"Failed to extract domain information: {e}")
        logger.debug("Domain extraction error", exc_info=True)

    return domain_info
