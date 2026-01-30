# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/daemon/control.py
"""
Control interface for daemon mode.
Provides runtime control via Unix socket.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any


class DaemonControl:
    """
    Control interface for daemon using Unix socket.

    Supports commands:
    - status: Get daemon status
    - stats: Get statistics
    - pause: Pause processing
    - resume: Resume processing
    - drain: Finish queue and exit
    - stop: Stop immediately
    """

    def __init__(self, logger: logging.Logger, socket_path: Path,
                 get_stats_callback: Callable[[], dict[str, Any]],
                 pause_callback: Callable[[], None],
                 resume_callback: Callable[[], None],
                 stop_callback: Callable[[], None]):
        self.logger = logger
        self.socket_path = socket_path
        self.get_stats_callback = get_stats_callback
        self.pause_callback = pause_callback
        self.resume_callback = resume_callback
        self.stop_callback = stop_callback

        self.socket: socket.socket | None = None
        self.running = False
        self.thread: threading.Thread | None = None

        self.paused = False
        self.draining = False

    def start(self) -> None:
        """Start control socket server."""
        try:
            # Remove existing socket file
            if self.socket_path.exists():
                self.socket_path.unlink()

            # Ensure parent directory exists
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

            # Create Unix socket
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.bind(str(self.socket_path))
            self.socket.listen(1)
            self.socket.settimeout(1.0)

            self.running = True
            self.thread = threading.Thread(target=self._serve, daemon=True)
            self.thread.start()

            self.logger.info(f"🎮 Control socket: {self.socket_path}")

        except Exception as e:
            self.logger.error(f"Failed to start control socket: {e}")

    def stop(self) -> None:
        """Stop control socket server."""
        self.running = False

        if self.thread:
            self.thread.join(timeout=5)

        if self.socket:
            self.socket.close()

        if self.socket_path.exists():
            self.socket_path.unlink()

    def _serve(self) -> None:
        """Serve control requests."""
        while self.running:
            try:
                try:
                    conn, _ = self.socket.accept()
                except TimeoutError:
                    continue

                with conn:
                    data = conn.recv(4096).decode('utf-8').strip()
                    if not data:
                        continue

                    # Parse command
                    try:
                        request = json.loads(data)
                        command = request.get('command', '')
                        response = self._handle_command(command, request)
                    except json.JSONDecodeError:
                        # Fallback: treat as simple command string
                        response = self._handle_command(data, {})

                    # Send response
                    conn.sendall(json.dumps(response).encode('utf-8'))

            except Exception as e:
                self.logger.error(f"Control socket error: {e}")

    def _handle_command(self, command: str, request: dict) -> dict:
        """Handle control command."""
        try:
            if command == 'status':
                return {
                    'status': 'ok',
                    'paused': self.paused,
                    'draining': self.draining,
                }

            elif command == 'stats':
                stats = self.get_stats_callback()
                return {
                    'status': 'ok',
                    'stats': stats,
                }

            elif command == 'pause':
                if not self.paused:
                    self.pause_callback()
                    self.paused = True
                    self.logger.info("⏸️ Daemon paused")
                return {'status': 'ok', 'message': 'Daemon paused'}

            elif command == 'resume':
                if self.paused:
                    self.resume_callback()
                    self.paused = False
                    self.logger.info("▶️ Daemon resumed")
                return {'status': 'ok', 'message': 'Daemon resumed'}

            elif command == 'drain':
                if not self.draining:
                    self.draining = True
                    self.logger.info("🚰 Draining queue, will exit when empty")
                return {'status': 'ok', 'message': 'Draining queue'}

            elif command == 'stop':
                self.logger.info("🛑 Stop command received")
                self.stop_callback()
                return {'status': 'ok', 'message': 'Stopping daemon'}

            else:
                return {
                    'status': 'error',
                    'message': f'Unknown command: {command}',
                    'available_commands': ['status', 'stats', 'pause', 'resume', 'drain', 'stop']
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }


class DaemonControlClient:
    """Client for sending commands to daemon control socket."""

    def __init__(self, socket_path: Path):
        self.socket_path = socket_path

    def send_command(self, command: str, timeout: float = 5.0) -> dict:
        """Send command to daemon."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(str(self.socket_path))

                request = json.dumps({'command': command})
                s.sendall(request.encode('utf-8'))

                response_data = s.recv(4096).decode('utf-8')
                return json.loads(response_data)

        except FileNotFoundError:
            return {
                'status': 'error',
                'message': f'Daemon not running (socket not found: {self.socket_path})'
            }
        except TimeoutError:
            return {
                'status': 'error',
                'message': 'Command timeout'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
