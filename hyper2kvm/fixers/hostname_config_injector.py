# SPDX-License-Identifier: LGPL-3.0-or-later
"""Hostname and hosts file configuration injector."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...

def inject_hostname_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """Configure hostname, domain, and /etc/hosts."""
    logger = getattr(self, "logger", None)
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    config = getattr(self, "hostname_config_inject", None)
    if config is None:
        return {"injected": False, "reason": "no_config"}
    if not isinstance(config, dict):
        return {"injected": False, "reason": "invalid_config"}

    dry = bool(getattr(self, "dry_run", False))
    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "hostname_set": False,
        "hosts_entries_added": 0,
    }

    hostname = config.get("hostname")
    domain = config.get("domain")
    hosts = config.get("hosts", {})

    if not hostname and not hosts:
        return {"injected": False, "reason": "no_config"}

    # Set hostname
    if hostname:
        if dry:
            _log("info", f"DRY-RUN: would set hostname to {hostname}")
            results["hostname_set"] = True
        else:
            try:
                # Write /etc/hostname
                g.write("/etc/hostname", f"{hostname}\n".encode("utf-8"))
                
                # Update /etc/hosts
                if g.is_file("/etc/hosts"):
                    hosts_content = g.read_file("/etc/hosts").decode("utf-8")
                else:
                    hosts_content = ""
                
                lines = hosts_content.splitlines()
                new_lines = []
                updated_127 = False
                
                for line in lines:
                    if line.strip().startswith("127.0.1.1"):
                        fqdn = f"{hostname}.{domain}" if domain else hostname
                        new_lines.append(f"127.0.1.1\t{fqdn} {hostname}")
                        updated_127 = True
                    else:
                        new_lines.append(line)
                
                if not updated_127:
                    fqdn = f"{hostname}.{domain}" if domain else hostname
                    new_lines.insert(1, f"127.0.1.1\t{fqdn} {hostname}")
                
                g.write("/etc/hosts", "\n".join(new_lines).encode("utf-8"))
                results["hostname_set"] = True
                _log("info", f"Set hostname to {hostname}")
            except Exception as e:
                _log("error", f"Failed to set hostname: {e}")

    # Add custom hosts entries
    if hosts:
        if dry:
            results["hosts_entries_added"] = len(hosts)
        else:
            try:
                if g.is_file("/etc/hosts"):
                    hosts_content = g.read_file("/etc/hosts").decode("utf-8")
                else:
                    hosts_content = "127.0.0.1\tlocalhost\n"
                
                for ip, names in hosts.items():
                    hosts_content += f"{ip}\t{names}\n"
                    results["hosts_entries_added"] += 1
                
                g.write("/etc/hosts", hosts_content.encode("utf-8"))
                _log("info", f"Added {len(hosts)} hosts entries")
            except Exception as e:
                _log("error", f"Failed to update hosts: {e}")

    return results
