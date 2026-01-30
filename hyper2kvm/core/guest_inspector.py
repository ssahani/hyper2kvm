# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/guest_inspector.py
"""
Comprehensive guest OS inspection with mounting.

Extracts detailed information from disk images by mounting them:
- OS details (distribution, version, kernel)
- Network interfaces and MAC addresses
- IP configuration
- Installed packages
- Running services
- User accounts
- SSH configuration
- Disk usage
- Installed software
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

from .guestfs_factory import create_guestfs
GUESTFS_AVAILABLE = True  # Native implementation always available

from .guest_identity import GuestDetector, GuestIdentity, GuestType
from .utils import U


logger = logging.getLogger(__name__)


@dataclass
class NetworkInterface:
    """Network interface information."""
    name: str
    mac_address: str | None = None
    ip_addresses: list[str] = field(default_factory=list)
    type: str | None = None  # ethernet, wireless, bridge, etc.
    state: str | None = None  # up, down
    mtu: int | None = None
    driver: str | None = None


@dataclass
class InstalledPackage:
    """Installed package information."""
    name: str
    version: str | None = None
    architecture: str | None = None
    package_format: str | None = None  # rpm, deb, apk, etc.


@dataclass
class SystemdService:
    """Systemd service information."""
    name: str
    enabled: bool = False
    state: str | None = None  # active, inactive, failed
    preset: str | None = None


@dataclass
class UserAccount:
    """User account information."""
    username: str
    uid: int | None = None
    gid: int | None = None
    home: str | None = None
    shell: str | None = None
    comment: str | None = None


@dataclass
class DiskUsage:
    """Disk usage information."""
    filesystem: str
    mountpoint: str
    size_bytes: int
    used_bytes: int
    available_bytes: int
    use_percent: float


@dataclass
class Partition:
    """Partition information."""
    device: str
    number: int | None = None
    size_bytes: int | None = None
    filesystem_type: str | None = None
    label: str | None = None
    uuid: str | None = None
    bootable: bool = False


@dataclass
class Application:
    """Installed application (Windows) or package (Linux)."""
    name: str
    version: str | None = None
    vendor: str | None = None
    install_date: str | None = None
    install_location: str | None = None
    size_bytes: int | None = None


@dataclass
class FirewallRule:
    """Firewall rule information."""
    name: str
    enabled: bool = False
    direction: str | None = None  # inbound, outbound
    action: str | None = None  # allow, deny
    protocol: str | None = None
    port: str | None = None


@dataclass
class ScheduledTask:
    """Scheduled task or cron job."""
    name: str
    command: str | None = None
    schedule: str | None = None
    user: str | None = None
    enabled: bool = True


@dataclass
class GuestInspectionResult:
    """Complete guest inspection result."""

    # Basic identity (from existing GuestIdentity)
    identity: GuestIdentity | None = None

    # Network information
    network_interfaces: list[NetworkInterface] = field(default_factory=list)
    hostname: str | None = None
    dns_servers: list[str] = field(default_factory=list)

    # Packages
    installed_packages: list[InstalledPackage] = field(default_factory=list)
    package_count: int = 0
    package_format: str | None = None  # rpm, deb, apk, pacman

    # Services
    systemd_services: list[SystemdService] = field(default_factory=list)
    service_count: int = 0

    # Users
    user_accounts: list[UserAccount] = field(default_factory=list)
    user_count: int = 0

    # SSH
    ssh_authorized_keys: dict[str, list[str]] = field(default_factory=dict)
    ssh_host_keys: list[str] = field(default_factory=list)

    # Disk usage
    disk_usage: list[DiskUsage] = field(default_factory=list)

    # Partitions and filesystems
    partitions: list[Partition] = field(default_factory=list)
    filesystems: list[str] = field(default_factory=list)
    mount_points: dict[str, str] = field(default_factory=dict)  # device -> mount point

    # Applications (Windows) or detailed packages (Linux)
    applications: list[Application] = field(default_factory=list)
    application_count: int = 0

    # Firewall
    firewall_rules: list[FirewallRule] = field(default_factory=list)
    firewall_enabled: bool | None = None

    # Scheduled tasks
    scheduled_tasks: list[ScheduledTask] = field(default_factory=list)

    # Environment and configuration
    environment_variables: dict[str, str] = field(default_factory=dict)
    selinux_status: str | None = None  # enforcing, permissive, disabled

    # Additional metadata
    kernel_modules: list[str] = field(default_factory=list)
    boot_parameters: str | None = None
    timezone: str | None = None
    locale: str | None = None

    # Windows-specific
    windows_product_name: str | None = None
    windows_build_number: str | None = None
    windows_install_date: str | None = None

    # Raw metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class ComprehensiveGuestInspector:
    """
    Comprehensive guest OS inspector that mounts images and extracts detailed information.
    """

    def __init__(self, logger_instance: logging.Logger | None = None):
        """
        Initialize inspector.

        Args:
            logger_instance: Logger to use (creates new one if None)
        """
        self.logger = logger_instance or logger

    def inspect(
        self,
        img_path: str | Path,
        *,
        readonly: bool = True,
        network_info: bool = True,
        package_info: bool = True,
        service_info: bool = True,
        user_info: bool = True,
        ssh_info: bool = True,
        disk_info: bool = True,
    ) -> GuestInspectionResult:
        """
        Perform comprehensive guest inspection.

        Args:
            img_path: Path to disk image
            readonly: Mount read-only (recommended)
            network_info: Extract network interface information
            package_info: Extract installed package information
            service_info: Extract systemd service information
            user_info: Extract user account information
            ssh_info: Extract SSH configuration
            disk_info: Extract disk usage information

        Returns:
            Complete inspection result

        Raises:
            RuntimeError: If guestfs not available or inspection fails
        """
        if not GUESTFS_AVAILABLE:
            raise RuntimeError("libguestfs not available. Install: python3-guestfs")

        img_path = Path(img_path)
        if not img_path.exists():
            raise FileNotFoundError(f"Image not found: {img_path}")

        result = GuestInspectionResult()

        # First, use existing GuestDetector for basic identity
        self.logger.info(f"Inspecting guest image: {img_path}")
        result.identity = GuestDetector.detect(img_path, self.logger, readonly=readonly)

        if not result.identity:
            self.logger.warning("Could not detect guest identity")
            return result

        # Now mount and extract detailed information
        g = create_guestfs(python_return_dict=True, backend='native')

        try:
            g.add_drive_opts(str(img_path), readonly=1 if readonly else 0)
            g.launch()

            # Extract partition and filesystem information (before mounting)
            result.partitions = self._extract_partitions(g)
            result.filesystems = self._extract_filesystems(g)

            # Get root filesystem
            roots = g.inspect_os()
            if not roots:
                self.logger.warning("No operating systems found")
                return result

            root = roots[0]
            self.logger.debug(f"Inspecting root: {root}")

            # Mount the filesystem
            mounts = self._get_mount_points(g, root)
            result.mount_points = mounts
            for mp, dev in mounts.items():
                try:
                    g.mount_ro(dev, mp) if readonly else g.mount(dev, mp)
                    self.logger.debug(f"Mounted {dev} at {mp}")
                except Exception as e:
                    self.logger.warning(f"Failed to mount {dev} at {mp}: {e}")

            # Extract information based on OS type
            if result.identity.type == GuestType.LINUX:
                if network_info:
                    result.network_interfaces = self._extract_network_interfaces_linux(g)
                    result.hostname = self._extract_hostname_linux(g)
                    result.dns_servers = self._extract_dns_servers_linux(g)

                if package_info:
                    result.package_format = self._detect_package_format_linux(g)
                    result.installed_packages = self._extract_packages_linux(g, result.package_format)
                    result.package_count = len(result.installed_packages)

                if service_info:
                    result.systemd_services = self._extract_systemd_services_linux(g)
                    result.service_count = len(result.systemd_services)

                if user_info:
                    result.user_accounts = self._extract_users_linux(g)
                    result.user_count = len(result.user_accounts)

                if ssh_info:
                    result.ssh_authorized_keys = self._extract_ssh_keys_linux(g)
                    result.ssh_host_keys = self._extract_ssh_host_keys_linux(g)

                if disk_info:
                    result.disk_usage = self._extract_disk_usage_linux(g)

                # Additional Linux info
                result.kernel_modules = self._extract_kernel_modules_linux(g)
                result.boot_parameters = self._extract_boot_parameters_linux(g)
                result.timezone = self._extract_timezone_linux(g)
                result.locale = self._extract_locale_linux(g)

                # Extended Linux info (guestfish-like)
                result.scheduled_tasks = self._extract_cron_jobs_linux(g)
                result.firewall_rules = self._extract_firewall_rules_linux(g)
                result.selinux_status = self._extract_selinux_status_linux(g)
                result.environment_variables = self._extract_environment_linux(g)

            elif result.identity.type == GuestType.WINDOWS:
                # Windows info extraction
                if network_info:
                    result.network_interfaces = self._extract_network_interfaces_windows(g)
                    result.hostname = self._extract_hostname_windows(g)

                # Windows Registry-based extraction
                result.applications = self._extract_applications_windows(g)
                result.application_count = len(result.applications)

                result.windows_product_name = self._extract_windows_product_name(g)
                result.windows_build_number = self._extract_windows_build_number(g)
                result.windows_install_date = self._extract_windows_install_date(g)

                if user_info:
                    result.user_accounts = self._extract_users_windows(g)
                    result.user_count = len(result.user_accounts)

                result.scheduled_tasks = self._extract_scheduled_tasks_windows(g)
                result.firewall_rules = self._extract_firewall_rules_windows(g)
                result.environment_variables = self._extract_environment_windows(g)

        except Exception as e:
            self.logger.error(f"Inspection failed: {e}", exc_info=True)
            raise
        finally:
            try:
                g.umount_all()
                g.shutdown()
                g.close()
            except Exception:
                pass

        return result

    def _get_mount_points(self, g: guestfs.GuestFS, root: str) -> dict[str, str]:
        """Get mount points for root filesystem."""
        mounts = {}

        try:
            # Get mount points from inspection
            mp_dict = g.inspect_get_mountpoints(root)

            # Sort by mount point length (mount / before /boot, etc.)
            sorted_mps = sorted(mp_dict.items(), key=lambda x: len(x[0]))

            for mp, dev in sorted_mps:
                mounts[mp] = dev

        except Exception as e:
            self.logger.warning(f"Failed to get mount points: {e}")
            # Fallback: try to mount root
            mounts["/"] = root

        return mounts

    # Linux extraction methods

    def _extract_network_interfaces_linux(self, g: guestfs.GuestFS) -> list[NetworkInterface]:
        """Extract network interface information from Linux guest."""
        interfaces = []

        try:
            # Method 1: Parse /sys/class/net/
            if g.exists("/sys/class/net"):
                try:
                    iface_names = g.ls("/sys/class/net")

                    for iface in iface_names:
                        if iface in ("lo", "bonding_masters"):
                            continue

                        interface = NetworkInterface(name=iface)

                        # Get MAC address
                        mac_path = f"/sys/class/net/{iface}/address"
                        if g.exists(mac_path):
                            try:
                                mac = g.cat(mac_path).strip()
                                if mac and mac != "00:00:00:00:00:00":
                                    interface.mac_address = mac
                            except Exception:
                                pass

                        # Get interface type
                        type_path = f"/sys/class/net/{iface}/type"
                        if g.exists(type_path):
                            try:
                                iface_type = g.cat(type_path).strip()
                                # 1 = Ethernet, 772 = Loopback, 801 = WLAN
                                type_map = {"1": "ethernet", "772": "loopback", "801": "wireless"}
                                interface.type = type_map.get(iface_type, f"type-{iface_type}")
                            except Exception:
                                pass

                        # Get MTU
                        mtu_path = f"/sys/class/net/{iface}/mtu"
                        if g.exists(mtu_path):
                            try:
                                mtu = int(g.cat(mtu_path).strip())
                                interface.mtu = mtu
                            except Exception:
                                pass

                        # Get driver name
                        driver_path = f"/sys/class/net/{iface}/device/driver"
                        if g.exists(driver_path):
                            try:
                                driver_link = g.readlink(driver_path)
                                interface.driver = Path(driver_link).name
                            except Exception:
                                pass

                        interfaces.append(interface)

                except Exception as e:
                    self.logger.debug(f"Failed to parse /sys/class/net: {e}")

            # Method 2: Parse network configuration files
            self._enrich_interfaces_from_config(g, interfaces)

        except Exception as e:
            self.logger.warning(f"Failed to extract network interfaces: {e}")

        return interfaces

    def _enrich_interfaces_from_config(self, g: guestfs.GuestFS, interfaces: list[NetworkInterface]) -> None:
        """Enrich interface information from configuration files."""
        # Check various network configuration formats

        # systemd-networkd
        if g.exists("/etc/systemd/network"):
            try:
                for network_file in g.glob_expand("/etc/systemd/network/*.network"):
                    content = g.cat(network_file)                    # Parse .network file (INI format)
                    current_section = None
                    iface_pattern = None
                    iface_mac = None
                    dhcp_mode = None

                    for line in content.splitlines():
                        line = line.strip()
                        if not line or line.startswith(';') or line.startswith('#'):
                            continue

                        # Section headers
                        if line.startswith('[') and line.endswith(']'):
                            current_section = line[1:-1]
                            continue

                        # Parse key=value
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()

                            if current_section == 'Match':
                                if key == 'Name':
                                    iface_pattern = value
                                elif key == 'MACAddress':
                                    iface_mac = value
                            elif current_section == 'Network':
                                if key == 'DHCP':
                                    dhcp_mode = value

                    # Create interface from pattern (e.g., "e*" -> "eth0/ens33/etc")
                    if iface_pattern:
                        iface_name = iface_pattern.replace('*', '0')  # e* -> e0 as placeholder
                        interface = NetworkInterface(
                            name=f"{iface_name} ({iface_pattern})",
                            mac_address=iface_mac,
                            type="dhcp" if dhcp_mode else "static"
                        )
                        interfaces.append(interface)
            except Exception as e:
                self.logger.debug(f"Failed to parse systemd-networkd config: {e}")

        # NetworkManager connections
        if g.exists("/etc/NetworkManager/system-connections"):
            try:
                for conn_file in g.glob_expand("/etc/NetworkManager/system-connections/*"):
                    content = g.cat(conn_file)                    # Parse connection file for MAC and interface name
                    # TODO: Parse INI-style NetworkManager format
            except Exception:
                pass

        # Netplan
        if g.exists("/etc/netplan"):
            try:
                for netplan_file in g.glob_expand("/etc/netplan/*.yaml"):
                    content = g.cat(netplan_file)                    # TODO: Parse YAML netplan format
            except Exception:
                pass

        # ifcfg-rh style
        if g.exists("/etc/sysconfig/network-scripts"):
            try:
                for ifcfg_file in g.glob_expand("/etc/sysconfig/network-scripts/ifcfg-*"):
                    content = g.cat(ifcfg_file)                    # Parse HWADDR= lines
                    for line in content.splitlines():
                        if line.startswith("HWADDR="):
                            mac = line.split("=", 1)[1].strip().strip('"')
                            # Find matching interface
                            for iface in interfaces:
                                if iface.mac_address == mac:
                                    # Can extract IPADDR, NETMASK, etc.
                                    pass
            except Exception:
                pass

    def _extract_hostname_linux(self, g: guestfs.GuestFS) -> str | None:
        """Extract hostname from Linux guest."""
        try:
            # Try /etc/hostname first
            if g.exists("/etc/hostname"):
                hostname = g.cat("/etc/hostname").strip()
                if hostname:
                    return hostname

            # Try /etc/sysconfig/network (RHEL/CentOS)
            if g.exists("/etc/sysconfig/network"):
                content = g.cat("/etc/sysconfig/network")
                match = re.search(r'^HOSTNAME=(.+)$', content, re.MULTILINE)
                if match:
                    return match.group(1).strip().strip('"')

        except Exception as e:
            self.logger.debug(f"Failed to extract hostname: {e}")

        return None

    def _extract_dns_servers_linux(self, g: guestfs.GuestFS) -> list[str]:
        """Extract DNS server list from Linux guest."""
        dns_servers = []

        try:
            if g.exists("/etc/resolv.conf"):
                content = g.cat("/etc/resolv.conf")
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("nameserver "):
                        dns = line.split()[1]
                        dns_servers.append(dns)

        except Exception as e:
            self.logger.debug(f"Failed to extract DNS servers: {e}")

        return dns_servers

    def _detect_package_format_linux(self, g: guestfs.GuestFS) -> str | None:
        """Detect package format used by Linux distribution."""
        # Check for package databases
        if g.exists("/var/lib/rpm"):
            return "rpm"
        elif g.exists("/var/lib/dpkg"):
            return "deb"
        elif g.exists("/lib/apk/db"):
            return "apk"
        elif g.exists("/var/lib/pacman"):
            return "pacman"

        return None

    def _extract_packages_linux(self, g: guestfs.GuestFS, package_format: str | None) -> list[InstalledPackage]:
        """Extract installed package list (limited, as this can be very large)."""
        packages = []

        # We'll limit to first 100 packages to avoid huge output
        max_packages = 100

        try:
            if package_format == "rpm":
                # Parse RPM database
                # Note: This requires mounting and is complex, so we'll use a simple approach
                pass  # TODO: Implement RPM parsing

            elif package_format == "deb":
                # Parse dpkg status
                if g.exists("/var/lib/dpkg/status"):
                    content = g.cat("/var/lib/dpkg/status")
                    current_pkg = None

                    for line in content.splitlines():
                        if line.startswith("Package: "):
                            if current_pkg and len(packages) < max_packages:
                                packages.append(current_pkg)
                            current_pkg = InstalledPackage(
                                name=line.split(": ", 1)[1].strip(),
                                package_format="deb"
                            )
                        elif current_pkg:
                            if line.startswith("Version: "):
                                current_pkg.version = line.split(": ", 1)[1].strip()
                            elif line.startswith("Architecture: "):
                                current_pkg.architecture = line.split(": ", 1)[1].strip()

                        if len(packages) >= max_packages:
                            break

            elif package_format == "apk":
                # Parse APK database
                if g.exists("/lib/apk/db/installed"):
                    content = g.cat("/lib/apk/db/installed")
                    # TODO: Parse APK format

        except Exception as e:
            self.logger.warning(f"Failed to extract packages: {e}")

        return packages

    def _extract_systemd_services_linux(self, g: guestfs.GuestFS) -> list[SystemdService]:
        """Extract systemd service information."""
        services = []

        try:
            # Check for systemd
            if not g.exists("/etc/systemd/system") and not g.exists("/usr/lib/systemd/system"):
                return services

            # Get enabled services from /etc/systemd/system
            if g.exists("/etc/systemd/system"):
                for target_dir in g.glob_expand("/etc/systemd/system/*.target.wants"):
                    try:
                        for service_link in g.ls(target_dir):
                            if service_link.endswith(".service"):
                                service = SystemdService(
                                    name=service_link,
                                    enabled=True
                                )
                                services.append(service)
                    except Exception:
                        pass

        except Exception as e:
            self.logger.debug(f"Failed to extract systemd services: {e}")

        return services

    def _extract_users_linux(self, g: guestfs.GuestFS) -> list[UserAccount]:
        """Extract user account information."""
        users = []

        try:
            if g.exists("/etc/passwd"):
                content = g.cat("/etc/passwd")
                for line in content.splitlines():
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split(":")
                    if len(parts) >= 7:
                        user = UserAccount(
                            username=parts[0],
                            uid=int(parts[2]) if parts[2].isdigit() else None,
                            gid=int(parts[3]) if parts[3].isdigit() else None,
                            comment=parts[4],
                            home=parts[5],
                            shell=parts[6]
                        )
                        # Only include non-system users (UID >= 1000) and root
                        if user.uid == 0 or (user.uid and user.uid >= 1000):
                            users.append(user)

        except Exception as e:
            self.logger.debug(f"Failed to extract users: {e}")

        return users

    def _extract_ssh_keys_linux(self, g: guestfs.GuestFS) -> dict[str, list[str]]:
        """Extract SSH authorized keys for users."""
        ssh_keys = {}

        try:
            # Check /home/*/. ssh/authorized_keys
            for home_dir in g.glob_expand("/home/*"):
                username = Path(home_dir).name
                auth_keys_path = f"{home_dir}/.ssh/authorized_keys"

                if g.exists(auth_keys_path):
                    try:
                        content = g.cat(auth_keys_path)
                        keys = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
                        if keys:
                            ssh_keys[username] = keys
                    except Exception:
                        pass

            # Check root
            if g.exists("/root/.ssh/authorized_keys"):
                try:
                    content = g.cat("/root/.ssh/authorized_keys")
                    keys = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
                    if keys:
                        ssh_keys["root"] = keys
                except Exception:
                    pass

        except Exception as e:
            self.logger.debug(f"Failed to extract SSH keys: {e}")

        return ssh_keys

    def _extract_ssh_host_keys_linux(self, g: guestfs.GuestFS) -> list[str]:
        """Extract SSH host key fingerprints."""
        host_keys = []

        try:
            if g.exists("/etc/ssh"):
                for key_file in g.glob_expand("/etc/ssh/ssh_host_*_key.pub"):
                    try:
                        content = g.cat(key_file).strip()
                        if content:
                            host_keys.append(f"{Path(key_file).name}: {content[:80]}...")
                    except Exception:
                        pass

        except Exception as e:
            self.logger.debug(f"Failed to extract SSH host keys: {e}")

        return host_keys

    def _extract_disk_usage_linux(self, g: guestfs.GuestFS) -> list[DiskUsage]:
        """Extract disk usage information."""
        usage_info = []

        try:
            # Get filesystem info
            filesystems = g.list_filesystems()

            for dev, fs_type in filesystems.items():
                if fs_type in ("unknown", "swap"):
                    continue

                try:
                    statvfs = g.statvfs(dev)

                    size_bytes = statvfs["blocks"] * statvfs["bsize"]
                    available_bytes = statvfs["bavail"] * statvfs["bsize"]
                    used_bytes = size_bytes - (statvfs["bfree"] * statvfs["bsize"])
                    use_percent = (used_bytes / size_bytes * 100) if size_bytes > 0 else 0

                    usage = DiskUsage(
                        filesystem=dev,
                        mountpoint="/",  # We don't know actual mount point offline
                        size_bytes=size_bytes,
                        used_bytes=used_bytes,
                        available_bytes=available_bytes,
                        use_percent=use_percent
                    )
                    usage_info.append(usage)

                except Exception:
                    pass

        except Exception as e:
            self.logger.debug(f"Failed to extract disk usage: {e}")

        return usage_info

    def _extract_kernel_modules_linux(self, g: guestfs.GuestFS) -> list[str]:
        """Extract list of kernel modules."""
        modules = []

        try:
            if g.exists("/proc/modules"):
                content = g.cat("/proc/modules")
                for line in content.splitlines():
                    if line:
                        module_name = line.split()[0]
                        modules.append(module_name)

        except Exception as e:
            self.logger.debug(f"Failed to extract kernel modules: {e}")

        return modules[:50]  # Limit to first 50

    def _extract_boot_parameters_linux(self, g: guestfs.GuestFS) -> str | None:
        """Extract kernel boot parameters."""
        try:
            if g.exists("/proc/cmdline"):
                return g.cat("/proc/cmdline").strip()
        except Exception:
            pass

        return None

    def _extract_timezone_linux(self, g: guestfs.GuestFS) -> str | None:
        """Extract configured timezone."""
        try:
            if g.exists("/etc/timezone"):
                return g.cat("/etc/timezone").strip()

            # Check symlink /etc/localtime
            if g.exists("/etc/localtime"):
                try:
                    link = g.readlink("/etc/localtime")
                    if "/zoneinfo/" in link:
                        return link.split("/zoneinfo/", 1)[1]
                except Exception:
                    pass

        except Exception:
            pass

        return None

    def _extract_locale_linux(self, g: guestfs.GuestFS) -> str | None:
        """Extract configured locale."""
        try:
            if g.exists("/etc/locale.conf"):
                content = g.cat("/etc/locale.conf")
                match = re.search(r'^LANG=(.+)$', content, re.MULTILINE)
                if match:
                    return match.group(1).strip().strip('"')

            elif g.exists("/etc/default/locale"):
                content = g.cat("/etc/default/locale")
                match = re.search(r'^LANG=(.+)$', content, re.MULTILINE)
                if match:
                    return match.group(1).strip().strip('"')

        except Exception:
            pass

        return None

    # General extraction methods (both Linux and Windows)

    def _extract_partitions(self, g: guestfs.GuestFS) -> list[Partition]:
        """Extract partition information from disk."""
        partitions = []

        try:
            devices = g.list_devices()
            for device in devices:
                try:
                    # Get partitions for this device
                    parts = g.list_partitions()
                    for part in parts:
                        if not part.startswith(device):
                            continue

                        partition = Partition(device=part)

                        # Try to get partition number
                        try:
                            partition.number = g.part_to_partnum(part)
                        except Exception:
                            pass

                        # Try to get size
                        try:
                            partition.size_bytes = g.blockdev_getsize64(part)
                        except Exception:
                            pass

                        # Try to get filesystem type
                        try:
                            partition.filesystem_type = g.vfs_type(part)
                        except Exception:
                            pass

                        # Try to get label
                        try:
                            partition.label = g.vfs_label(part)
                        except Exception:
                            pass

                        # Try to get UUID
                        try:
                            partition.uuid = g.vfs_uuid(part)
                        except Exception:
                            pass

                        partitions.append(partition)
                except Exception as e:
                    self.logger.debug(f"Failed to get partitions for {device}: {e}")

        except Exception as e:
            self.logger.warning(f"Failed to extract partition information: {e}")

        return partitions

    def _extract_filesystems(self, g: guestfs.GuestFS) -> list[str]:
        """Extract list of filesystems."""
        filesystems = []

        try:
            parts = g.list_partitions()
            for part in parts:
                try:
                    fs_type = g.vfs_type(part)
                    if fs_type and fs_type not in filesystems:
                        filesystems.append(fs_type)
                except Exception:
                    pass
        except Exception as e:
            self.logger.debug(f"Failed to extract filesystems: {e}")

        return filesystems

    # Extended Linux extraction methods

    def _extract_cron_jobs_linux(self, g: guestfs.GuestFS) -> list[ScheduledTask]:
        """Extract cron jobs from Linux guest."""
        tasks = []

        try:
            # System crontabs
            for cron_file in ["/etc/crontab"]:
                if g.exists(cron_file):
                    try:
                        content = g.cat(cron_file)
                        for line in content.splitlines():
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue

                            # Parse cron format: minute hour day month dow user command
                            parts = line.split(None, 6)
                            if len(parts) >= 7:
                                task = ScheduledTask(
                                    name=f"cron: {parts[6][:50]}...",
                                    command=parts[6],
                                    schedule=f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[4]}",
                                    user=parts[5]
                                )
                                tasks.append(task)
                    except Exception:
                        pass

            # User crontabs in /var/spool/cron
            if g.exists("/var/spool/cron"):
                try:
                    cron_files = g.ls("/var/spool/cron")
                    for username in cron_files:
                        cron_path = f"/var/spool/cron/{username}"
                        if g.is_file(cron_path):
                            content = g.cat(cron_path)
                            for line in content.splitlines():
                                line = line.strip()
                                if not line or line.startswith("#"):
                                    continue

                                # Parse cron format: minute hour day month dow command
                                parts = line.split(None, 5)
                                if len(parts) >= 6:
                                    task = ScheduledTask(
                                        name=f"cron ({username}): {parts[5][:50]}...",
                                        command=parts[5],
                                        schedule=f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[4]}",
                                        user=username
                                    )
                                    tasks.append(task)
                except Exception:
                    pass

        except Exception as e:
            self.logger.debug(f"Failed to extract cron jobs: {e}")

        return tasks

    def _extract_firewall_rules_linux(self, g: guestfs.GuestFS) -> list[FirewallRule]:
        """Extract firewall rules from Linux guest."""
        rules = []

        try:
            # Try iptables-save output
            if g.exists("/etc/iptables/rules.v4"):
                try:
                    content = g.cat("/etc/iptables/rules.v4")
                    for line in content.splitlines():
                        line = line.strip()
                        if line.startswith("-A"):
                            # Parse iptables rule
                            rule = FirewallRule(
                                name=line[:60],
                                enabled=True,
                                direction="inbound" if "INPUT" in line else "outbound" if "OUTPUT" in line else "forward",
                                action="allow" if "ACCEPT" in line else "deny" if "DROP" in line or "REJECT" in line else None
                            )
                            rules.append(rule)
                except Exception:
                    pass

            # Try firewalld (RHEL/CentOS/Fedora)
            if g.exists("/etc/firewalld/zones"):
                try:
                    zones = g.ls("/etc/firewalld/zones")
                    for zone in zones:
                        if zone.endswith(".xml"):
                            zone_path = f"/etc/firewalld/zones/{zone}"
                            content = g.cat(zone_path)
                            # Basic XML parsing for services
                            import re
                            services = re.findall(r'<service name="([^"]+)"', content)
                            for service in services:
                                rule = FirewallRule(
                                    name=f"{zone}: {service}",
                                    enabled=True,
                                    action="allow"
                                )
                                rules.append(rule)
                except Exception:
                    pass

        except Exception as e:
            self.logger.debug(f"Failed to extract firewall rules: {e}")

        return rules

    def _extract_selinux_status_linux(self, g: guestfs.GuestFS) -> str | None:
        """Extract SELinux status."""
        try:
            if g.exists("/etc/selinux/config"):
                content = g.cat("/etc/selinux/config")
                match = re.search(r'^SELINUX=(.+)$', content, re.MULTILINE)
                if match:
                    return match.group(1).strip().lower()
        except Exception:
            pass

        return None

    def _extract_environment_linux(self, g: guestfs.GuestFS) -> dict[str, str]:
        """Extract system environment variables."""
        env_vars = {}

        try:
            # /etc/environment
            if g.exists("/etc/environment"):
                content = g.cat("/etc/environment")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue

                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"')

            # /etc/profile.d
            if g.exists("/etc/profile.d"):
                try:
                    profile_files = g.glob_expand("/etc/profile.d/*.sh")
                    for pfile in profile_files[:5]:  # Limit to first 5
                        content = g.cat(pfile)
                        # Look for export statements
                        for match in re.finditer(r'export\s+([A-Z_][A-Z0-9_]*)=(.+)', content):
                            key = match.group(1)
                            value = match.group(2).strip().strip('"').strip("'")
                            env_vars[key] = value
                except Exception:
                    pass

        except Exception as e:
            self.logger.debug(f"Failed to extract environment variables: {e}")

        return env_vars

    # Windows extraction methods

    def _extract_network_interfaces_windows(self, g: guestfs.GuestFS) -> list[NetworkInterface]:
        """Extract network interface information from Windows guest."""
        interfaces = []

        # Windows network config is in registry, which is complex to parse
        # For now, return empty list
        # TODO: Implement Windows registry parsing for network adapters
        # HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces

        return interfaces

    def _extract_hostname_windows(self, g: guestfs.GuestFS) -> str | None:
        """Extract hostname from Windows guest."""
        # Windows hostname is in registry
        # HKLM\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName
        # For now, return None
        # TODO: Implement Windows registry parsing

        return None

    def _extract_applications_windows(self, g: guestfs.GuestFS) -> list[Application]:
        """Extract installed applications from Windows registry."""
        applications = []

        # Windows applications are in:
        # HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
        # HKLM\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall (64-bit)
        # This requires parsing the Windows registry hives

        # For now, we'll add a note that this requires registry parsing
        # TODO: Implement using hivex library to parse SOFTWARE registry hive

        try:
            # Check if Windows Program Files directory exists
            if g.exists("/Program Files"):
                try:
                    programs = g.ls("/Program Files")
                    for program in programs[:50]:  # Limit to 50
                        app = Application(
                            name=program,
                            install_location=f"C:\\Program Files\\{program}"
                        )
                        applications.append(app)
                except Exception:
                    pass

            if g.exists("/Program Files (x86)"):
                try:
                    programs = g.ls("/Program Files (x86)")
                    for program in programs[:50]:  # Limit to 50
                        app = Application(
                            name=program,
                            install_location=f"C:\\Program Files (x86)\\{program}"
                        )
                        applications.append(app)
                except Exception:
                    pass
        except Exception as e:
            self.logger.debug(f"Failed to extract Windows applications: {e}")

        return applications

    def _extract_windows_product_name(self, g: guestfs.GuestFS) -> str | None:
        """Extract Windows product name."""
        # Stored in registry: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProductName
        # TODO: Implement registry parsing
        return None

    def _extract_windows_build_number(self, g: guestfs.GuestFS) -> str | None:
        """Extract Windows build number."""
        # Stored in registry: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\CurrentBuildNumber
        # TODO: Implement registry parsing
        return None

    def _extract_windows_install_date(self, g: guestfs.GuestFS) -> str | None:
        """Extract Windows installation date."""
        # Stored in registry: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\InstallDate
        # TODO: Implement registry parsing
        return None

    def _extract_users_windows(self, g: guestfs.GuestFS) -> list[UserAccount]:
        """Extract user accounts from Windows."""
        users = []

        # Windows users are in SAM registry hive
        # For now, check for user profile directories
        try:
            if g.exists("/Users"):
                user_dirs = g.ls("/Users")
                for username in user_dirs:
                    if username not in ("Public", "Default", "Default User", "All Users"):
                        user = UserAccount(
                            username=username,
                            home=f"C:\\Users\\{username}"
                        )
                        users.append(user)
        except Exception as e:
            self.logger.debug(f"Failed to extract Windows users: {e}")

        return users

    def _extract_scheduled_tasks_windows(self, g: guestfs.GuestFS) -> list[ScheduledTask]:
        """Extract Windows scheduled tasks."""
        tasks = []

        # Windows scheduled tasks are in C:\Windows\System32\Tasks
        try:
            if g.exists("/Windows/System32/Tasks"):
                task_files = g.find("/Windows/System32/Tasks")
                for task_path in task_files[:20]:  # Limit to 20
                    if g.is_file(task_path):
                        task_name = task_path.replace("/Windows/System32/Tasks/", "")
                        task = ScheduledTask(
                            name=task_name,
                            command=None  # Would need to parse XML
                        )
                        tasks.append(task)
        except Exception as e:
            self.logger.debug(f"Failed to extract Windows scheduled tasks: {e}")

        return tasks

    def _extract_firewall_rules_windows(self, g: guestfs.GuestFS) -> list[FirewallRule]:
        """Extract Windows firewall rules."""
        rules = []

        # Windows Firewall rules are in registry
        # HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy
        # TODO: Implement registry parsing

        return rules

    def _extract_environment_windows(self, g: guestfs.GuestFS) -> dict[str, str]:
        """Extract Windows environment variables."""
        env_vars = {}

        # Windows environment variables are in registry
        # HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment
        # TODO: Implement registry parsing

        return env_vars
