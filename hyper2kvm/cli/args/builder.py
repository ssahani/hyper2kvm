# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/cli/args/builder.py
from __future__ import annotations

import argparse

from ...config.systemd_template import SYSTEMD_UNIT_TEMPLATE
from ...core.logger import c
from ..help_texts import FEATURE_SUMMARY, SYSTEMD_EXAMPLE, YAML_EXAMPLE


class HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    """Combines raw description formatting with default value display in help."""



def _build_epilog() -> str:
    return (
        c("YAML examples:\n", "cyan", ["bold"])
        + c(YAML_EXAMPLE, "cyan")
        + "\n"
        + c("Feature summary:\n", "cyan", ["bold"])
        + c(FEATURE_SUMMARY, "cyan")
        + c("\nSystemd Service Example:\n", "cyan", ["bold"])
        + c(SYSTEMD_UNIT_TEMPLATE + SYSTEMD_EXAMPLE, "cyan")
    )
