# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/daemon/daemon_watcher.py
"""
Daemon mode file watcher.
Monitors a directory for new VM disk files and processes them automatically.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path
from queue import Queue, Empty
from threading import Event
from typing import Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from ..core.logger import Log
from ..core.utils import U


class VMFileHandler(FileSystemEventHandler):
    """
    Watches for new VM disk files and queues them for processing.

    Supported file extensions:
    - .vmdk (VMware)
    - .ova, .ovf (OVF archives)
    - .vhd, .vhdx (Hyper-V)
    - .raw, .img (Raw disk images)
    - .ami (AWS AMI images)
    """

    SUPPORTED_EXTENSIONS = {'.vmdk', '.ova', '.ovf', '.vhd', '.vhdx', '.raw', '.img', '.ami'}

    def __init__(self, logger: logging.Logger, queue: Queue, watch_dir: Path):
        super().__init__()
        self.logger = logger
        self.queue = queue
        self.watch_dir = watch_dir
        self.processing: Set[str] = set()
        self.processed: Set[str] = set()

    def _is_valid_file(self, path: Path) -> bool:
        """Check if file is a supported VM disk file."""
        if not path.is_file():
            return False
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False
        if str(path) in self.processing or str(path) in self.processed:
            return False
        return True

    def _queue_file(self, path: Path) -> None:
        """Add file to processing queue."""
        if self._is_valid_file(path):
            Log.trace(self.logger, f"📥 Queuing file: {path.name}")
            self.queue.put(path)
            self.processing.add(str(path))
            self.logger.info(f"📥 New file queued: {path.name}")

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        path = Path(event.src_path)
        # Wait a bit to ensure file is fully written
        time.sleep(1)
        self._queue_file(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move events (e.g., mv from temp location)."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        time.sleep(1)
        self._queue_file(path)

    def mark_completed(self, path: Path) -> None:
        """Mark file as processed."""
        self.processing.discard(str(path))
        self.processed.add(str(path))


class DaemonWatcher:
    """
    Daemon mode file watcher.

    Monitors a watch directory for new VM disk files and processes them
    through the hyper2kvm conversion pipeline.
    """

    def __init__(self, logger: logging.Logger, args: argparse.Namespace):
        self.logger = logger
        self.args = args
        self.watch_dir = Path(args.watch_dir).expanduser().resolve()
        self.output_dir = Path(args.output_dir).expanduser().resolve()
        self.queue: Queue = Queue()
        self.stop_event = Event()
        self.observer: Optional[Observer] = None
        self.handler: Optional[VMFileHandler] = None

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"🛑 Received {sig_name}, shutting down gracefully...")
        self.stop()

    def _validate_directories(self) -> None:
        """Validate watch and output directories."""
        if not self.watch_dir.exists():
            Log.trace(self.logger, f"Creating watch directory: {self.watch_dir}")
            U.ensure_dir(self.watch_dir)

        if not self.watch_dir.is_dir():
            U.die(self.logger, f"Watch path is not a directory: {self.watch_dir}", 1)

        if not self.output_dir.exists():
            Log.trace(self.logger, f"Creating output directory: {self.output_dir}")
            U.ensure_dir(self.output_dir)

        if not self.output_dir.is_dir():
            U.die(self.logger, f"Output path is not a directory: {self.output_dir}", 1)

    def _process_file(self, file_path: Path) -> None:
        """
        Process a single VM disk file through the conversion pipeline.

        Args:
            file_path: Path to the VM disk file
        """
        try:
            self.logger.info(f"🔄 Processing: {file_path.name}")

            # Determine file type and set appropriate command
            ext = file_path.suffix.lower()
            if ext == '.vmdk':
                cmd = 'local'
            elif ext in {'.ova'}:
                cmd = 'ova'
            elif ext == '.ovf':
                cmd = 'ovf'
            elif ext in {'.vhd', '.vhdx'}:
                cmd = 'vhd'
            elif ext in {'.raw', '.img'}:
                cmd = 'raw'
            elif ext == '.ami':
                cmd = 'ami'
            else:
                self.logger.warning(f"⚠️ Unknown file type: {ext}, skipping {file_path.name}")
                return

            # Create a new args namespace for this file
            file_args = argparse.Namespace(**vars(self.args))
            file_args.cmd = cmd

            # Set the input file path based on command type
            if cmd == 'local':
                file_args.vmdk = str(file_path)
            elif cmd == 'ova':
                file_args.ova = str(file_path)
            elif cmd == 'ovf':
                file_args.ovf = str(file_path)
            elif cmd == 'vhd':
                file_args.vhd = str(file_path)
            elif cmd == 'raw':
                file_args.raw = str(file_path)
            elif cmd == 'ami':
                file_args.ami = str(file_path)

            # Create output directory for this file
            file_output_dir = self.output_dir / file_path.stem
            file_args.output_dir = str(file_output_dir)
            U.ensure_dir(file_output_dir)

            # Import here to avoid circular dependency
            from ..orchestrator.orchestrator import Orchestrator

            # Run the conversion pipeline
            Log.step(self.logger, f"Converting: {file_path.name} → {file_output_dir}")
            orchestrator = Orchestrator(self.logger, file_args)
            orchestrator.run()

            self.logger.info(f"✅ Completed: {file_path.name}")

            # Optionally move processed file to archive directory
            if getattr(self.args, 'archive_processed', False):
                archive_dir = self.watch_dir / '.processed'
                U.ensure_dir(archive_dir)
                archive_path = archive_dir / file_path.name
                file_path.rename(archive_path)
                Log.trace(self.logger, f"📦 Archived: {file_path.name} → {archive_path}")

        except Exception as e:
            self.logger.error(f"❌ Failed to process {file_path.name}: {e}")
            self.logger.debug("💥 Processing exception", exc_info=True)

            # Move failed file to error directory
            error_dir = self.watch_dir / '.errors'
            U.ensure_dir(error_dir)
            error_path = error_dir / file_path.name
            try:
                file_path.rename(error_path)
                Log.trace(self.logger, f"📛 Moved to errors: {file_path.name} → {error_path}")
            except Exception as move_err:
                self.logger.error(f"Failed to move error file: {move_err}")

    def _scan_existing_files(self) -> None:
        """Scan watch directory for existing files to process."""
        self.logger.info(f"🔍 Scanning existing files in: {self.watch_dir}")

        for ext in VMFileHandler.SUPPORTED_EXTENSIONS:
            pattern = f"*{ext}"
            for file_path in self.watch_dir.glob(pattern):
                if file_path.is_file():
                    Log.trace(self.logger, f"📥 Queuing existing file: {file_path.name}")
                    self.queue.put(file_path)
                    if self.handler:
                        self.handler.processing.add(str(file_path))

        queue_size = self.queue.qsize()
        if queue_size > 0:
            self.logger.info(f"📥 Found {queue_size} existing file(s) to process")
        else:
            self.logger.info("📭 No existing files found")

    def run(self) -> None:
        """
        Start the daemon watcher.

        This method:
        1. Validates directories
        2. Scans for existing files
        3. Starts file system observer
        4. Processes files from queue
        """
        self.logger.info("🚀 Starting daemon mode")
        self.logger.info(f"👀 Watching: {self.watch_dir}")
        self.logger.info(f"📤 Output: {self.output_dir}")

        self._validate_directories()

        # Setup file system observer
        self.handler = VMFileHandler(self.logger, self.queue, self.watch_dir)
        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
        self.observer.start()

        self.logger.info("👂 File system observer started")

        # Scan for existing files
        self._scan_existing_files()

        self.logger.info("✅ Daemon ready")

        # Main processing loop
        while not self.stop_event.is_set():
            try:
                # Wait for new file with timeout
                file_path = self.queue.get(timeout=1.0)

                # Process the file
                self._process_file(file_path)

                # Mark as completed
                if self.handler:
                    self.handler.mark_completed(file_path)

                self.queue.task_done()

            except Empty:
                # No files in queue, continue waiting
                continue
            except Exception as e:
                self.logger.error(f"💥 Unexpected error in daemon loop: {e}")
                self.logger.debug("💥 Daemon loop exception", exc_info=True)
                time.sleep(5)  # Back off before retrying

        self.logger.info("🛑 Daemon stopped")

    def stop(self) -> None:
        """Stop the daemon watcher."""
        self.logger.info("🛑 Stopping daemon...")
        self.stop_event.set()

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

        # Wait for queue to finish
        remaining = self.queue.qsize()
        if remaining > 0:
            self.logger.info(f"⏳ Waiting for {remaining} file(s) to complete...")
            self.queue.join()

        self.logger.info("✅ Daemon shutdown complete")
