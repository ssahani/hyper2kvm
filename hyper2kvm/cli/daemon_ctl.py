# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/cli/daemon_ctl.py
"""
CLI tool for controlling hyper2kvm daemon.

Commands:
    status  - Get daemon status
    stats   - Get statistics
    pause   - Pause processing
    resume  - Resume processing
    drain   - Finish queue and exit
    stop    - Stop daemon
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..daemon.control import DaemonControlClient


def main() -> None:
    """Main entry point for daemon control CLI."""
    parser = argparse.ArgumentParser(
        description='Control hyper2kvm daemon',
        epilog='Example: hyper2kvm-daemon-ctl --socket /path/to/control.sock status'
    )

    parser.add_argument(
        '--socket',
        type=Path,
        help='Path to daemon control socket (default: auto-detect from output_dir/.daemon/control.sock)'
    )

    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('/var/lib/hyper2kvm/output'),
        help='Daemon output directory (used to auto-detect socket)'
    )

    parser.add_argument(
        'command',
        choices=['status', 'stats', 'pause', 'resume', 'drain', 'stop'],
        help='Command to send to daemon'
    )

    parser.add_argument(
        '--json',
        action='store_true',
        help='Output in JSON format'
    )

    args = parser.parse_args()

    # Determine socket path
    if args.socket:
        socket_path = args.socket
    else:
        socket_path = args.output_dir / '.daemon' / 'control.sock'

    if not socket_path.exists():
        print(f"Error: Daemon control socket not found: {socket_path}", file=sys.stderr)
        print("Is the daemon running?", file=sys.stderr)
        sys.exit(1)

    # Send command
    client = DaemonControlClient(socket_path)
    response = client.send_command(args.command)

    # Handle response
    if args.json:
        print(json.dumps(response, indent=2))
    else:
        if response.get('status') == 'ok':
            print(f"✅ {response.get('message', 'Success')}")

            # Print stats if available
            if 'stats' in response:
                stats = response['stats']
                print("\n📊 Daemon Statistics:")
                print(f"  Uptime: {stats.get('uptime_hours', 0):.1f} hours")
                print(f"  Processed: {stats.get('total_processed', 0)}")
                print(f"  Failed: {stats.get('total_failed', 0)}")
                print(f"  Success Rate: {stats.get('success_rate_percent', 0):.1f}%")
                print(f"  Avg Processing Time: {stats.get('average_processing_time_seconds', 0):.1f}s")
                print(f"  Queue Depth: {stats.get('current_queue_depth', 0)}")

                if stats.get('by_file_type'):
                    print("\n  By File Type:")
                    for file_type, type_stats in stats['by_file_type'].items():
                        print(f"    {file_type}: {type_stats['processed']} ok, "
                              f"{type_stats['failed']} failed, "
                              f"{type_stats['success_rate_percent']}% success")

            # Print status if available
            if 'paused' in response:
                status_text = "⏸️  PAUSED" if response['paused'] else "▶️  RUNNING"
                print(f"\n  Status: {status_text}")

            if 'draining' in response and response['draining']:
                print("  Mode: 🚰 DRAINING")

        else:
            print(f"❌ Error: {response.get('message', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
