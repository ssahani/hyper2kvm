# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
from unittest.mock import Mock

from hyper2kvm.config.systemd_template import SystemdTemplate


class TestSystemdTemplate(unittest.TestCase):
    """Test systemd unit file generation."""

    def test_generates_valid_unit_file(self):
        """Test that valid systemd unit is generated."""
        template = SystemdTemplate(
            vm_name="test-vm",
            description="Test VM",
            exec_start="/usr/bin/virsh start test-vm",
            exec_stop="/usr/bin/virsh shutdown test-vm",
        )

        unit_content = template.render()

        self.assertIsInstance(unit_content, str)
        self.assertIn("[Unit]", unit_content)
        self.assertIn("[Service]", unit_content)
        self.assertIn("[Install]", unit_content)

    def test_includes_description(self):
        """Test that description is included in unit file."""
        template = SystemdTemplate(
            vm_name="test-vm",
            description="My Custom VM Description",
            exec_start="/usr/bin/virsh start test-vm",
        )

        unit_content = template.render()

        self.assertIn("Description=My Custom VM Description", unit_content)

    def test_includes_exec_start(self):
        """Test that ExecStart is included."""
        template = SystemdTemplate(
            vm_name="test-vm",
            exec_start="/usr/bin/virsh start test-vm",
        )

        unit_content = template.render()

        self.assertIn("ExecStart=/usr/bin/virsh start test-vm", unit_content)

    def test_includes_exec_stop(self):
        """Test that ExecStop is included."""
        template = SystemdTemplate(
            vm_name="test-vm",
            exec_start="/usr/bin/virsh start test-vm",
            exec_stop="/usr/bin/virsh shutdown test-vm",
        )

        unit_content = template.render()

        self.assertIn("ExecStop=/usr/bin/virsh shutdown test-vm", unit_content)

    def test_includes_dependencies(self):
        """Test that systemd dependencies are configured."""
        template = SystemdTemplate(
            vm_name="test-vm",
            exec_start="/usr/bin/virsh start test-vm",
            after=["libvirtd.service"],
            requires=["libvirtd.service"],
        )

        unit_content = template.render()

        self.assertIn("After=", unit_content)
        self.assertIn("Requires=", unit_content)

    def test_libvirt_vm_template(self):
        """Test template for libvirt VM autostart."""
        vm_name = "test-vm"
        template = SystemdTemplate.for_libvirt_vm(vm_name)

        unit_content = template.render()

        # Should include virsh commands
        self.assertIn("virsh", unit_content)
        self.assertIn(vm_name, unit_content)
        self.assertIn("start", unit_content)
        self.assertIn("shutdown", unit_content)

    def test_sanitizes_vm_name(self):
        """Test that VM name is sanitized for systemd."""
        vm_name = "my-vm-with-special-chars!@#"
        template = SystemdTemplate.for_libvirt_vm(vm_name)

        unit_content = template.render()

        # Should handle special characters
        self.assertIsInstance(unit_content, str)

    def test_install_section(self):
        """Test that Install section is configured."""
        template = SystemdTemplate(
            vm_name="test-vm",
            exec_start="/usr/bin/virsh start test-vm",
            wanted_by=["multi-user.target"],
        )

        unit_content = template.render()

        self.assertIn("[Install]", unit_content)
        self.assertIn("WantedBy=", unit_content)


class TestSystemdTemplateFormatting(unittest.TestCase):
    """Test systemd template formatting."""

    def test_multiline_formatting(self):
        """Test that multi-line commands are formatted correctly."""
        template = SystemdTemplate(
            vm_name="test-vm",
            exec_start="/usr/bin/virsh start test-vm",
        )

        unit_content = template.render()

        # Each section should be on its own line
        lines = unit_content.strip().split("\n")
        self.assertGreater(len(lines), 3)

    def test_preserves_systemd_structure(self):
        """Test that systemd INI structure is preserved."""
        template = SystemdTemplate(
            vm_name="test-vm",
            exec_start="/usr/bin/virsh start test-vm",
        )

        unit_content = template.render()

        # Sections should appear in order
        unit_idx = unit_content.find("[Unit]")
        service_idx = unit_content.find("[Service]")
        install_idx = unit_content.find("[Install]")

        self.assertGreater(service_idx, unit_idx)
        self.assertGreater(install_idx, service_idx)


if __name__ == "__main__":
    unittest.main()
