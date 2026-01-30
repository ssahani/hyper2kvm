# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib
import pytest

from fakes.fake_guestfs import FakeGuestFS
from fakes.fake_logger import FakeLogger

def test_validation_suite_basic_checks():
    try:
        offline_fixer = importlib.import_module("vmdk2kvm.fixers.offline_fixer")
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
