# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Integration tests for VMCraft systemd APIs.

Tests actual systemd functionality against real disk images.
"""

import pytest
from pathlib import Path
from hyper2kvm.core.vmcraft.main import VMCraft


@pytest.fixture(scope="module")
def test_images():
    """Find available test images."""
    possible_images = [
        "tests/fixtures/images/test-linux-qcow2.qcow2",
        "tests/fixtures/images/test-linux-vmdk.vmdk",
        "tests/fixtures/images/test-linux-raw.img",
    ]

    for img in possible_images:
        if Path(img).exists():
            return img

    pytest.skip("No test disk images available")


@pytest.fixture(scope="module")
def vmcraft_session(test_images):
    """Create a VMCraft session for testing."""
    g = VMCraft()
    g.add_drive_opts(test_images, readonly=True)
    g.launch()
    yield g
    g.shutdown()


class TestSystemctlIntegration:
    """Integration tests for systemctl APIs."""

    def test_systemctl_list_units_services(self, vmcraft_session):
        """Test listing systemd service units."""
        units = vmcraft_session.systemctl_list_units(unit_type="service")

        print(f"\n=== Systemd Services ===")
        print(f"Total services found: {len(units)}")

        if units:
            print("\nFirst 10 services:")
            for unit in units[:10]:
                print(f"  {unit.get('unit', 'N/A'):40s} {unit.get('active', 'N/A'):10s} {unit.get('sub', 'N/A')}")

        # Should return a list (even if empty)
        assert isinstance(units, list)
        for unit in units:
            assert isinstance(unit, dict)
            assert 'unit' in unit

    def test_systemctl_list_failed(self, vmcraft_session):
        """Test listing failed units."""
        failed = vmcraft_session.systemctl_list_failed()

        print(f"\n=== Failed Services ===")
        print(f"Failed services: {len(failed)}")

        if failed:
            for svc in failed:
                print(f"  ❌ {svc.get('unit', 'N/A'):40s} {svc.get('description', 'N/A')}")
        else:
            print("  ✅ No failed services")

        assert isinstance(failed, list)

    def test_systemctl_get_default_target(self, vmcraft_session):
        """Test getting default target."""
        target = vmcraft_session.systemctl_get_default_target()

        print(f"\n=== Default Target ===")
        print(f"Default boot target: {target or 'Unable to determine'}")

        # Should return a string (may be empty if systemd not available)
        assert isinstance(target, str)

    def test_systemctl_list_timers(self, vmcraft_session):
        """Test listing systemd timers."""
        timers = vmcraft_session.systemctl_list_timers()

        print(f"\n=== Systemd Timers ===")
        print(f"Total timers: {len(timers)}")

        if timers:
            print("\nActive timers:")
            for timer in timers[:5]:
                print(f"  {timer.get('unit', 'N/A'):40s} {timer.get('next', 'N/A')}")

        assert isinstance(timers, list)


class TestJournalctlIntegration:
    """Integration tests for journalctl APIs."""

    def test_journalctl_list_boots(self, vmcraft_session):
        """Test listing boot entries."""
        boots = vmcraft_session.journalctl_list_boots()

        print(f"\n=== Boot History ===")
        print(f"Total boots recorded: {len(boots)}")

        if boots:
            print("\nRecent boots:")
            for boot in boots[:3]:
                print(f"  Boot {boot.get('offset', 'N/A'):3s}: {boot.get('boot_id', 'N/A')[:16]}... {boot.get('time_range', 'N/A')[:50]}")

        assert isinstance(boots, list)

    def test_journalctl_get_errors(self, vmcraft_session):
        """Test getting error messages."""
        errors = vmcraft_session.journalctl_get_errors(lines=10)

        print(f"\n=== Recent Errors ===")
        print(f"Error messages found: {len(errors)}")

        if errors:
            print("\nLast 5 errors:")
            for err in errors[:5]:
                unit = err.get('unit', 'unknown')[:30]
                msg = err.get('message', 'N/A')[:80]
                print(f"  [{unit}] {msg}")
        else:
            print("  ✅ No errors in journal")

        assert isinstance(errors, list)

    def test_journalctl_disk_usage(self, vmcraft_session):
        """Test journal disk usage."""
        usage = vmcraft_session.journalctl_disk_usage()

        print(f"\n=== Journal Disk Usage ===")
        if usage:
            print(f"Current usage: {usage.get('current_use', 'Unknown')}")
        else:
            print("Unable to determine journal disk usage")

        assert isinstance(usage, dict)


class TestSystemdAnalyzeIntegration:
    """Integration tests for systemd-analyze APIs."""

    def test_systemd_analyze_time(self, vmcraft_session):
        """Test boot time analysis."""
        timing = vmcraft_session.systemd_analyze_time()

        print(f"\n=== Boot Time Analysis ===")
        if timing:
            print(f"Total boot time: {timing.get('total', 0):.2f}s")
            if 'firmware' in timing:
                print(f"  Firmware: {timing.get('firmware', 0):.2f}s")
            if 'loader' in timing:
                print(f"  Loader: {timing.get('loader', 0):.2f}s")
            if 'kernel' in timing:
                print(f"  Kernel: {timing.get('kernel', 0):.2f}s")
            if 'initrd' in timing:
                print(f"  Initrd: {timing.get('initrd', 0):.2f}s")
            if 'userspace' in timing:
                print(f"  Userspace: {timing.get('userspace', 0):.2f}s")
        else:
            print("Unable to analyze boot time")

        assert isinstance(timing, dict)

    def test_systemd_analyze_blame(self, vmcraft_session):
        """Test service blame analysis."""
        blame = vmcraft_session.systemd_analyze_blame(lines=10)

        print(f"\n=== Top 10 Slowest Services ===")
        if blame:
            for idx, svc in enumerate(blame, 1):
                print(f"{idx:2d}. {svc.get('time', 'N/A'):>10s}  {svc.get('unit', 'N/A')}")
        else:
            print("Unable to perform blame analysis")

        assert isinstance(blame, list)

    def test_systemd_analyze_critical_chain(self, vmcraft_session):
        """Test critical chain analysis."""
        chain = vmcraft_session.systemd_analyze_critical_chain()

        print(f"\n=== Critical Boot Chain ===")
        if chain:
            # Show first 500 chars
            print(chain[:500])
            if len(chain) > 500:
                print(f"... ({len(chain) - 500} more characters)")
        else:
            print("Unable to determine critical chain")

        assert isinstance(chain, str)


class TestConfigurationToolsIntegration:
    """Integration tests for configuration tools."""

    def test_timedatectl_status(self, vmcraft_session):
        """Test time/date configuration."""
        status = vmcraft_session.timedatectl_status()

        print(f"\n=== Time/Date Configuration ===")
        if status:
            for key, value in list(status.items())[:8]:
                print(f"  {key:20s}: {value}")
        else:
            print("Unable to get time/date status")

        assert isinstance(status, dict)

    def test_hostnamectl_status(self, vmcraft_session):
        """Test hostname configuration."""
        status = vmcraft_session.hostnamectl_status()

        print(f"\n=== System Identity ===")
        if status:
            hostname = status.get('static_hostname', 'Unknown')
            os_name = status.get('operating_system', 'Unknown')
            kernel = status.get('kernel', 'Unknown')
            arch = status.get('architecture', 'Unknown')

            print(f"  Hostname: {hostname}")
            print(f"  OS: {os_name}")
            print(f"  Kernel: {kernel}")
            print(f"  Architecture: {arch}")
        else:
            print("Unable to get hostname status")

        assert isinstance(status, dict)

    def test_localectl_status(self, vmcraft_session):
        """Test locale configuration."""
        status = vmcraft_session.localectl_status()

        print(f"\n=== Locale Configuration ===")
        if status:
            locale = status.get('system_locale', 'Unknown')
            keymap = status.get('vc_keymap', 'Unknown')
            print(f"  System Locale: {locale}")
            print(f"  Keymap: {keymap}")
        else:
            print("Unable to get locale status")

        assert isinstance(status, dict)

    def test_loginctl_list_sessions(self, vmcraft_session):
        """Test session listing."""
        sessions = vmcraft_session.loginctl_list_sessions()

        print(f"\n=== Active Sessions ===")
        print(f"Total sessions: {len(sessions)}")

        if sessions:
            for session in sessions:
                print(f"  Session {session.get('session', 'N/A')}: User {session.get('user', 'N/A')} on {session.get('tty', 'N/A')}")
        else:
            print("  No active sessions")

        assert isinstance(sessions, list)


class TestSystemdFullWorkflow:
    """Test complete systemd workflow."""

    def test_vm_health_check(self, vmcraft_session):
        """Perform complete VM health check using systemd APIs."""
        print("\n" + "="*80)
        print("VM HEALTH CHECK REPORT")
        print("="*80)

        # 1. Service Status
        print("\n1. SERVICE STATUS")
        print("-" * 40)
        failed = vmcraft_session.systemctl_list_failed()
        if failed:
            print(f"⚠️  {len(failed)} failed services detected:")
            for svc in failed[:5]:
                print(f"   - {svc.get('unit', 'N/A')}")
        else:
            print("✅ All services running normally")

        # 2. Boot Performance
        print("\n2. BOOT PERFORMANCE")
        print("-" * 40)
        timing = vmcraft_session.systemd_analyze_time()
        if timing:
            total = timing.get('total', 0)
            print(f"Total boot time: {total:.2f}s")
            if total > 120:
                print("⚠️  Boot time exceeds 2 minutes")
            else:
                print("✅ Boot time is acceptable")

        # 3. Error Analysis
        print("\n3. ERROR ANALYSIS")
        print("-" * 40)
        errors = vmcraft_session.journalctl_get_errors(lines=5)
        if errors:
            print(f"⚠️  {len(errors)} recent errors found")
            for err in errors[:3]:
                print(f"   [{err.get('unit', 'unknown')}] {err.get('message', 'N/A')[:60]}")
        else:
            print("✅ No recent errors")

        # 4. System Configuration
        print("\n4. SYSTEM CONFIGURATION")
        print("-" * 40)
        hostname_info = vmcraft_session.hostnamectl_status()
        if hostname_info:
            print(f"Hostname: {hostname_info.get('static_hostname', 'Unknown')}")
            print(f"OS: {hostname_info.get('operating_system', 'Unknown')}")

        time_info = vmcraft_session.timedatectl_status()
        if time_info:
            print(f"Timezone: {time_info.get('timezone', 'Unknown')}")

        print("\n" + "="*80)
        print("HEALTH CHECK COMPLETE")
        print("="*80 + "\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
