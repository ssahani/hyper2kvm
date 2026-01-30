# SPDX-License-Identifier: LGPL-3.0-or-later
"""Systemd service management injector."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

def inject_service_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """Enable, disable, or mask systemd services."""
    logger = getattr(self, "logger", None)
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    config = getattr(self, "service_config_inject", None)
    if config is None:
        return {"injected": False, "reason": "no_config"}
    if not isinstance(config, dict):
        return {"injected": False, "reason": "invalid_config"}

    dry = bool(getattr(self, "dry_run", False))
    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "enabled": [],
        "disabled": [],
        "masked": [],
    }

    enable = config.get("enable", [])
    disable = config.get("disable", [])
    mask = config.get("mask", [])

    if not enable and not disable and not mask:
        return {"injected": False, "reason": "no_config"}

    wants_dir = "/etc/systemd/system/multi-user.target.wants"

    for svc in enable:
        if not svc.endswith(".service"):
            svc += ".service"
        if dry:
            _log("info", f"DRY-RUN: would enable {svc}")
            results["enabled"].append(svc)
        else:
            try:
                for base in ["/usr/lib/systemd/system", "/lib/systemd/system"]:
                    svc_path = f"{base}/{svc}"
                    if g.exists(svc_path):
                        if not g.is_dir(wants_dir):
                            g.mkdir_p(wants_dir)
                        g.ln_sf(svc_path, f"{wants_dir}/{svc}")
                        results["enabled"].append(svc)
                        _log("info", f"Enabled {svc}")
                        break
            except Exception as e:
                _log("warning", f"Failed to enable {svc}: {e}")

    for svc in disable:
        if not svc.endswith(".service"):
            svc += ".service"
        if dry:
            _log("info", f"DRY-RUN: would disable {svc}")
            results["disabled"].append(svc)
        else:
            try:
                link = f"{wants_dir}/{svc}"
                if g.exists(link):
                    g.rm(link)
                results["disabled"].append(svc)
                _log("info", f"Disabled {svc}")
            except Exception as e:
                _log("warning", f"Failed to disable {svc}: {e}")

    for svc in mask:
        if not svc.endswith(".service"):
            svc += ".service"
        if dry:
            _log("info", f"DRY-RUN: would mask {svc}")
            results["masked"].append(svc)
        else:
            try:
                svc_path = f"/etc/systemd/system/{svc}"
                g.ln_sf("/dev/null", svc_path)
                results["masked"].append(svc)
                _log("info", f"Masked {svc}")
            except Exception as e:
                _log("warning", f"Failed to mask {svc}: {e}")

    return results
