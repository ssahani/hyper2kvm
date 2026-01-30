# Systemd Integration Proposal - VMCraft v9.2

**Proposal Date:** January 26, 2026
**Target Release:** VMCraft v9.2
**Estimated Effort:** 3-4 weeks
**Priority:** HIGH (Critical for modern Linux migrations)

---

## Executive Summary

This proposal outlines comprehensive systemd integration for VMCraft, adding 50+ new APIs across 4 major categories to enable enterprise-grade Linux system management during VM migrations. Systemd is the de facto init system for modern Linux distributions (RHEL, Fedora, Ubuntu, Debian, SUSE), making this integration critical for production migrations.

**Key Benefits:**
- 🔧 **Service Management:** Control systemd services during migration (start, stop, enable, disable)
- 🌐 **Network Configuration:** Manage systemd-networkd configurations for consistent networking
- 📝 **Unit File Management:** Create, modify, and validate systemd unit files
- 📊 **Boot Analysis:** Analyze boot performance and critical path services
- 🔍 **Journal Integration:** Query and analyze systemd journal logs
- ⏰ **Timer Support:** Manage systemd timers for scheduled tasks
- 🚀 **Boot Optimization:** Identify and disable unnecessary services

---

## Motivation

### Current Gaps

VMCraft currently has limited systemd support:
- ✅ Basic service enable/disable via `systemctl` commands
- ✅ Network manager detection (systemd-networkd vs NetworkManager)
- ❌ **No structured systemd unit file manipulation**
- ❌ **No systemd-networkd configuration management**
- ❌ **No journal query APIs**
- ❌ **No boot analysis capabilities**
- ❌ **No timer/target management**

### Migration Pain Points

**Real-world migration scenarios that require systemd integration:**

1. **Network Configuration Migration**
   - Problem: VMs migrated from VMware often have VMware-specific network configs
   - Solution: Generate proper systemd-networkd `.network` files for KVM environment

2. **Service Dependency Management**
   - Problem: Services fail on first boot due to missing dependencies or wrong ordering
   - Solution: Analyze systemd dependencies and fix ordering issues before migration

3. **Boot Performance**
   - Problem: Migrated VMs boot slowly due to unnecessary services
   - Solution: Identify and disable non-critical services using systemd-analyze

4. **Logging Consistency**
   - Problem: Migration events scattered across multiple log files
   - Solution: Integrate with systemd journal for centralized, structured logging

5. **Automated Maintenance**
   - Problem: Post-migration tasks require manual intervention
   - Solution: Create systemd timers for automated cleanup and validation

### Target Users

- 🏢 **Enterprise Linux Administrators** migrating RHEL/Fedora VMs
- 🔧 **DevOps Engineers** automating large-scale migrations
- ☁️ **Cloud Architects** building hybrid cloud infrastructure
- 🐧 **Linux Distribution Maintainers** creating migration tooling

---

## Proposed Architecture

### New Module Structure

```
hyper2kvm/core/vmcraft/
├── systemd_mgr.py              # NEW: Core systemd management (400 lines)
├── systemd_networkd.py         # NEW: Network configuration (350 lines)
├── systemd_journal.py          # NEW: Journal integration (300 lines)
├── systemd_units.py            # NEW: Unit file management (450 lines)
└── main.py                     # MODIFIED: Add systemd wrappers (50+ methods)

tests/unit/test_core/
├── test_vmcraft_systemd_mgr.py         # NEW: 25 tests
├── test_vmcraft_systemd_networkd.py    # NEW: 20 tests
├── test_vmcraft_systemd_journal.py     # NEW: 18 tests
└── test_vmcraft_systemd_units.py       # NEW: 22 tests
```

---

## Phase 1: Core Systemd Service Management (Week 1)

### APIs (15 methods)

**File:** `hyper2kvm/core/vmcraft/systemd_mgr.py`

```python
class SystemdManager:
    """Core systemd service and unit management."""

    # Service Control (6 methods)
    def service_start(self, service: str) -> dict[str, Any]:
        """Start systemd service."""

    def service_stop(self, service: str) -> dict[str, Any]:
        """Stop systemd service."""

    def service_restart(self, service: str) -> dict[str, Any]:
        """Restart systemd service."""

    def service_enable(self, service: str) -> dict[str, Any]:
        """Enable service to start at boot."""

    def service_disable(self, service: str) -> dict[str, Any]:
        """Disable service from starting at boot."""

    def service_status(self, service: str) -> dict[str, Any]:
        """Get detailed service status."""

    # Bulk Operations (3 methods)
    def services_enable_multiple(self, services: list[str]) -> dict[str, bool]:
        """Enable multiple services at once."""

    def services_disable_multiple(self, services: list[str]) -> dict[str, bool]:
        """Disable multiple services at once."""

    def services_mask(self, services: list[str]) -> dict[str, bool]:
        """Mask services to prevent activation."""

    # Query/Analysis (6 methods)
    def list_services(self, state: str | None = None) -> list[dict[str, Any]]:
        """List all systemd services with optional state filter.

        Args:
            state: Filter by state (active, inactive, failed, enabled, disabled)

        Returns:
            List of service info dicts with keys:
            - name: Service name
            - load: Load state (loaded, not-found)
            - active: Active state (active, inactive, failed)
            - sub: Sub-state (running, dead, exited)
            - description: Service description
        """

    def list_failed_services(self) -> list[str]:
        """List services in failed state."""

    def get_service_dependencies(self, service: str) -> dict[str, list[str]]:
        """Get service dependencies (Requires, Wants, After, Before)."""

    def daemon_reload(self) -> dict[str, Any]:
        """Reload systemd manager configuration."""

    def systemctl_preset(self, service: str) -> dict[str, Any]:
        """Apply distribution preset for service."""

    def is_systemd_available(self) -> bool:
        """Check if systemd is available in guest."""
```

### Implementation Example

```python
# hyper2kvm/core/vmcraft/systemd_mgr.py
import logging
from pathlib import Path
from typing import Any

class SystemdManager:
    """Systemd service and unit management."""

    def __init__(self, logger: logging.Logger, guest_root: str):
        self.logger = logger
        self.guest_root = Path(guest_root)
        self._systemd_available: bool | None = None

    def is_systemd_available(self) -> bool:
        """Check if systemd is available in guest."""
        if self._systemd_available is not None:
            return self._systemd_available

        # Check for systemd binary
        systemd_bin = self.guest_root / "usr/lib/systemd/systemd"
        alt_systemd_bin = self.guest_root / "lib/systemd/systemd"

        self._systemd_available = systemd_bin.exists() or alt_systemd_bin.exists()
        return self._systemd_available

    def service_enable(self, service: str) -> dict[str, Any]:
        """Enable service to start at boot."""
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "service": service,
            "action": "enable"
        }

        if not self.is_systemd_available():
            audit["error"] = "systemd_not_available"
            return audit

        audit["attempted"] = True

        try:
            # Use systemctl with chroot
            from hyper2kvm.core.vmcraft._utils import run_sudo

            cmd = ["systemd-nspawn", "-D", str(self.guest_root),
                   "--quiet", "systemctl", "enable", service]

            run_sudo(self.logger, cmd, check=True, capture=True)

            audit["ok"] = True
            self.logger.info(f"Enabled systemd service: {service}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            self.logger.warning(f"Failed to enable service {service}: {e}")
            return audit

    def list_services(self, state: str | None = None) -> list[dict[str, Any]]:
        """List all systemd services with optional state filter."""
        if not self.is_systemd_available():
            return []

        try:
            from hyper2kvm.core.vmcraft._utils import run_sudo

            cmd = ["systemd-nspawn", "-D", str(self.guest_root),
                   "--quiet", "systemctl", "list-units", "--type=service",
                   "--all", "--no-pager", "--no-legend"]

            if state:
                cmd.append(f"--state={state}")

            result = run_sudo(self.logger, cmd, check=True, capture=True,
                            failure_log_level=logging.DEBUG)

            services = []
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue

                parts = line.split(None, 4)
                if len(parts) >= 5:
                    services.append({
                        "name": parts[0],
                        "load": parts[1],
                        "active": parts[2],
                        "sub": parts[3],
                        "description": parts[4]
                    })

            return services

        except Exception as e:
            self.logger.debug(f"Failed to list services: {e}")
            return []

    def get_service_dependencies(self, service: str) -> dict[str, list[str]]:
        """Get service dependencies."""
        deps = {
            "requires": [],
            "wants": [],
            "after": [],
            "before": []
        }

        if not self.is_systemd_available():
            return deps

        try:
            from hyper2kvm.core.vmcraft._utils import run_sudo

            cmd = ["systemd-nspawn", "-D", str(self.guest_root),
                   "--quiet", "systemctl", "show", service,
                   "--property=Requires,Wants,After,Before", "--no-pager"]

            result = run_sudo(self.logger, cmd, check=True, capture=True,
                            failure_log_level=logging.DEBUG)

            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.lower()
                    if key in deps and value:
                        deps[key] = [v.strip() for v in value.split() if v.strip()]

            return deps

        except Exception as e:
            self.logger.debug(f"Failed to get dependencies for {service}: {e}")
            return deps
```

### Use Cases

```python
# Example 1: Disable VMware-specific services before migration
with VMCraft() as g:
    g.add_drive_opts("vm.vmdk")
    g.launch()

    # Disable VMware services
    vmware_services = ["vmtoolsd", "vmware-tools", "open-vm-tools"]
    g.systemd_services_disable_multiple(vmware_services)

    # Enable KVM-optimized services
    g.systemd_service_enable("qemu-guest-agent")

# Example 2: Identify failed services after migration
with VMCraft() as g:
    g.add_drive_opts("migrated-vm.qcow2")
    g.launch()

    failed = g.systemd_list_failed_services()
    if failed:
        print(f"Failed services: {', '.join(failed)}")

        # Get details for troubleshooting
        for service in failed:
            status = g.systemd_service_status(service)
            print(f"{service}: {status}")
```

---

## Phase 2: Systemd-networkd Configuration (Week 2)

### APIs (12 methods)

**File:** `hyper2kvm/core/vmcraft/systemd_networkd.py`

```python
class SystemdNetworkdManager:
    """Systemd-networkd configuration management."""

    # Network File Management (6 methods)
    def create_network_file(
        self,
        name: str,
        match: dict[str, str],
        network: dict[str, Any],
        dhcp: str | None = None
    ) -> dict[str, Any]:
        """Create .network file in /etc/systemd/network/.

        Args:
            name: Network file name (e.g., "10-eth0")
            match: Match section (e.g., {"Name": "eth0", "MACAddress": "..."})
            network: Network section (e.g., {"DHCP": "yes", "Address": "192.168.1.10/24"})
            dhcp: DHCP mode (yes, no, ipv4, ipv6)

        Example:
            g.networkd_create_network_file(
                name="10-eth0",
                match={"Name": "eth0"},
                network={"DHCP": "yes"},
                dhcp="yes"
            )
        """

    def create_netdev_file(
        self,
        name: str,
        kind: str,
        netdev_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Create .netdev file for virtual devices (bridge, bond, vlan)."""

    def create_link_file(
        self,
        name: str,
        match: dict[str, str],
        link: dict[str, str]
    ) -> dict[str, Any]:
        """Create .link file for device naming."""

    def remove_network_file(self, name: str) -> dict[str, Any]:
        """Remove .network file."""

    def list_network_files(self) -> list[dict[str, Any]]:
        """List all systemd-networkd configuration files."""

    def parse_network_file(self, name: str) -> dict[str, Any]:
        """Parse existing .network file."""

    # Migration Helpers (6 methods)
    def migrate_from_ifcfg(self, interface: str) -> dict[str, Any]:
        """Migrate from /etc/sysconfig/network-scripts/ifcfg-* to networkd."""

    def migrate_from_networkmanager(self) -> dict[str, Any]:
        """Migrate NetworkManager connections to systemd-networkd."""

    def create_dhcp_network(self, interface: str) -> dict[str, Any]:
        """Create simple DHCP configuration for interface."""

    def create_static_network(
        self,
        interface: str,
        address: str,
        gateway: str,
        dns: list[str] | None = None
    ) -> dict[str, Any]:
        """Create static IP configuration."""

    def create_bridge_network(
        self,
        bridge_name: str,
        interfaces: list[str]
    ) -> dict[str, Any]:
        """Create bridge configuration."""

    def enable_networkd(self) -> dict[str, Any]:
        """Enable and start systemd-networkd."""
```

### Implementation Example

```python
# hyper2kvm/core/vmcraft/systemd_networkd.py
from pathlib import Path
from typing import Any
import logging

class SystemdNetworkdManager:
    """Systemd-networkd configuration management."""

    def __init__(self, logger: logging.Logger, guest_root: str):
        self.logger = logger
        self.guest_root = Path(guest_root)
        self.networkd_dir = self.guest_root / "etc/systemd/network"

    def create_network_file(
        self,
        name: str,
        match: dict[str, str],
        network: dict[str, Any],
        dhcp: str | None = None
    ) -> dict[str, Any]:
        """Create .network file."""
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "file": name
        }

        try:
            # Ensure directory exists
            self.networkd_dir.mkdir(parents=True, exist_ok=True)

            # Construct file path
            if not name.endswith('.network'):
                name = f"{name}.network"

            file_path = self.networkd_dir / name

            audit["attempted"] = True
            audit["path"] = str(file_path)

            # Build INI-style content
            content = "[Match]\n"
            for key, value in match.items():
                content += f"{key}={value}\n"

            content += "\n[Network]\n"
            if dhcp:
                content += f"DHCP={dhcp}\n"

            for key, value in network.items():
                if key != "DHCP":  # Already handled
                    content += f"{key}={value}\n"

            # Write file
            file_path.write_text(content)
            file_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info(f"Created network file: {file_path}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            self.logger.warning(f"Failed to create network file: {e}")
            return audit

    def migrate_from_ifcfg(self, interface: str) -> dict[str, Any]:
        """Migrate from ifcfg-* to systemd-networkd."""
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "interface": interface
        }

        try:
            # Read ifcfg file
            ifcfg_path = self.guest_root / f"etc/sysconfig/network-scripts/ifcfg-{interface}"

            if not ifcfg_path.exists():
                audit["error"] = "ifcfg_not_found"
                return audit

            audit["attempted"] = True

            # Parse ifcfg file
            config = {}
            for line in ifcfg_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"')

            # Convert to networkd format
            match_section = {"Name": interface}
            network_section = {}

            bootproto = config.get('BOOTPROTO', 'none').lower()

            if bootproto == 'dhcp':
                network_section['DHCP'] = 'yes'
            elif bootproto == 'none' or bootproto == 'static':
                if 'IPADDR' in config:
                    prefix = config.get('PREFIX', '24')
                    network_section['Address'] = f"{config['IPADDR']}/{prefix}"

                if 'GATEWAY' in config:
                    network_section['Gateway'] = config['GATEWAY']

                if 'DNS1' in config:
                    network_section['DNS'] = config['DNS1']

            # Create networkd file
            result = self.create_network_file(
                name=f"10-{interface}",
                match=match_section,
                network=network_section
            )

            audit["ok"] = result["ok"]
            audit["networkd_file"] = result.get("path")

            self.logger.info(f"Migrated {interface} from ifcfg to networkd")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            self.logger.warning(f"Failed to migrate ifcfg: {e}")
            return audit
```

### Use Cases

```python
# Example 1: Migrate RHEL VM from NetworkManager to systemd-networkd
with VMCraft() as g:
    g.add_drive_opts("rhel8-vm.qcow2")
    g.launch()

    # Migrate all interfaces
    interfaces = ["eth0", "eth1"]
    for iface in interfaces:
        result = g.networkd_migrate_from_ifcfg(iface)
        if result["ok"]:
            print(f"Migrated {iface} to systemd-networkd")

    # Enable networkd
    g.networkd_enable_networkd()

    # Disable NetworkManager
    g.systemd_service_disable("NetworkManager")

# Example 2: Create bridge for KVM networking
with VMCraft() as g:
    g.add_drive_opts("vm.qcow2")
    g.launch()

    # Create bridge
    g.networkd_create_bridge_network(
        bridge_name="br0",
        interfaces=["eth0"]
    )

    # Configure bridge with DHCP
    g.networkd_create_dhcp_network("br0")
```

---

## Phase 3: Systemd Journal Integration (Week 3)

### APIs (10 methods)

**File:** `hyper2kvm/core/vmcraft/systemd_journal.py`

```python
class SystemdJournalManager:
    """Systemd journal query and analysis."""

    # Journal Queries (6 methods)
    def journal_query(
        self,
        unit: str | None = None,
        priority: int | None = None,
        since: str | None = None,
        until: str | None = None,
        boot: int = 0,
        lines: int | None = None
    ) -> list[dict[str, Any]]:
        """Query systemd journal with filters.

        Args:
            unit: Filter by systemd unit (e.g., "sshd.service")
            priority: Filter by syslog priority (0-7, 0=emerg, 7=debug)
            since: Start time (e.g., "2024-01-01", "1 hour ago")
            until: End time
            boot: Boot number (0=current, -1=previous, -2=before that)
            lines: Limit number of entries

        Returns:
            List of journal entries with timestamp, priority, unit, message
        """

    def journal_list_boots(self) -> list[dict[str, Any]]:
        """List all available boot sessions."""

    def journal_verify(self) -> dict[str, Any]:
        """Verify journal file consistency."""

    def journal_disk_usage(self) -> dict[str, Any]:
        """Get journal disk usage statistics."""

    def journal_vacuum(self, size: str | None = None, time: str | None = None) -> dict[str, Any]:
        """Clean up journal to reduce size.

        Args:
            size: Keep journals below size (e.g., "100M", "1G")
            time: Keep journals newer than time (e.g., "1month", "2weeks")
        """

    def journal_get_catalog(self, message_id: str) -> str | None:
        """Get catalog entry for message ID."""

    # Analysis (4 methods)
    def journal_find_errors(
        self,
        since: str | None = None,
        unit: str | None = None
    ) -> list[dict[str, Any]]:
        """Find error/critical messages in journal."""

    def journal_boot_messages(self, boot: int = 0) -> list[dict[str, Any]]:
        """Get all messages from specific boot."""

    def journal_service_logs(
        self,
        service: str,
        lines: int = 100
    ) -> list[dict[str, Any]]:
        """Get recent logs for specific service."""

    def journal_export(self, output_file: str, **filters) -> dict[str, Any]:
        """Export journal to file (JSON or binary format)."""
```

### Use Cases

```python
# Example 1: Analyze boot failures
with VMCraft() as g:
    g.add_drive_opts("failed-vm.qcow2")
    g.launch()

    # Get last boot errors
    errors = g.journal_find_errors(since="-1 boot")

    for error in errors[:10]:  # Top 10 errors
        print(f"{error['timestamp']}: {error['unit']} - {error['message']}")

    # Check specific service
    ssh_logs = g.journal_service_logs("sshd.service", lines=50)

# Example 2: Clean up journal before migration
with VMCraft() as g:
    g.add_drive_opts("bloated-vm.qcow2")
    g.launch()

    # Check current size
    usage = g.journal_disk_usage()
    print(f"Journal size: {usage['size_mb']}MB")

    # Vacuum old entries
    g.journal_vacuum(size="100M", time="1month")
```

---

## Phase 4: Advanced Unit File Management (Week 4)

### APIs (13 methods)

**File:** `hyper2kvm/core/vmcraft/systemd_units.py`

```python
class SystemdUnitsManager:
    """Systemd unit file management and generation."""

    # Unit File Creation (5 methods)
    def create_service_unit(
        self,
        name: str,
        description: str,
        exec_start: str,
        exec_stop: str | None = None,
        type: str = "simple",
        restart: str = "on-failure",
        user: str | None = None,
        after: list[str] | None = None,
        requires: list[str] | None = None
    ) -> dict[str, Any]:
        """Create systemd service unit file."""

    def create_timer_unit(
        self,
        name: str,
        description: str,
        on_calendar: str | None = None,
        on_boot_sec: str | None = None,
        service: str | None = None
    ) -> dict[str, Any]:
        """Create systemd timer unit file."""

    def create_mount_unit(
        self,
        name: str,
        what: str,
        where: str,
        type: str = "auto",
        options: str | None = None
    ) -> dict[str, Any]:
        """Create systemd mount unit file."""

    def create_target_unit(
        self,
        name: str,
        description: str,
        requires: list[str] | None = None,
        wants: list[str] | None = None
    ) -> dict[str, Any]:
        """Create systemd target unit file."""

    def create_path_unit(
        self,
        name: str,
        description: str,
        path_exists: str | None = None,
        path_changed: str | None = None,
        unit: str | None = None
    ) -> dict[str, Any]:
        """Create systemd path unit (watch filesystem paths)."""

    # Unit File Management (4 methods)
    def read_unit_file(self, unit: str) -> dict[str, Any]:
        """Parse systemd unit file into structured dict."""

    def modify_unit_file(
        self,
        unit: str,
        section: str,
        key: str,
        value: str
    ) -> dict[str, Any]:
        """Modify specific key in unit file."""

    def delete_unit_file(self, unit: str) -> dict[str, Any]:
        """Delete unit file."""

    def validate_unit_file(self, unit: str) -> dict[str, Any]:
        """Validate unit file syntax."""

    # Analysis (4 methods)
    def analyze_boot_performance(self) -> dict[str, Any]:
        """Analyze boot performance using systemd-analyze."""

    def analyze_critical_chain(self, unit: str | None = None) -> dict[str, Any]:
        """Get critical boot path chain."""

    def analyze_blame(self) -> list[dict[str, Any]]:
        """Get services ordered by initialization time."""

    def list_timers(self, all: bool = False) -> list[dict[str, Any]]:
        """List active or all timers."""
```

### Implementation Example

```python
# hyper2kvm/core/vmcraft/systemd_units.py
from pathlib import Path
from typing import Any
import logging

class SystemdUnitsManager:
    """Systemd unit file management."""

    def __init__(self, logger: logging.Logger, guest_root: str):
        self.logger = logger
        self.guest_root = Path(guest_root)
        self.system_unit_dir = self.guest_root / "etc/systemd/system"

    def create_service_unit(
        self,
        name: str,
        description: str,
        exec_start: str,
        exec_stop: str | None = None,
        type: str = "simple",
        restart: str = "on-failure",
        user: str | None = None,
        after: list[str] | None = None,
        requires: list[str] | None = None
    ) -> dict[str, Any]:
        """Create systemd service unit file."""
        audit: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "error": None,
            "unit": name
        }

        try:
            # Ensure directory exists
            self.system_unit_dir.mkdir(parents=True, exist_ok=True)

            # Construct file path
            if not name.endswith('.service'):
                name = f"{name}.service"

            file_path = self.system_unit_dir / name
            audit["attempted"] = True
            audit["path"] = str(file_path)

            # Build unit file content
            content = "[Unit]\n"
            content += f"Description={description}\n"

            if after:
                content += f"After={' '.join(after)}\n"
            if requires:
                content += f"Requires={' '.join(requires)}\n"

            content += "\n[Service]\n"
            content += f"Type={type}\n"
            content += f"ExecStart={exec_start}\n"

            if exec_stop:
                content += f"ExecStop={exec_stop}\n"

            content += f"Restart={restart}\n"

            if user:
                content += f"User={user}\n"

            content += "\n[Install]\n"
            content += "WantedBy=multi-user.target\n"

            # Write file
            file_path.write_text(content)
            file_path.chmod(0o644)

            audit["ok"] = True
            self.logger.info(f"Created service unit: {file_path}")
            return audit

        except Exception as e:
            audit["error"] = str(e)
            self.logger.warning(f"Failed to create service unit: {e}")
            return audit

    def analyze_boot_performance(self) -> dict[str, Any]:
        """Analyze boot performance using systemd-analyze."""
        result = {
            "ok": False,
            "error": None,
            "firmware_time": None,
            "loader_time": None,
            "kernel_time": None,
            "initrd_time": None,
            "userspace_time": None,
            "total_time": None
        }

        try:
            from hyper2kvm.core.vmcraft._utils import run_sudo

            cmd = ["systemd-nspawn", "-D", str(self.guest_root),
                   "--quiet", "systemd-analyze", "time"]

            output = run_sudo(self.logger, cmd, check=True, capture=True,
                            failure_log_level=logging.DEBUG)

            # Parse output like:
            # Startup finished in 2.456s (firmware) + 1.234s (loader) + 3.456s (kernel) + 5.678s (initrd) + 12.345s (userspace) = 25.169s

            text = output.stdout.strip()
            result["raw_output"] = text

            # Extract times using regex
            import re

            patterns = {
                "firmware_time": r'(\d+\.\d+)s \(firmware\)',
                "loader_time": r'(\d+\.\d+)s \(loader\)',
                "kernel_time": r'(\d+\.\d+)s \(kernel\)',
                "initrd_time": r'(\d+\.\d+)s \(initrd\)',
                "userspace_time": r'(\d+\.\d+)s \(userspace\)',
                "total_time": r'= (\d+\.\d+)s'
            }

            for key, pattern in patterns.items():
                match = re.search(pattern, text)
                if match:
                    result[key] = float(match.group(1))

            result["ok"] = True
            return result

        except Exception as e:
            result["error"] = str(e)
            self.logger.debug(f"Failed to analyze boot performance: {e}")
            return result
```

### Use Cases

```python
# Example 1: Create post-migration cleanup timer
with VMCraft() as g:
    g.add_drive_opts("migrated-vm.qcow2")
    g.launch()

    # Create cleanup service
    g.systemd_create_service_unit(
        name="migration-cleanup",
        description="Post-migration cleanup tasks",
        exec_start="/usr/local/bin/cleanup-vmware-artifacts.sh",
        type="oneshot"
    )

    # Create timer to run 5 minutes after boot
    g.systemd_create_timer_unit(
        name="migration-cleanup",
        description="Run migration cleanup after boot",
        on_boot_sec="5min",
        service="migration-cleanup.service"
    )

    # Enable timer
    g.systemd_service_enable("migration-cleanup.timer")

# Example 2: Analyze boot performance
with VMCraft() as g:
    g.add_drive_opts("slow-boot-vm.qcow2")
    g.launch()

    # Get boot time breakdown
    perf = g.systemd_analyze_boot_performance()
    print(f"Total boot time: {perf['total_time']}s")
    print(f"  Userspace: {perf['userspace_time']}s")

    # Find slow services
    blame = g.systemd_analyze_blame()
    print("\nSlowest services:")
    for service in blame[:10]:
        print(f"  {service['time']}s - {service['unit']}")
```

---

## Testing Strategy

### Unit Tests (85 tests total)

```python
# tests/unit/test_core/test_vmcraft_systemd_mgr.py (25 tests)
def test_service_enable_success()
def test_service_disable_success()
def test_service_start_stop_restart()
def test_services_enable_multiple()
def test_list_services_all()
def test_list_services_by_state()
def test_list_failed_services()
def test_get_service_dependencies()
def test_daemon_reload()
def test_systemd_not_available()
# ... 15 more tests

# tests/unit/test_core/test_vmcraft_systemd_networkd.py (20 tests)
def test_create_network_file_dhcp()
def test_create_network_file_static()
def test_create_bridge_network()
def test_migrate_from_ifcfg_dhcp()
def test_migrate_from_ifcfg_static()
def test_parse_network_file()
# ... 14 more tests

# tests/unit/test_core/test_vmcraft_systemd_journal.py (18 tests)
def test_journal_query_by_unit()
def test_journal_query_by_priority()
def test_journal_find_errors()
def test_journal_vacuum()
def test_journal_disk_usage()
# ... 13 more tests

# tests/unit/test_core/test_vmcraft_systemd_units.py (22 tests)
def test_create_service_unit()
def test_create_timer_unit()
def test_read_unit_file()
def test_modify_unit_file()
def test_analyze_boot_performance()
def test_analyze_blame()
# ... 16 more tests
```

### Integration Tests

```python
# tests/integration/test_systemd_migration_workflow.py
def test_full_network_migration_workflow():
    """Test complete migration from NetworkManager to systemd-networkd."""

def test_service_optimization_workflow():
    """Test identifying and disabling unnecessary services."""

def test_boot_performance_optimization():
    """Test boot analysis and optimization."""
```

---

## Documentation

### New Documentation Files

1. **`docs/SYSTEMD_INTEGRATION.md`** (600+ lines)
   - Complete API reference
   - Usage examples
   - Migration workflows
   - Best practices

2. **`docs/SYSTEMD_MIGRATION_GUIDE.md`** (400+ lines)
   - NetworkManager → systemd-networkd migration
   - ifcfg → systemd-networkd migration
   - Service optimization guide
   - Troubleshooting

3. **`docs/SYSTEMD_RECIPES.md`** (300+ lines)
   - Common migration scenarios
   - Pre-migration checklists
   - Post-migration validation

### Updated Documentation

- `docs/09-VMCraft.md` - Add systemd section
- `README.md` - Update feature list and API count
- `CHANGELOG.md` - Add v9.2 release notes

---

## Success Metrics

### API Coverage

- **Before v9.2**: 343 methods
- **After v9.2**: 393 methods (+50)
- **Systemd Coverage**: ~80% of common systemd operations

### Performance Impact

- **Network Migration**: Automated (was manual)
- **Service Optimization**: 30-50% faster boot times
- **Configuration Time**: 5-10x faster vs manual editing

### Test Coverage

- **Unit Tests**: 85 new tests
- **Integration Tests**: 5 workflows
- **Coverage**: 100% of new code

---

## Migration Benefits

### Real-World Impact

**Scenario 1: RHEL 7 → RHEL 9 Migration**
- Before: Manual network reconfiguration (30-60 min per VM)
- After: Automated with `networkd_migrate_from_ifcfg()` (<1 min)

**Scenario 2: VMware → KVM Service Cleanup**
- Before: Manual service disable, potential boot failures
- After: Automated VMware service removal with validation

**Scenario 3: Boot Performance Optimization**
- Before: No visibility into slow services
- After: Automated analysis and optimization

---

## Risks and Mitigations

### Risk 1: systemd-nspawn Availability
- **Risk**: systemd-nspawn may not be available on host
- **Mitigation**: Fall back to chroot with bind mounts
- **Detection**: Check for systemd-nspawn availability at init

### Risk 2: Corrupted Journal Files
- **Risk**: Journal queries may fail on corrupted files
- **Mitigation**: Implement journal verification before queries
- **Recovery**: Graceful degradation with warning logs

### Risk 3: Unit File Syntax Errors
- **Risk**: Generated unit files may have syntax errors
- **Mitigation**: Validate unit files after creation
- **Testing**: Comprehensive syntax validation tests

---

## Implementation Timeline

### Sprint 1 (Week 1): Core Service Management
- Days 1-2: SystemdManager class + service control
- Days 3-4: Bulk operations + query APIs
- Day 5: Testing (25 unit tests)

### Sprint 2 (Week 2): Networkd Integration
- Days 1-3: SystemdNetworkdManager + file creation
- Day 4: Migration helpers (ifcfg, NetworkManager)
- Day 5: Testing (20 unit tests)

### Sprint 3 (Week 3): Journal Integration
- Days 1-2: SystemdJournalManager + query APIs
- Days 3-4: Analysis methods
- Day 5: Testing (18 unit tests)

### Sprint 4 (Week 4): Unit Management + Documentation
- Days 1-2: SystemdUnitsManager + unit creation
- Day 3: Boot analysis integration
- Days 4-5: Documentation + integration tests (22 unit tests + docs)

**Total Duration**: 4 weeks (20 working days)

---

## Backward Compatibility

**100% Backward Compatible** - All new functionality is additive:
- ✅ No changes to existing VMCraft APIs
- ✅ Systemd features are opt-in
- ✅ Graceful degradation if systemd not available
- ✅ Existing migrations continue to work unchanged

---

## Future Enhancements (v9.3+)

**Potential future features:**

1. **systemd-boot Integration**
   - Manage systemd-boot (UEFI boot manager)
   - Convert from GRUB to systemd-boot

2. **systemd-resolved Integration**
   - DNS configuration management
   - mDNS/LLMNR configuration

3. **systemd-machined Integration**
   - Container/VM registration
   - Machine metadata management

4. **systemd-logind Integration**
   - Session management
   - Power management configuration

5. **Cgroup Management**
   - Resource limits configuration
   - Slice management

---

## Conclusion

This systemd integration proposal addresses critical gaps in VMCraft's Linux system management capabilities. By adding 50+ new APIs across 4 major categories, we enable:

✅ **Automated Network Migration** - NetworkManager/ifcfg → systemd-networkd
✅ **Service Optimization** - Disable VMware services, enable KVM services
✅ **Boot Performance Analysis** - Identify and fix slow boot issues
✅ **Journal Integration** - Centralized logging and troubleshooting
✅ **Unit File Management** - Create/modify systemd units programmatically

**This proposal positions VMCraft as the most comprehensive systemd-aware VM migration platform available, with deep integration into the modern Linux ecosystem.**

---

**Ready for Review and Approval** ✅

**Next Steps:**
1. Review and approve proposal
2. Begin Sprint 1 implementation
3. Iterative testing and refinement
4. Documentation completion
5. Release VMCraft v9.2

**Questions or feedback?** Please provide input for refinement before implementation begins.
