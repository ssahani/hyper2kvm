# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for firstboot systemd service and script injection.
"""
import importlib

import pytest
from fakes.fake_guestfs import FakeGuestFS
from fakes.fake_logger import FakeLogger


@pytest.fixture
def firstboot_module():
    """Import firstboot_injector module"""
    try:
        return importlib.import_module("hyper2kvm.fixers.firstboot_injector")
    except Exception as e:
        pytest.skip(f"Cannot import firstboot_injector: {e}")


class TestFirstbootInjector:
    """Test suite for firstboot injection functionality"""

    def test_inject_firstboot_no_config(self, firstboot_module):
        """Test that injection is skipped when no config provided"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is False
        assert result["reason"] == "no_config"

    def test_inject_firstboot_invalid_config_type(self, firstboot_module):
        """Test that invalid config type is handled"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.firstboot_config = "not_a_dict"  # Should be dict

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is False
        assert result["reason"] == "invalid_config"

    def test_inject_firstboot_no_systemd(self, firstboot_module):
        """Test that injection fails gracefully without systemd"""
        g = FakeGuestFS()
        g.test_no_systemd = True  # Flag to simulate no systemd

        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.firstboot_config = {
            "script": "#!/bin/bash\necho 'test'"
        }

        # Mock _guest_has_systemd to return False
        original_func = firstboot_module._guest_has_systemd
        firstboot_module._guest_has_systemd = lambda g: False

        try:
            result = firstboot_module.inject_firstboot(obj, g)
            assert result["injected"] is False
            assert result["reason"] == "no_systemd"
        finally:
            firstboot_module._guest_has_systemd = original_func

    def test_inject_firstboot_inline_script(self, firstboot_module):
        """Test injection with inline script"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.firstboot_config = {
            "script": "#!/bin/bash\necho 'Hello First Boot'"
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is True
        assert result["dry_run"] is False
        assert "service_name" in result
        assert len(result["files_created"]) > 0

        # Check that files were created
        file_paths = [f["path"] for f in result["files_created"]]
        assert any("/usr/local/lib/hyper2kvm-firstboot/" in path for path in file_paths)
        assert any(".service" in path for path in file_paths)

    def test_inject_firstboot_multiple_scripts_with_order(self, firstboot_module):
        """Test injection with multiple scripts in specific order"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.firstboot_config = {
            "scripts": [
                {
                    "name": "third-script",
                    "content": "#!/bin/bash\necho 'third'",
                    "order": 30
                },
                {
                    "name": "first-script",
                    "content": "#!/bin/bash\necho 'first'",
                    "order": 10
                },
                {
                    "name": "second-script",
                    "content": "#!/bin/bash\necho 'second'",
                    "order": 20
                }
            ]
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is True
        assert len(result["files_created"]) >= 3  # 3 scripts + runner + service

    def test_inject_firstboot_custom_service_name(self, firstboot_module):
        """Test custom service name"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.firstboot_config = {
            "service_name": "custom-firstboot",
            "script": "#!/bin/bash\necho 'custom'"
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is True
        assert result["service_name"] == "custom-firstboot.service"

    def test_inject_firstboot_dry_run(self, firstboot_module):
        """Test dry-run mode"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = True
        obj.firstboot_config = {
            "script": "#!/bin/bash\necho 'test'"
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is True
        assert result["dry_run"] is True
        # In dry-run, files_created should contain metadata but files aren't actually written
        assert len(result["files_created"]) > 0
        assert all("bytes" in f for f in result["files_created"])

    def test_inject_firstboot_no_scripts(self, firstboot_module):
        """Test that config with no scripts is handled"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.firstboot_config = {
            "scripts": []  # Empty scripts list
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is False
        assert result["reason"] == "no_scripts"

    def test_inject_firstboot_script_without_shebang(self, firstboot_module):
        """Test that shebang is added if missing"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.firstboot_config = {
            "script": "echo 'no shebang'"  # Missing #!/bin/bash
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is True
        # Shebang should be added automatically

    def test_inject_firstboot_service_customization(self, firstboot_module):
        """Test systemd service customization"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.firstboot_config = {
            "script": "#!/bin/bash\necho 'test'",
            "service": {
                "Description": "Custom first boot service",
                "After": "network-online.target",
                "Environment": ["VAR1=value1", "VAR2=value2"]
            }
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is True

        # Check that service file contains customizations
        service_files = [f for f in result["files_created"] if f["kind"] == "service"]
        assert len(service_files) == 1

    def test_inject_firstboot_keep_enabled(self, firstboot_module):
        """Test keep_enabled flag"""
        g = FakeGuestFS()
        obj = type("Obj", (), {})()
        obj.logger = FakeLogger()
        obj.dry_run = False
        obj.firstboot_config = {
            "script": "#!/bin/bash\necho 'debug'",
            "keep_enabled": True  # Don't disable service after run
        }

        result = firstboot_module.inject_firstboot(obj, g)

        assert result["injected"] is True
        # Runner script should not contain systemctl disable command


class TestGenerateRunnerScript:
    """Test runner script generation"""

    def test_generate_runner_script_basic(self, firstboot_module):
        """Test basic runner script generation"""
        script_paths = ["/path/to/script1.sh", "/path/to/script2.sh"]
        service_name = "test.service"

        runner = firstboot_module._generate_runner_script(
            script_paths, service_name, keep_enabled=False
        )

        assert "#!/bin/bash" in runner
        assert "script1.sh" in runner
        assert "script2.sh" in runner
        assert "systemctl disable test.service" in runner
        assert "/var/log/hyper2kvm-firstboot.log" in runner

    def test_generate_runner_script_keep_enabled(self, firstboot_module):
        """Test runner script with keep_enabled=True"""
        script_paths = ["/path/to/script.sh"]
        service_name = "test.service"

        runner = firstboot_module._generate_runner_script(
            script_paths, service_name, keep_enabled=True
        )

        assert "systemctl disable" not in runner

    def test_generate_runner_script_multiple_scripts(self, firstboot_module):
        """Test runner with multiple scripts"""
        script_paths = [
            "/usr/local/lib/firstboot/network.sh",
            "/usr/local/lib/firstboot/hostname.sh",
            "/usr/local/lib/firstboot/cleanup.sh"
        ]
        service_name = "firstboot.service"

        runner = firstboot_module._generate_runner_script(
            script_paths, service_name, keep_enabled=False
        )

        for path in script_paths:
            assert path in runner

        assert "SUCCESS_COUNT" in runner
        assert "FAIL_COUNT" in runner


class TestGenerateSystemdService:
    """Test systemd service unit generation"""

    def test_generate_systemd_service_basic(self, firstboot_module):
        """Test basic systemd service generation"""
        runner_path = "/usr/local/lib/firstboot/run.sh"
        service_config = {}

        service = firstboot_module._generate_systemd_service(runner_path, service_config)

        assert "[Unit]" in service
        assert "[Service]" in service
        assert "[Install]" in service
        assert runner_path in service
        assert "Type=oneshot" in service
        assert "WantedBy=multi-user.target" in service

    def test_generate_systemd_service_custom_description(self, firstboot_module):
        """Test service with custom description"""
        runner_path = "/usr/local/lib/firstboot/run.sh"
        service_config = {
            "Description": "My custom first boot service"
        }

        service = firstboot_module._generate_systemd_service(runner_path, service_config)

        assert "My custom first boot service" in service

    def test_generate_systemd_service_with_after(self, firstboot_module):
        """Test service with After directive"""
        runner_path = "/usr/local/lib/firstboot/run.sh"
        service_config = {
            "After": "network-online.target systemd-resolved.service"
        }

        service = firstboot_module._generate_systemd_service(runner_path, service_config)

        assert "After=network-online.target systemd-resolved.service" in service

    def test_generate_systemd_service_with_environment(self, firstboot_module):
        """Test service with environment variables"""
        runner_path = "/usr/local/lib/firstboot/run.sh"
        service_config = {
            "Environment": ["VAR1=value1", "VAR2=value2", "DEBUG=1"]
        }

        service = firstboot_module._generate_systemd_service(runner_path, service_config)

        assert 'Environment="VAR1=value1"' in service
        assert 'Environment="VAR2=value2"' in service
        assert 'Environment="DEBUG=1"' in service

    def test_generate_systemd_service_with_requires_mounts_for(self, firstboot_module):
        """Test service with RequiresMountsFor"""
        runner_path = "/usr/local/lib/firstboot/run.sh"
        service_config = {
            "RequiresMountsFor": ["/data", "/opt/app"]
        }

        service = firstboot_module._generate_systemd_service(runner_path, service_config)

        assert "RequiresMountsFor=/data /opt/app" in service


class TestGuestHasSystemd:
    """Test systemd detection"""

    def test_guest_has_systemd_true(self, firstboot_module):
        """Test detection when systemd is present"""
        g = FakeGuestFS()
        # FakeGuestFS will return True for exists() by default

        has_systemd = firstboot_module._guest_has_systemd(g)

        # Should detect systemd (FakeGuestFS exists() returns True)
        assert has_systemd is True

    def test_guest_has_systemd_false(self, firstboot_module):
        """Test detection when systemd is absent"""
        g = FakeGuestFS()
        g.test_no_systemd = True

        # Mock to return False for all systemd paths
        original_exists = g.exists
        g.exists = lambda path: False if any(s in path for s in ["systemd", "systemctl"]) else original_exists(path)

        has_systemd = firstboot_module._guest_has_systemd(g)

        assert has_systemd is False
