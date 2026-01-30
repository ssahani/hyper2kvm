# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Systemctl integration for VMCraft.

Provides service management and inspection capabilities.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable


class SystemctlManager:
    """Manage systemd services via systemctl."""

    def __init__(self, command_runner: Callable[[list[str]], str], logger: logging.Logger):
        """
        Initialize SystemctlManager.

        Args:
            command_runner: Function to execute commands in guest (e.g., VMCraft.command_quiet)
            logger: Logger instance
        """
        self.command = command_runner
        self.logger = logger

    def list_units(
        self,
        unit_type: str = "service",
        state: str | None = None,
        all_units: bool = True
    ) -> list[dict[str, str]]:
        """
        List systemd units.

        Args:
            unit_type: Type of unit (service, timer, socket, target, mount, etc.)
            state: Filter by state (active, inactive, failed, running, etc.)
            all_units: Include inactive units (default: True)

        Returns:
            List of dicts with keys: unit, load, active, sub, description

        Example:
            services = manager.list_units("service", "active")
            for svc in services:
                print(f"{svc['unit']}: {svc['description']}")
        """
        try:
            cmd = ["systemctl", "list-units", f"--type={unit_type}", "--no-pager", "--plain", "--no-legend"]
            if all_units:
                cmd.append("--all")
            if state:
                cmd.append(f"--state={state}")

            result = self.command(cmd)

            units = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Parse systemctl output
                # Format: UNIT  LOAD  ACTIVE  SUB  DESCRIPTION
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    units.append({
                        "unit": parts[0],
                        "load": parts[1],
                        "active": parts[2],
                        "sub": parts[3],
                        "description": parts[4],
                    })
                elif len(parts) >= 4:
                    units.append({
                        "unit": parts[0],
                        "load": parts[1],
                        "active": parts[2],
                        "sub": parts[3],
                        "description": "",
                    })

            return units

        except Exception as e:
            self.logger.debug(f"systemctl list-units failed: {e}")
            return []

    def list_unit_files(self, unit_type: str = "service") -> list[dict[str, str]]:
        """
        List installed unit files.

        Args:
            unit_type: Type of unit file to list

        Returns:
            List of dicts with keys: unit_file, state

        Example:
            unit_files = manager.list_unit_files("service")
            enabled = [u for u in unit_files if u['state'] == 'enabled']
        """
        try:
            cmd = ["systemctl", "list-unit-files", f"--type={unit_type}", "--no-pager", "--plain", "--no-legend"]
            result = self.command(cmd)

            unit_files = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 1)
                if len(parts) >= 2:
                    unit_files.append({
                        "unit_file": parts[0],
                        "state": parts[1],
                    })

            return unit_files

        except Exception as e:
            self.logger.debug(f"systemctl list-unit-files failed: {e}")
            return []

    def is_active(self, unit: str) -> bool:
        """
        Check if a unit is active.

        Args:
            unit: Unit name (e.g., "sshd.service")

        Returns:
            True if active, False otherwise
        """
        try:
            cmd = ["systemctl", "is-active", unit]
            result = self.command(cmd)
            return result.strip() == "active"
        except Exception:
            return False

    def is_enabled(self, unit: str) -> str:
        """
        Check if a unit is enabled.

        Args:
            unit: Unit name

        Returns:
            State string: "enabled", "disabled", "static", "masked", "generated", etc.
        """
        try:
            cmd = ["systemctl", "is-enabled", unit]
            result = self.command(cmd)
            return result.strip()
        except Exception:
            return "unknown"

    def is_failed(self, unit: str) -> bool:
        """
        Check if a unit is in failed state.

        Args:
            unit: Unit name

        Returns:
            True if failed, False otherwise
        """
        try:
            cmd = ["systemctl", "is-failed", unit]
            result = self.command(cmd)
            return result.strip() == "failed"
        except Exception:
            return False

    def show(self, unit: str) -> dict[str, str]:
        """
        Show properties of a unit.

        Args:
            unit: Unit name

        Returns:
            Dict of unit properties

        Example:
            props = manager.show("sshd.service")
            print(f"Main PID: {props.get('MainPID')}")
            print(f"Memory: {props.get('MemoryCurrent')}")
        """
        try:
            cmd = ["systemctl", "show", unit, "--no-pager"]
            result = self.command(cmd)

            properties = {}
            for line in result.splitlines():
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    properties[key] = value

            return properties

        except Exception as e:
            self.logger.debug(f"systemctl show failed for {unit}: {e}")
            return {}

    def status(self, unit: str) -> dict[str, Any]:
        """
        Get detailed status of a unit.

        Args:
            unit: Unit name

        Returns:
            Dict with keys: active, sub, main_pid, status_text, recent_logs

        Example:
            status = manager.status("nginx.service")
            print(f"Active: {status['active']}")
            print(f"PID: {status['main_pid']}")
        """
        try:
            cmd = ["systemctl", "status", unit, "--no-pager", "--lines=10"]
            result = self.command(cmd)

            status_info = {
                "active": "unknown",
                "sub": "unknown",
                "main_pid": "",
                "status_text": result,
                "recent_logs": [],
            }

            # Parse status output
            for line in result.splitlines():
                line = line.strip()

                # Active line: "Active: active (running) since ..."
                if line.startswith("Active:"):
                    match = re.search(r'Active:\s+(\w+)\s+\((\w+)\)', line)
                    if match:
                        status_info["active"] = match.group(1)
                        status_info["sub"] = match.group(2)

                # Main PID line: "Main PID: 1234 (nginx)"
                elif line.startswith("Main PID:"):
                    match = re.search(r'Main PID:\s+(\d+)', line)
                    if match:
                        status_info["main_pid"] = match.group(1)

                # Log lines
                elif line.startswith("├─") or line.startswith("└─") or line.startswith("│"):
                    status_info["recent_logs"].append(line)

            return status_info

        except Exception as e:
            self.logger.debug(f"systemctl status failed for {unit}: {e}")
            return {
                "active": "unknown",
                "sub": "unknown",
                "main_pid": "",
                "status_text": "",
                "recent_logs": [],
            }

    def cat(self, unit: str) -> str:
        """
        Show unit file content.

        Args:
            unit: Unit name

        Returns:
            Unit file content as string
        """
        try:
            cmd = ["systemctl", "cat", unit, "--no-pager"]
            return self.command(cmd)
        except Exception as e:
            self.logger.debug(f"systemctl cat failed for {unit}: {e}")
            return ""

    def list_dependencies(self, unit: str, reverse: bool = False, recursive: bool = True) -> list[str]:
        """
        List unit dependencies.

        Args:
            unit: Unit name
            reverse: Show reverse dependencies (what depends on this unit)
            recursive: Show all recursive dependencies (default: True)

        Returns:
            List of dependency unit names

        Example:
            deps = manager.list_dependencies("nginx.service")
            print(f"nginx depends on: {deps}")

            rdeps = manager.list_dependencies("network.target", reverse=True)
            print(f"Services needing network: {rdeps}")
        """
        try:
            cmd = ["systemctl", "list-dependencies", unit, "--no-pager", "--plain"]
            if reverse:
                cmd.append("--reverse")
            if not recursive:
                cmd.append("--no-recursion")

            result = self.command(cmd)

            dependencies = []
            for line in result.splitlines():
                line = line.strip()
                if not line or line == unit:
                    continue

                # Remove tree characters
                line = re.sub(r'^[●├─└│\s]+', '', line)
                if line:
                    dependencies.append(line)

            return dependencies

        except Exception as e:
            self.logger.debug(f"systemctl list-dependencies failed for {unit}: {e}")
            return []

    def list_failed(self) -> list[dict[str, str]]:
        """
        List all failed units.

        Returns:
            List of dicts with failed unit information

        Example:
            failed = manager.list_failed()
            if failed:
                print(f"⚠️  {len(failed)} services failed!")
                for unit in failed:
                    print(f"  - {unit['unit']}: {unit['description']}")
        """
        try:
            cmd = ["systemctl", "list-units", "--state=failed", "--no-pager", "--plain", "--no-legend"]
            result = self.command(cmd)

            failed_units = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 4)
                if len(parts) >= 5:
                    failed_units.append({
                        "unit": parts[0],
                        "load": parts[1],
                        "active": parts[2],
                        "sub": parts[3],
                        "description": parts[4],
                    })

            return failed_units

        except Exception as e:
            self.logger.debug(f"systemctl list failed units: {e}")
            return []

    def get_default_target(self) -> str:
        """
        Get the default boot target.

        Returns:
            Default target name (e.g., "multi-user.target", "graphical.target")
        """
        try:
            cmd = ["systemctl", "get-default"]
            result = self.command(cmd)
            return result.strip()
        except Exception:
            return ""

    def list_targets(self) -> list[str]:
        """
        List all available targets.

        Returns:
            List of target names
        """
        try:
            cmd = ["systemctl", "list-units", "--type=target", "--all", "--no-pager", "--plain", "--no-legend"]
            result = self.command(cmd)

            targets = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 1)
                if parts:
                    targets.append(parts[0])

            return targets

        except Exception as e:
            self.logger.debug(f"systemctl list targets failed: {e}")
            return []

    def list_timers(self) -> list[dict[str, str]]:
        """
        List systemd timers.

        Returns:
            List of dicts with timer information
            Keys: next, left, last, passed, unit, activates

        Example:
            timers = manager.list_timers()
            for timer in timers:
                print(f"{timer['unit']} next run: {timer['next']}")
        """
        try:
            cmd = ["systemctl", "list-timers", "--all", "--no-pager", "--plain", "--no-legend"]
            result = self.command(cmd)

            timers = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Format: NEXT  LEFT  LAST  PASSED  UNIT  ACTIVATES
                parts = line.split(None, 5)
                if len(parts) >= 6:
                    timers.append({
                        "next": parts[0],
                        "left": parts[1],
                        "last": parts[2],
                        "passed": parts[3],
                        "unit": parts[4],
                        "activates": parts[5],
                    })

            return timers

        except Exception as e:
            self.logger.debug(f"systemctl list-timers failed: {e}")
            return []

    def list_sockets(self) -> list[dict[str, str]]:
        """
        List systemd socket units.

        Returns:
            List of dicts with socket information
        """
        return self.list_units("socket", all_units=True)

    def list_mounts(self) -> list[dict[str, str]]:
        """
        List systemd mount units.

        Returns:
            List of dicts with mount information
        """
        return self.list_units("mount", all_units=True)
