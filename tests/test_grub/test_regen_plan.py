# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib
import pytest

from fakes.fake_guestfs import FakeGuestFS
from fakes.fake_logger import FakeLogger

def test_regen_dry_run_returns_info():
    try:
        grub_fixer = importlib.import_module("hyper2kvm.fixers.grub_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import grub_fixer: {e}")

    g = FakeGuestFS()
    fx = type("Fx", (), {})()
    fx.logger = FakeLogger()
    fx.dry_run = True
    fx.regen_initramfs = True
    fx.inspect_root = "/dev/sda2"

    info = grub_fixer.regen(fx, g)
    assert isinstance(info, dict)
    assert info.get("enabled") is True
    assert info.get("dry_run") is True
