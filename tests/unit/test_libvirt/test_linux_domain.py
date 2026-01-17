# SPDX-License-Identifier: LGPL-3.0-or-later
import unittest
import tempfile
import argparse
from pathlib import Path
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from hyper2kvm.libvirt.linux_domain import LinuxDomainSpec


class TestLinuxDomainSpec(unittest.TestCase):
    """Test Linux domain XML generation."""

    def setUp(self):
        self.logger = Mock()

    def test_generates_valid_xml(self):
        """Test that generated XML is valid."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk)],
                network="default",
                graphics=False,
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)

            # Parse XML to verify it's valid
            root = ET.fromstring(xml_str)
            self.assertEqual(root.tag, "domain")
            self.assertEqual(root.get("type"), "kvm")

    def test_includes_vm_name(self):
        """Test that VM name is included in XML."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="my-linux-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            name = root.find("name")
            self.assertIsNotNone(name)
            self.assertEqual(name.text, "my-linux-vm")

    def test_includes_memory_config(self):
        """Test that memory configuration is included."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=4096,
                vcpus=2,
                disk=[str(disk)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            memory = root.find("memory")
            self.assertIsNotNone(memory)
            # Memory is typically in KiB
            self.assertIn("4096", memory.text or str(memory.get("value", "")))

    def test_includes_vcpu_config(self):
        """Test that vCPU configuration is included."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=4,
                disk=[str(disk)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            vcpu = root.find("vcpu")
            self.assertIsNotNone(vcpu)
            self.assertEqual(vcpu.text, "4")

    def test_includes_disk_device(self):
        """Test that disk device is included."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            devices = root.find("devices")
            self.assertIsNotNone(devices)

            # Find disk device
            disk_dev = devices.find(".//disk[@type='file']")
            self.assertIsNotNone(disk_dev)

    def test_supports_multiple_disks(self):
        """Test support for multiple disk devices."""
        with tempfile.TemporaryDirectory() as td:
            disk1 = Path(td) / "disk1.qcow2"
            disk2 = Path(td) / "disk2.qcow2"
            disk1.write_bytes(b"fake disk 1")
            disk2.write_bytes(b"fake disk 2")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk1), str(disk2)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            devices = root.find("devices")
            disks = devices.findall(".//disk[@type='file']")

            # Should have at least 2 disks
            self.assertGreaterEqual(len(disks), 2)

    def test_includes_network_interface(self):
        """Test that network interface is included."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk)],
                network="default",
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            devices = root.find("devices")
            interface = devices.find(".//interface")
            self.assertIsNotNone(interface)

    def test_virtio_drivers(self):
        """Test that virtio drivers are used."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)

            # virtio is the preferred driver for Linux VMs
            self.assertIn("virtio", xml_str)


class TestLinuxDomainSpecFeatures(unittest.TestCase):
    """Test Linux domain feature configuration."""

    def setUp(self):
        self.logger = Mock()

    def test_includes_os_boot_config(self):
        """Test that OS boot configuration is included."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            os_elem = root.find("os")
            self.assertIsNotNone(os_elem)

            os_type = os_elem.find("type")
            self.assertIsNotNone(os_type)
            self.assertEqual(os_type.text, "hvm")

    def test_includes_features(self):
        """Test that domain features are included."""
        with tempfile.TemporaryDirectory() as td:
            disk = Path(td) / "test.qcow2"
            disk.write_bytes(b"fake disk")

            args = argparse.Namespace(
                name="test-vm",
                memory=2048,
                vcpus=2,
                disk=[str(disk)],
            )

            xml_str = LinuxDomainSpec.generate(self.logger, args)
            root = ET.fromstring(xml_str)

            features = root.find("features")
            self.assertIsNotNone(features)


if __name__ == "__main__":
    unittest.main()
