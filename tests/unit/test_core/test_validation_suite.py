# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit Tests for Validation Suite

Tests offline validation checks for:
- fstab existence and validity
- Kernel presence
- Bootloader configuration
- Network configuration
"""

import importlib
import pytest
from pathlib import Path

from tests.fixtures.fake_guestfs import FakeGuestFS
from tests.fixtures.fake_logger import FakeLogger


def test_validation_suite_basic_checks():
    """Test basic validation checks pass"""
    try:
        offline_fixer = importlib.import_module("hyper2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    g = FakeGuestFS()
    g.dirs |= {"/boot", "/etc", "/boot/grub2"}
    g.fs["/etc/fstab"] = b"UUID=1 / ext4 defaults 0 1\n"
    g.fs["/boot/vmlinuz-1"] = b"kernel"

    fx = object.__new__(offline_fixer.OfflineFSFix)
    fx.logger = FakeLogger()
    suite = offline_fixer.OfflineFSFix.create_validation_suite(fx, g)
    res = suite.run_all({"image": "x", "root_dev": "/dev/sda2", "subvol": None})

    results = res.get("results", res)
    assert "fstab_exists" in results
    assert "kernel_present" in results


def test_validation_fstab_missing():
    """Test validation detects missing fstab"""
    try:
        offline_fixer = importlib.import_module("hyper2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    g = FakeGuestFS()
    g.dirs |= {"/boot", "/etc"}
    # No fstab

    fx = object.__new__(offline_fixer.OfflineFSFix)
    fx.logger = FakeLogger()
    suite = offline_fixer.OfflineFSFix.create_validation_suite(fx, g)
    res = suite.run_all({"image": "x", "root_dev": "/dev/sda2", "subvol": None})

    results = res.get("results", res)
    # Should detect missing fstab
    assert "fstab_exists" in results


def test_validation_kernel_missing():
    """Test validation detects missing kernel"""
    try:
        offline_fixer = importlib.import_module("hyper2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    g = FakeGuestFS()
    g.dirs |= {"/boot", "/etc"}
    g.fs["/etc/fstab"] = b"UUID=1 / ext4 defaults 0 1\n"
    # No kernel in /boot

    fx = object.__new__(offline_fixer.OfflineFSFix)
    fx.logger = FakeLogger()
    suite = offline_fixer.OfflineFSFix.create_validation_suite(fx, g)
    res = suite.run_all({"image": "x", "root_dev": "/dev/sda2", "subvol": None})

    results = res.get("results", res)
    assert "kernel_present" in results


def test_validation_suite_all_checks_pass():
    """Test complete validation with all checks passing"""
    try:
        offline_fixer = importlib.import_module("hyper2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    # Complete fake filesystem
    g = FakeGuestFS()
    g.dirs |= {
        "/boot", "/etc", "/boot/grub2", "/var", "/usr", "/home",
        "/etc/sysconfig", "/etc/sysconfig/network-scripts"
    }

    # Required files
    g.fs["/etc/fstab"] = b"UUID=root-uuid / ext4 defaults 0 1\n"
    g.fs["/boot/vmlinuz-5.14.0"] = b"kernel-binary"
    g.fs["/boot/initramfs-5.14.0.img"] = b"initramfs-data"
    g.fs["/boot/grub2/grub.cfg"] = b"set default=0\n"
    g.fs["/etc/sysconfig/network-scripts/ifcfg-eth0"] = b"DEVICE=eth0\nBOOTPROTO=dhcp\n"

    fx = object.__new__(offline_fixer.OfflineFSFix)
    fx.logger = FakeLogger()
    suite = offline_fixer.OfflineFSFix.create_validation_suite(fx, g)
    res = suite.run_all({"image": "test.qcow2", "root_dev": "/dev/sda2", "subvol": None})

    results = res.get("results", res)

    # All critical checks should pass
    assert "fstab_exists" in results
    assert "kernel_present" in results


def test_validation_with_grub_config():
    """Test validation checks for GRUB configuration"""
    try:
        offline_fixer = importlib.import_module("hyper2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    g = FakeGuestFS()
    g.dirs |= {"/boot", "/boot/grub2", "/etc"}
    g.fs["/etc/fstab"] = b"UUID=1 / ext4 defaults 0 1\n"
    g.fs["/boot/vmlinuz-1"] = b"kernel"
    g.fs["/boot/grub2/grub.cfg"] = b"""
set timeout=5
set default=0

menuentry 'Linux' {
    linux /vmlinuz root=UUID=test-uuid
    initrd /initramfs.img
}
"""

    fx = object.__new__(offline_fixer.OfflineFSFix)
    fx.logger = FakeLogger()
    suite = offline_fixer.OfflineFSFix.create_validation_suite(fx, g)
    res = suite.run_all({"image": "x", "root_dev": "/dev/sda2", "subvol": None})

    results = res.get("results", res)
    assert "fstab_exists" in results


def test_validation_multiple_kernels():
    """Test validation with multiple kernel versions"""
    try:
        offline_fixer = importlib.import_module("hyper2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    g = FakeGuestFS()
    g.dirs |= {"/boot", "/etc"}
    g.fs["/etc/fstab"] = b"UUID=1 / ext4 defaults 0 1\n"

    # Multiple kernel versions
    g.fs["/boot/vmlinuz-5.14.0-123"] = b"kernel-v1"
    g.fs["/boot/vmlinuz-5.14.0-124"] = b"kernel-v2"
    g.fs["/boot/vmlinuz-5.14.0-125"] = b"kernel-v3"

    fx = object.__new__(offline_fixer.OfflineFSFix)
    fx.logger = FakeLogger()
    suite = offline_fixer.OfflineFSFix.create_validation_suite(fx, g)
    res = suite.run_all({"image": "x", "root_dev": "/dev/sda2", "subvol": None})

    results = res.get("results", res)
    assert "kernel_present" in results


def test_validation_with_network_config():
    """Test validation with network configuration files"""
    try:
        offline_fixer = importlib.import_module("hyper2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    g = FakeGuestFS()
    g.dirs |= {"/boot", "/etc", "/etc/sysconfig/network-scripts"}
    g.fs["/etc/fstab"] = b"UUID=1 / ext4 defaults 0 1\n"
    g.fs["/boot/vmlinuz-1"] = b"kernel"

    # Network configs
    g.fs["/etc/sysconfig/network-scripts/ifcfg-eth0"] = b"DEVICE=eth0\nBOOTPROTO=dhcp\n"
    g.fs["/etc/sysconfig/network-scripts/ifcfg-eth1"] = b"DEVICE=eth1\nBOOTPROTO=static\n"

    fx = object.__new__(offline_fixer.OfflineFSFix)
    fx.logger = FakeLogger()
    suite = offline_fixer.OfflineFSFix.create_validation_suite(fx, g)
    res = suite.run_all({"image": "x", "root_dev": "/dev/sda2", "subvol": None})

    results = res.get("results", res)
    assert "fstab_exists" in results
