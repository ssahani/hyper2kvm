# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for VMCraft systemd integration.

Tests systemctl, journalctl, systemd-analyze, and configuration tools.
"""

import pytest
from hyper2kvm.core.vmcraft.main import VMCraft


class TestSystemctlAPIs:
    """Test systemctl service management APIs."""

    def test_systemctl_list_units_not_launched(self):
        """Test that systemctl_list_units raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemctl_list_units()

    def test_systemctl_is_active_not_launched(self):
        """Test that systemctl_is_active raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemctl_is_active("sshd.service")

    def test_systemctl_list_failed_not_launched(self):
        """Test that systemctl_list_failed raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemctl_list_failed()

    def test_systemctl_list_dependencies_not_launched(self):
        """Test that systemctl_list_dependencies raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemctl_list_dependencies("network.target")

    def test_systemctl_get_default_target_not_launched(self):
        """Test that systemctl_get_default_target raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemctl_get_default_target()

    def test_systemctl_list_timers_not_launched(self):
        """Test that systemctl_list_timers raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemctl_list_timers()


class TestJournalctlAPIs:
    """Test journalctl log analysis APIs."""

    def test_journalctl_query_not_launched(self):
        """Test that journalctl_query raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.journalctl_query()

    def test_journalctl_get_errors_not_launched(self):
        """Test that journalctl_get_errors raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.journalctl_get_errors()

    def test_journalctl_list_boots_not_launched(self):
        """Test that journalctl_list_boots raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.journalctl_list_boots()

    def test_journalctl_disk_usage_not_launched(self):
        """Test that journalctl_disk_usage raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.journalctl_disk_usage()


class TestSystemdAnalyzeAPIs:
    """Test systemd-analyze system analysis APIs."""

    def test_systemd_analyze_time_not_launched(self):
        """Test that systemd_analyze_time raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemd_analyze_time()

    def test_systemd_analyze_blame_not_launched(self):
        """Test that systemd_analyze_blame raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemd_analyze_blame()

    def test_systemd_analyze_critical_chain_not_launched(self):
        """Test that systemd_analyze_critical_chain raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemd_analyze_critical_chain()

    def test_systemd_analyze_security_not_launched(self):
        """Test that systemd_analyze_security raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemd_analyze_security()

    def test_systemd_analyze_calendar_not_launched(self):
        """Test that systemd_analyze_calendar raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.systemd_analyze_calendar("daily")


class TestConfigurationAPIs:
    """Test configuration tools (timedatectl, hostnamectl, localectl)."""

    def test_timedatectl_status_not_launched(self):
        """Test that timedatectl_status raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.timedatectl_status()

    def test_hostnamectl_status_not_launched(self):
        """Test that hostnamectl_status raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.hostnamectl_status()

    def test_localectl_status_not_launched(self):
        """Test that localectl_status raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.localectl_status()

    def test_loginctl_list_sessions_not_launched(self):
        """Test that loginctl_list_sessions raises error when not launched."""
        g = VMCraft()
        with pytest.raises(RuntimeError, match="Not launched"):
            g.loginctl_list_sessions()


class TestSystemdManagersInitialization:
    """Test that systemd managers are properly initialized."""

    def test_systemd_managers_not_initialized_before_launch(self):
        """Test that systemd managers are None before launch."""
        g = VMCraft()
        assert g._systemctl is None
        assert g._journalctl is None
        assert g._systemd_analyze is None
        assert g._sysconfig is None


class TestAPISignatures:
    """Test that all systemd APIs have correct signatures."""

    def test_all_systemctl_methods_exist(self):
        """Test that all expected systemctl methods exist."""
        g = VMCraft()

        expected_methods = [
            'systemctl_list_units',
            'systemctl_list_unit_files',
            'systemctl_is_active',
            'systemctl_is_enabled',
            'systemctl_is_failed',
            'systemctl_show',
            'systemctl_status',
            'systemctl_cat',
            'systemctl_list_dependencies',
            'systemctl_list_failed',
            'systemctl_get_default_target',
            'systemctl_list_targets',
            'systemctl_list_timers',
            'systemctl_list_sockets',
            'systemctl_list_mounts',
        ]

        for method_name in expected_methods:
            assert hasattr(g, method_name), f"Method {method_name} not found"
            method = getattr(g, method_name)
            assert callable(method), f"Method {method_name} is not callable"

    def test_all_journalctl_methods_exist(self):
        """Test that all expected journalctl methods exist."""
        g = VMCraft()

        expected_methods = [
            'journalctl_query',
            'journalctl_list_boots',
            'journalctl_get_boot_log',
            'journalctl_get_errors',
            'journalctl_get_warnings',
            'journalctl_disk_usage',
            'journalctl_verify',
            'journalctl_export',
        ]

        for method_name in expected_methods:
            assert hasattr(g, method_name), f"Method {method_name} not found"
            method = getattr(g, method_name)
            assert callable(method), f"Method {method_name} is not callable"

    def test_all_systemd_analyze_methods_exist(self):
        """Test that all expected systemd-analyze methods exist."""
        g = VMCraft()

        expected_methods = [
            'systemd_analyze_time',
            'systemd_analyze_blame',
            'systemd_analyze_critical_chain',
            'systemd_analyze_security',
            'systemd_analyze_verify',
            'systemd_analyze_dot',
            'systemd_analyze_calendar',
            'systemd_analyze_dump',
            'systemd_analyze_plot',
            'systemd_analyze_syscall_filter',
        ]

        for method_name in expected_methods:
            assert hasattr(g, method_name), f"Method {method_name} not found"
            method = getattr(g, method_name)
            assert callable(method), f"Method {method_name} is not callable"

    def test_all_config_methods_exist(self):
        """Test that all expected configuration methods exist."""
        g = VMCraft()

        expected_methods = [
            'timedatectl_status',
            'timedatectl_list_timezones',
            'timedatectl_show',
            'hostnamectl_status',
            'hostnamectl_hostname',
            'localectl_status',
            'localectl_list_locales',
            'localectl_list_keymaps',
            'localectl_list_x11_keymap_models',
            'localectl_list_x11_keymap_layouts',
            'loginctl_list_sessions',
            'loginctl_list_users',
            'loginctl_show_session',
        ]

        for method_name in expected_methods:
            assert hasattr(g, method_name), f"Method {method_name} not found"
            method = getattr(g, method_name)
            assert callable(method), f"Method {method_name} is not callable"

    def test_methods_have_docstrings(self):
        """Test that all new methods have docstrings."""
        g = VMCraft()

        methods_to_check = [
            # systemctl
            'systemctl_list_units', 'systemctl_is_active', 'systemctl_list_failed',
            # journalctl
            'journalctl_query', 'journalctl_get_errors', 'journalctl_list_boots',
            # systemd-analyze
            'systemd_analyze_time', 'systemd_analyze_blame', 'systemd_analyze_security',
            # config
            'timedatectl_status', 'hostnamectl_status', 'localectl_status',
        ]

        for method_name in methods_to_check:
            method = getattr(g, method_name)
            assert method.__doc__ is not None, f"Method {method_name} has no docstring"
            assert len(method.__doc__.strip()) > 0, f"Method {method_name} has empty docstring"


class TestManagerInstantiation:
    """Test that systemd managers can be instantiated directly."""

    def test_systemctl_manager_instantiation(self):
        """Test that SystemctlManager can be instantiated."""
        from hyper2kvm.core.vmcraft.systemd import SystemctlManager
        import logging

        def dummy_command(cmd):
            return ""

        logger = logging.getLogger(__name__)
        manager = SystemctlManager(dummy_command, logger)
        assert manager is not None

    def test_journalctl_manager_instantiation(self):
        """Test that JournalctlManager can be instantiated."""
        from hyper2kvm.core.vmcraft.systemd import JournalctlManager
        import logging

        def dummy_command(cmd):
            return ""

        logger = logging.getLogger(__name__)
        manager = JournalctlManager(dummy_command, logger)
        assert manager is not None

    def test_systemd_analyzer_instantiation(self):
        """Test that SystemdAnalyzer can be instantiated."""
        from hyper2kvm.core.vmcraft.systemd import SystemdAnalyzer
        import logging

        def dummy_command(cmd):
            return ""

        logger = logging.getLogger(__name__)
        analyzer = SystemdAnalyzer(dummy_command, logger)
        assert analyzer is not None

    def test_sysconfig_manager_instantiation(self):
        """Test that SystemConfigManager can be instantiated."""
        from hyper2kvm.core.vmcraft.systemd import SystemConfigManager
        import logging

        def dummy_command(cmd):
            return ""

        logger = logging.getLogger(__name__)
        manager = SystemConfigManager(dummy_command, logger)
        assert manager is not None


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
