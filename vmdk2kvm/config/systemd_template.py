# SPDX-License-Identifier: LGPL-3.0-or-later
from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..core.utils import U

# Keep this template in one place so both CLI help and generator use the same text.
# We use Python .format_map() so we can inject safe, quoted values.
SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=vmdk2kvm Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python} {script} --daemon --watch-dir={watch_dir} --config={config} {extra_args}
Restart=always
RestartSec=3
User={user}
Group={group}
WorkingDirectory={workdir}
Environment=PYTHONUNBUFFERED=1
# (Optional) load environment overrides, secrets, proxies, etc.
EnvironmentFile=-{env_file}
# Hardening (safe defaults; relax if you need device access beyond libvirt/qemu)
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectControlGroups=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
LockPersonality=true
RestrictRealtime=true
RestrictSUIDSGID=true
RemoveIPC=true
UMask=0022
# Write access only where needed
ReadWritePaths={rw_paths}

# If you rely on libguestfs/qemu/libvirt, you may need to loosen some of these.
# E.g. uncomment:
# DeviceAllow=/dev/kvm r
# DeviceAllow=/dev/nbd* rw
# SupplementaryGroups=libvirt,kvm

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def _q(s: str) -> str:
    """Shell-quote for systemd ExecStart arguments."""
    return shlex.quote(s)


@dataclass
class SystemdUnitParams:
    python: str
    script: str
    watch_dir: str
    config: str
    user: str = "root"
    group: str = "root"
    workdir: str = "/"
    env_file: str = "/etc/default/vmdk2kvm"
    rw_paths: str = "/var/lib/vmdk2kvm /var/log/vmdk2kvm /tmp"
    extra_args: str = ""


def _infer_defaults(args: Any) -> SystemdUnitParams:
    """
    Infer sensible defaults from args, with fallbacks.
    We quote values for ExecStart safety.
    """
    python = getattr(args, "python", None) or "/usr/bin/python3"
    script = getattr(args, "script", None) or getattr(args, "entrypoint", None) or "/path/to/vmdk2kvm.py"
    watch_dir = getattr(args, "watch_dir", None) or "/path/to/watch"
    config = getattr(args, "config", None) or "/path/to/config.yaml"

    user = getattr(args, "user", None) or "root"
    group = getattr(args, "group", None) or user
    workdir = getattr(args, "workdir", None) or "/"
    env_file = getattr(args, "env_file", None) or "/etc/default/vmdk2kvm"

    # Read/write paths: allow user to pass a list or a string
    rw = getattr(args, "rw_paths", None)
    if isinstance(rw, (list, tuple)):
        rw_paths = " ".join(str(x) for x in rw)
    elif isinstance(rw, str) and rw.strip():
        rw_paths = rw.strip()
    else:
        rw_paths = "/var/lib/vmdk2kvm /var/log/vmdk2kvm /tmp"

    extra = getattr(args, "extra_args", None) or ""
    extra_args = extra.strip()

    return SystemdUnitParams(
        python=_q(str(python)),
        script=_q(str(script)),
        watch_dir=_q(str(watch_dir)),
        config=_q(str(config)),
        user=str(user),
        group=str(group),
        workdir=str(workdir),
        env_file=str(env_file),
        rw_paths=str(rw_paths),
        extra_args=extra_args,
    )


def generate_systemd_unit(args: Any, logger=None) -> None:
    """
    Print or write a sample systemd unit file.

    Enhancements:
      - fills template with values from args (python/script/watch_dir/config/user/group/...)
      - supports atomic write to output file
      - creates parent dir when writing
      - logs next-step instructions
      - avoids dangerous unquoted ExecStart arguments
    """
    params = _infer_defaults(args)

    unit = SYSTEMD_UNIT_TEMPLATE.format_map(
        {
            "python": params.python,
            "script": params.script,
            "watch_dir": params.watch_dir,
            "config": params.config,
            "extra_args": params.extra_args,
            "user": params.user,
            "group": params.group,
            "workdir": params.workdir,
            "env_file": params.env_file,
            "rw_paths": params.rw_paths,
        }
    )

    out = getattr(args, "output", None)
    if out:
        out_path = Path(out).expanduser()
        U.ensure_dir(out_path.parent)

        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(unit, encoding="utf-8")
        tmp.replace(out_path)

        if logger:
            logger.info(f"Systemd unit written to {out_path}")
            # Helpful next steps (no assumptions about distro, but generally correct)
            name = out_path.name
            logger.info(f"Next steps:")
            logger.info(f"  sudo install -m 0644 {out_path} /etc/systemd/system/{name}")
            logger.info(f"  sudo systemctl daemon-reload")
            logger.info(f"  sudo systemctl enable --now {name.replace('.service','')}.service")
        return

    # No output path: print to stdout
    print(unit)
