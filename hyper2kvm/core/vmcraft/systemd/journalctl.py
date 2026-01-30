# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Journalctl integration for VMCraft.

Provides systemd journal log analysis capabilities.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable


class JournalctlManager:
    """Manage systemd journal via journalctl."""

    def __init__(self, command_runner: Callable[[list[str]], str], logger: logging.Logger):
        """
        Initialize JournalctlManager.

        Args:
            command_runner: Function to execute commands in guest
            logger: Logger instance
        """
        self.command = command_runner
        self.logger = logger

    def query(
        self,
        unit: str | None = None,
        priority: int | None = None,
        since: str | None = None,
        until: str | None = None,
        boot: int | str | None = None,
        lines: int | None = None,
        grep: str | None = None,
        output_format: str = "short"
    ) -> str:
        """
        Query systemd journal logs.

        Args:
            unit: Filter by unit name (e.g., "sshd.service")
            priority: Filter by priority (0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug)
            since: Start time (e.g., "1 hour ago", "yesterday", "2023-01-01")
            until: End time
            boot: Boot ID or offset (0=current, -1=previous, etc.)
            lines: Number of lines to show
            grep: Pattern to grep for
            output_format: Output format (short, json, verbose, cat, etc.)

        Returns:
            Log output as string

        Example:
            # Get SSH logs from last hour
            logs = manager.query(unit="sshd.service", since="1 hour ago")

            # Get all errors
            errors = manager.query(priority=3)

            # Get boot logs
            boot_log = manager.query(boot=0)
        """
        try:
            cmd = ["journalctl", "--no-pager", f"-o{output_format}"]

            if unit:
                cmd.extend(["-u", unit])
            if priority is not None:
                cmd.extend(["-p", str(priority)])
            if since:
                cmd.extend(["--since", since])
            if until:
                cmd.extend(["--until", until])
            if boot is not None:
                cmd.extend(["-b", str(boot)])
            if lines is not None:
                cmd.extend(["-n", str(lines)])
            if grep:
                cmd.extend(["--grep", grep])

            return self.command(cmd)

        except Exception as e:
            self.logger.debug(f"journalctl query failed: {e}")
            return ""

    def list_boots(self) -> list[dict[str, str]]:
        """
        List available boot entries.

        Returns:
            List of dicts with keys: boot_id, first_entry, last_entry

        Example:
            boots = manager.list_boots()
            print(f"Current boot: {boots[0]['boot_id']}")
            print(f"Previous boot: {boots[1]['boot_id']}")
        """
        try:
            cmd = ["journalctl", "--list-boots", "--no-pager"]
            result = self.command(cmd)

            boots = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Format: -1 abc123... 2023-01-01 12:00:00 UTC—2023-01-01 13:00:00 UTC
                parts = line.split(None, 2)
                if len(parts) >= 3:
                    boots.append({
                        "offset": parts[0],
                        "boot_id": parts[1],
                        "time_range": parts[2] if len(parts) > 2 else "",
                    })

            return boots

        except Exception as e:
            self.logger.debug(f"journalctl list-boots failed: {e}")
            return []

    def get_boot_log(self, boot: int | str = 0, lines: int | None = None) -> str:
        """
        Get log for a specific boot.

        Args:
            boot: Boot ID or offset (0=current, -1=previous)
            lines: Number of lines to return

        Returns:
            Boot log as string
        """
        return self.query(boot=boot, lines=lines)

    def get_errors(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """
        Get error messages from journal.

        Args:
            since: Time specification
            lines: Maximum number of errors to return

        Returns:
            List of dicts with keys: timestamp, unit, message, priority

        Example:
            errors = manager.get_errors(since="1 hour ago")
            for err in errors:
                print(f"{err['unit']}: {err['message']}")
        """
        try:
            cmd = ["journalctl", "-p", "err", "--no-pager", "-o", "json", "-n", str(lines)]
            if since:
                cmd.extend(["--since", since])

            result = self.command(cmd)

            errors = []
            for line in result.splitlines():
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    errors.append({
                        "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                        "unit": entry.get("_SYSTEMD_UNIT", entry.get("SYSLOG_IDENTIFIER", "unknown")),
                        "message": entry.get("MESSAGE", ""),
                        "priority": entry.get("PRIORITY", ""),
                    })
                except json.JSONDecodeError:
                    continue

            return errors

        except Exception as e:
            self.logger.debug(f"journalctl get errors failed: {e}")
            return []

    def get_warnings(self, since: str | None = None, lines: int = 100) -> list[dict[str, str]]:
        """
        Get warning messages from journal.

        Args:
            since: Time specification
            lines: Maximum number of warnings to return

        Returns:
            List of dicts with warning information
        """
        try:
            cmd = ["journalctl", "-p", "warning", "--no-pager", "-o", "json", "-n", str(lines)]
            if since:
                cmd.extend(["--since", since])

            result = self.command(cmd)

            warnings = []
            for line in result.splitlines():
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    warnings.append({
                        "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                        "unit": entry.get("_SYSTEMD_UNIT", entry.get("SYSLOG_IDENTIFIER", "unknown")),
                        "message": entry.get("MESSAGE", ""),
                        "priority": entry.get("PRIORITY", ""),
                    })
                except json.JSONDecodeError:
                    continue

            return warnings

        except Exception as e:
            self.logger.debug(f"journalctl get warnings failed: {e}")
            return []

    def disk_usage(self) -> dict[str, Any]:
        """
        Get journal disk usage information.

        Returns:
            Dict with disk usage information
            Keys: total_size, current_use, max_use

        Example:
            usage = manager.disk_usage()
            print(f"Journal size: {usage['current_use']} / {usage['max_use']}")
        """
        try:
            cmd = ["journalctl", "--disk-usage", "--no-pager"]
            result = self.command(cmd)

            usage = {}

            # Parse output like: "Archived and active journals take up 123.4M in the file system."
            import re
            match = re.search(r'(\d+\.?\d*[KMGT]?)\s*(?:in|on)', result)
            if match:
                usage["current_use"] = match.group(1)

            return usage

        except Exception as e:
            self.logger.debug(f"journalctl disk-usage failed: {e}")
            return {}

    def verify(self) -> dict[str, Any]:
        """
        Verify journal file consistency.

        Returns:
            Dict with verification results
            Keys: passed, errors, details

        Example:
            result = manager.verify()
            if not result['passed']:
                print(f"Journal verification failed: {result['errors']}")
        """
        try:
            cmd = ["journalctl", "--verify", "--no-pager"]
            result = self.command(cmd)

            verification = {
                "passed": "PASS" in result.upper(),
                "errors": [],
                "details": result,
            }

            # Extract errors
            for line in result.splitlines():
                if "error" in line.lower() or "fail" in line.lower():
                    verification["errors"].append(line.strip())

            return verification

        except Exception as e:
            self.logger.debug(f"journalctl verify failed: {e}")
            return {"passed": False, "errors": [str(e)], "details": ""}

    def get_cursor(self) -> str:
        """
        Get current journal cursor position.

        Returns:
            Cursor string
        """
        try:
            cmd = ["journalctl", "-n", "1", "--show-cursor", "--no-pager", "-o", "json"]
            result = self.command(cmd)

            # Extract cursor from output
            import re
            match = re.search(r'--cursor.*?([a-zA-Z0-9+/=]+)', result)
            if match:
                return match.group(1)

            return ""

        except Exception as e:
            self.logger.debug(f"journalctl get cursor failed: {e}")
            return ""

    def export(self, output_format: str = "json", since: str | None = None) -> str:
        """
        Export journal logs.

        Args:
            output_format: Export format (json, short, verbose, export, cat)
            since: Export logs since this time

        Returns:
            Exported log data as string

        Example:
            # Export all logs as JSON
            json_logs = manager.export("json")

            # Export last hour
            recent = manager.export("json", since="1 hour ago")
        """
        return self.query(since=since, output_format=output_format)
