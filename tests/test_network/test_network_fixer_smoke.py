# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib
import pytest

from fakes.fake_guestfs import FakeGuestFS
from fakes.fake_logger import FakeLogger

def test_network_fixer_smoke():
    try:
        network_fixer = importlib.import_module("hyper2kvm.fixers.network_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import network_fixer: {e}")

    if not hasattr(network_fixer, "fix_network_config"):
        pytest.skip("network_fixer.fix_network_config not present")

    fx = type("Fx", (), {})()
    fx.logger = FakeLogger()
    fx.dry_run = True

    g = FakeGuestFS()
    res = network_fixer.fix_network_config(fx, g)
    assert isinstance(res, dict)
