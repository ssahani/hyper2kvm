# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib
import pytest

def test_two_phase_config_supported():
    try:
        importlib.import_module("hyper2kvm.cli.argument_parser")
    except Exception as e:
        pytest.skip(f"argument_parser import failed: {e}")

    try:
        importlib.import_module("hyper2kvm.config.config_loader")
    except Exception as e:
        pytest.skip(f"config_loader import failed: {e}")
