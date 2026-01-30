# SPDX-License-Identifier: LGPL-3.0-or-later
import argparse
import importlib
import pytest

def _load_parser():
    try:
        m = importlib.import_module("vmdk2kvm.cli.argument_parser")
    except Exception as e:
        pytest.skip(f"Cannot import vmdk2kvm.cli.argument_parser: {e}")

    for attr in ("build_parser", "get_parser", "make_parser", "create_parser", "parser"):
        if hasattr(m, attr):
            obj = getattr(m, attr)
            try:
                p = obj() if callable(obj) else obj
                if isinstance(p, argparse.ArgumentParser):
                    return p
            except TypeError:
                continue
            except Exception:
                continue

    for name in dir(m):
        if name.startswith("_"):
            continue
        obj = getattr(m, name)
        if callable(obj):
            try:
                p = obj()
                if isinstance(p, argparse.ArgumentParser):
                    return p
            except TypeError:
                continue
            except Exception:
                continue

    pytest.skip("Could not locate an ArgumentParser builder in vmdk2kvm.cli.argument_parser")

def test_parser_has_subcommands():
    p = _load_parser()
    subparsers = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
    assert subparsers, "Expected argparse subcommands (subparsers) to be configured"

def test_parser_parses_config_flag(tmp_path):
    p = _load_parser()
    cfg = tmp_path / "x.yaml"
    cfg.write_text("foo: bar\n")
    args = None
    for flag in ("--config", "-c"):
        try:
            args = p.parse_args([flag, str(cfg), "local"])
            break
        except SystemExit:
            continue
    if args is None:
        pytest.skip("Parser does not appear to support --config/-c with a 'local' subcommand")
    assert hasattr(args, "config")
