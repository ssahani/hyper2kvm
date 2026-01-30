# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/cli/args/parser.py
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from ...config.config_loader import Config
from ...core.logger import c
from ...core.utils import U
from .builder import HelpFormatter, _build_epilog
from .groups import (
    _add_ami_extraction_knobs,
    _add_azure_knobs,
    _add_batch_knobs,
    _add_daemon_flags,
    _add_domain_emission,
    _add_fixing_behavior,
    _add_flatten_convert,
    _add_global_config_logging,
    _add_global_operation_flags,
    _add_govc_knobs,
    _add_input_paths,
    _add_libvirt_xml_knobs,
    _add_luks_knobs,
    _add_ovf_ova_knobs,
    _add_ovftool_knobs,
    _add_project_control,
    _add_ssh_fetch_knobs,
    _add_systemd_gen,
    _add_tests,
    _add_vsphere_core_knobs,
    _add_vsphere_export_and_download_knobs,
    _add_windows_network_override,
    _add_windows_virtio_definitions,
)
from .helpers import (
    _materialize_virtio_config_json_if_needed,
    _materialize_win_net_json_if_needed,
)
from .validators import validate_args


def build_parser() -> argparse.ArgumentParser:
    epilog = _build_epilog()

    p = argparse.ArgumentParser(
        description=c("hyper2kvm: Ultimate VMware → KVM/QEMU Converter + Fixer", "green", ["bold"]),
        formatter_class=HelpFormatter,
        epilog=epilog,
    )

    _add_global_config_logging(p)
    _add_project_control(p)
    _add_global_operation_flags(p)

    _add_flatten_convert(p)
    _add_fixing_behavior(p)
    _add_windows_virtio_definitions(p)
    _add_windows_network_override(p)
    _add_luks_knobs(p)

    _add_tests(p)
    _add_domain_emission(p)

    _add_batch_knobs(p)
    _add_daemon_flags(p)
    _add_ovf_ova_knobs(p)
    _add_ami_extraction_knobs(p)
    _add_libvirt_xml_knobs(p)

    _add_input_paths(p)
    _add_ssh_fetch_knobs(p)
    _add_systemd_gen(p)

    _add_vsphere_core_knobs(p)
    _add_govc_knobs(p)
    _add_ovftool_knobs(p)
    _add_vsphere_export_and_download_knobs(p)

    _add_azure_knobs(p)

    return p


def _build_preparser() -> argparse.ArgumentParser:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", action="append", default=[])
    pre.add_argument("-v", "--verbose", action="count", default=0)
    pre.add_argument("--log-file", dest="log_file", default=None)
    pre.add_argument("--dump-config", action="store_true")
    pre.add_argument("--dump-args", action="store_true")
    return pre


def _load_merged_config(logger: Any, cfgs: Sequence[str]) -> dict[str, Any]:
    if not cfgs:
        return {}
    expanded = Config.expand_configs(logger, list(cfgs))
    return Config.load_many(logger, expanded)


def parse_args_with_config(
    argv: Sequence[str] | None = None,
    logger: Any = None,
) -> tuple[argparse.Namespace, dict[str, Any], Any]:
    """
    New-project policy:
      - No CLI subcommands.
      - YAML drives `cmd` and (for vsphere) `vs_action`.
      - CLI provides overrides/toggles.

    Flow:
      Phase 0: parse ONLY global flags needed to locate config/logging
      Phase 1: load+merge config files
      Phase 2: apply config as defaults onto the parser
      Phase 3: full parse to get final args
      Phase 4: validate using merged config + args
      Phase 5: materialize inline JSON overrides into workdir (side-effect, after validation)
    """
    import sys

    # Enable shell completion via argcomplete if available
    try:
        import argcomplete
        _ARGCOMPLETE_AVAILABLE = True
    except ImportError:
        _ARGCOMPLETE_AVAILABLE = False

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)

    parser = build_parser()

    # Enable argcomplete for shell completion
    if _ARGCOMPLETE_AVAILABLE:
        argcomplete.autocomplete(parser)

    pre = _build_preparser()
    args0, _rest = pre.parse_known_args(argv)

    if logger is None:
        from ...core.logger import Log  # local import to avoid cycles

        logger = Log.setup(getattr(args0, "verbose", 0), getattr(args0, "log_file", None))

    conf = _load_merged_config(logger, getattr(args0, "config", None) or [])

    if getattr(args0, "dump_config", False):
        print(U.json_dump(conf))
        raise SystemExit(0)

    # Apply config as defaults so CLI can override.
    Config.apply_as_defaults(logger, parser, conf)

    args = parser.parse_args(argv)

    if getattr(args0, "dump_args", False):
        print(U.json_dump(vars(args)))
        raise SystemExit(0)

    validate_args(args, conf)

    # Side-effect stage: if win_net_json is used, write it under workdir and set args.win_net_override.
    _materialize_win_net_json_if_needed(args, conf, logger)

    # Side-effect stage: if virtio_config_json is used, write it under workdir and set args.virtio_config_path.
    _materialize_virtio_config_json_if_needed(args, conf, logger)

    return args, conf, logger
