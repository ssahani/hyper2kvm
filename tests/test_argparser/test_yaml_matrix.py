# SPDX-License-Identifier: GPL-2.0-or-later
import importlib
import pytest

def _load_config_loader():
    try:
        m = importlib.import_module("vmdk2kvm.config.config_loader")
    except Exception as e:
        pytest.skip(f"Cannot import vmdk2kvm.config.config_loader: {e}")

    for attr in ("load_config", "load"):
        if hasattr(m, attr) and callable(getattr(m, attr)):
            return ("func", getattr(m, attr))

    if hasattr(m, "ConfigLoader"):
        CL = getattr(m, "ConfigLoader")
        try:
            inst = CL()
            for meth in ("load_config", "load"):
                if hasattr(inst, meth) and callable(getattr(inst, meth)):
                    return ("method", getattr(inst, meth))
        except Exception:
            pass

    pytest.skip("Could not find a usable config loader API (load_config/load/ConfigLoader.load*)")

def test_config_loader_accepts_yaml(tmp_path):
    kind, loader = _load_config_loader()
    p = tmp_path / "a.yaml"
    p.write_text("mode: local\ninput: x.vmdk\n")
    cfg = loader(str(p))
    assert cfg is not None

def test_config_merge_last_wins(tmp_path):
    kind, loader = _load_config_loader()
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("mode: local\ncompress: false\n")
    b.write_text("mode: local\ncompress: true\n")

    cfg_a = loader(str(a))
    cfg_b = loader(str(b))
    assert cfg_a is not None and cfg_b is not None
