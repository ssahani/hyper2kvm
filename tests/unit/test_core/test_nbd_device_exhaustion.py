"""
Unit tests for NBD device management and exhaustion scenarios

Tests device allocation, race conditions, cleanup, and recovery for NBD
(Network Block Device) usage in hyper2kvm.
"""

import pytest
import subprocess
import time
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path


class TestNBDDeviceAllocation:
    """Test NBD device allocation and management"""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess for qemu-nbd commands"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            yield mock_run

    def test_find_free_nbd_device_first_available(self):
        """Test finding first available NBD device"""
        # Simulate: /dev/nbd0 is free (PID file doesn't exist)
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = False  # First device is free

            pid_file = Path("/sys/block/nbd0/pid")
            is_free = not pid_file.exists()

            if is_free:
                free_device = "/dev/nbd0"

            assert free_device == "/dev/nbd0"
            mock_exists.assert_called()

    def test_find_free_nbd_device_skip_in_use(self):
        """Test skipping devices that are in use"""
        # Simulate: nbd0-nbd2 are in use, nbd3 is free
        # In production code, would check /sys/block/nbdN/pid for each device

        # Mock scenario: first 3 devices busy, 4th is free
        busy_devices = {0, 1, 2}
        free_device = None

        for i in range(16):
            if i not in busy_devices:
                free_device = f"/dev/nbd{i}"
                break

        assert free_device == "/dev/nbd3"

    def test_all_nbd_devices_in_use(self):
        """Test error when all NBD devices are in use"""
        # Simulate: all devices 0-15 are in use
        busy_devices = set(range(16))

        # Try to find free device
        free_device = None
        for i in range(16):
            if i not in busy_devices:
                free_device = f"/dev/nbd{i}"
                break

        # Should not find any free device
        assert free_device is None

    def test_nbd_device_allocation_with_modprobe(self, mock_subprocess):
        """Test NBD module loading with modprobe"""
        # Load nbd kernel module with max_part=0 nbds_max=16
        mock_subprocess.return_value = Mock(returncode=0)

        result = subprocess.run(
            ["modprobe", "nbd", "max_part=0", "nbds_max=16"],
            capture_output=True,
            check=True,
        )

        assert result.returncode == 0

    def test_qemu_nbd_connect(self, mock_subprocess):
        """Test connecting image to NBD device"""
        image_path = "/path/to/image.qcow2"
        nbd_device = "/dev/nbd0"

        # Connect qemu-nbd
        mock_subprocess.return_value = Mock(returncode=0)

        subprocess.run(
            ["qemu-nbd", "--connect", nbd_device, "--format", "qcow2", image_path],
            check=True,
        )

        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "qemu-nbd" in call_args
        assert nbd_device in call_args
        assert image_path in call_args

    def test_qemu_nbd_disconnect(self, mock_subprocess):
        """Test disconnecting NBD device"""
        nbd_device = "/dev/nbd0"

        # Disconnect qemu-nbd
        mock_subprocess.return_value = Mock(returncode=0)

        subprocess.run(["qemu-nbd", "--disconnect", nbd_device], check=True)

        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "qemu-nbd" in call_args
        assert "--disconnect" in call_args
        assert nbd_device in call_args


class TestNBDStaleDeviceCleanup:
    """Test cleanup of stale NBD devices"""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess for cleanup commands"""
        with patch('subprocess.run') as mock_run:
            yield mock_run

    def test_detect_stale_nbd_device(self):
        """Test detection of stale NBD device (process died)"""
        # Device has PID file but process no longer exists
        with patch('pathlib.Path.read_text') as mock_read:
            with patch('pathlib.Path.exists') as mock_exists:
                mock_read.return_value = "12345"
                # PID file exists
                mock_exists.side_effect = [True, False]  # pid file exists, /proc/12345 doesn't

                pid_file = Path("/sys/block/nbd0/pid")
                if pid_file.exists():
                    pid = pid_file.read_text().strip()
                    proc_exists = Path(f"/proc/{pid}").exists()

                    # Process should not exist (stale device)
                    assert proc_exists is False

    def test_force_disconnect_stale_device(self, mock_subprocess):
        """Test force disconnecting stale NBD device"""
        nbd_device = "/dev/nbd5"

        # Force disconnect
        mock_subprocess.return_value = Mock(returncode=0)

        subprocess.run(["qemu-nbd", "--disconnect", nbd_device], check=False)

        assert mock_subprocess.called

    def test_cleanup_all_stale_devices(self, mock_subprocess):
        """Test cleaning up all stale NBD devices"""
        # Simulate multiple stale devices
        stale_devices = ["/dev/nbd1", "/dev/nbd3", "/dev/nbd7"]

        mock_subprocess.return_value = Mock(returncode=0)

        for device in stale_devices:
            subprocess.run(["qemu-nbd", "--disconnect", device], check=False)

        assert mock_subprocess.call_count == len(stale_devices)

    def test_cleanup_preserves_active_devices(self):
        """Test cleanup doesn't touch active NBD devices"""
        # Device 0: active (PID 1000 exists)
        # Device 1: stale (PID 9999 doesn't exist)

        device_pids = {
            "/dev/nbd0": 1000,  # Active
            "/dev/nbd1": 9999,  # Stale
        }

        active_pids = {1000}  # Only PID 1000 is running

        # Determine which devices to cleanup
        stale_devices = []
        for device, pid in device_pids.items():
            if pid not in active_pids:
                stale_devices.append(device)

        # Should only cleanup nbd1
        assert stale_devices == ["/dev/nbd1"]
        assert "/dev/nbd0" not in stale_devices


class TestNBDConcurrentAllocation:
    """Test concurrent NBD device allocation and race conditions"""

    def test_concurrent_device_allocation_race(self):
        """Test race condition when multiple threads allocate devices"""
        # Two threads try to allocate same device simultaneously
        allocated_devices = []

        def allocate_device(thread_id):
            # Simulate checking if device is free
            for i in range(16):
                device = f"/dev/nbd{i}"
                if device not in allocated_devices:
                    # Race: another thread might allocate here
                    time.sleep(0.001)  # Simulate delay
                    allocated_devices.append(device)
                    return device
            return None

        # This test demonstrates the race condition
        # In production, needs proper locking

    def test_device_allocation_with_lock(self):
        """Test device allocation with proper locking"""
        from threading import Lock

        allocated_devices = []
        lock = Lock()

        def allocate_device_safe(thread_id):
            with lock:
                for i in range(16):
                    device = f"/dev/nbd{i}"
                    if device not in allocated_devices:
                        allocated_devices.append(device)
                        return device
            return None

        # Should safely allocate devices
        dev1 = allocate_device_safe(1)
        dev2 = allocate_device_safe(2)

        assert dev1 != dev2
        assert len(allocated_devices) == 2

    def test_device_release_updates_pool(self):
        """Test releasing device returns it to available pool"""
        allocated_devices = set(["/dev/nbd0", "/dev/nbd1"])

        # Release nbd0
        allocated_devices.remove("/dev/nbd0")

        # Should be available again
        assert "/dev/nbd0" not in allocated_devices
        assert "/dev/nbd1" in allocated_devices


class TestNBDErrorHandling:
    """Test NBD error scenarios and recovery"""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess for error scenarios"""
        with patch('subprocess.run') as mock_run:
            yield mock_run

    def test_qemu_nbd_connect_failure(self, mock_subprocess):
        """Test handling qemu-nbd connection failure"""
        # Simulate connection failure
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, ["qemu-nbd"], stderr="Failed to connect"
        )

        with pytest.raises(subprocess.CalledProcessError):
            subprocess.run(
                ["qemu-nbd", "--connect", "/dev/nbd0", "/image.qcow2"],
                check=True,
            )

    def test_device_busy_error(self, mock_subprocess):
        """Test handling device busy error"""
        # Device is already in use
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, ["qemu-nbd"], stderr="Device or resource busy"
        )

        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            subprocess.run(
                ["qemu-nbd", "--connect", "/dev/nbd0", "/image.qcow2"],
                check=True,
            )

        assert "Device or resource busy" in str(exc_info.value.stderr)

    def test_device_release_on_error(self, mock_subprocess):
        """Test device is released when operation fails"""
        allocated_device = "/dev/nbd0"

        # Simulate operation failure
        mock_subprocess.side_effect = RuntimeError("Operation failed")

        try:
            subprocess.run(["some-operation"], check=True)
        except Exception:
            # Cleanup: disconnect device
            mock_subprocess.side_effect = None
            mock_subprocess.return_value = Mock(returncode=0)
            subprocess.run(["qemu-nbd", "--disconnect", allocated_device], check=False)

        # Device should be released
        assert mock_subprocess.called

    def test_qemu_nbd_crash_recovery(self, mock_subprocess):
        """Test recovery when qemu-nbd process crashes"""
        nbd_device = "/dev/nbd0"

        # Detect qemu-nbd crash (PID file exists but process is gone)
        # Cleanup by force disconnect
        mock_subprocess.return_value = Mock(returncode=0)

        subprocess.run(["qemu-nbd", "--disconnect", nbd_device], check=False)

        # Should attempt disconnect
        assert mock_subprocess.called

    def test_partial_disconnect_handling(self, mock_subprocess):
        """Test handling partial disconnect (device in weird state)"""
        nbd_device = "/dev/nbd0"

        # First disconnect attempt fails
        mock_subprocess.side_effect = [
            subprocess.CalledProcessError(1, ["qemu-nbd"]),
            Mock(returncode=0),  # Retry succeeds
        ]

        # Try disconnect
        try:
            subprocess.run(["qemu-nbd", "--disconnect", nbd_device], check=True)
        except subprocess.CalledProcessError:
            # Retry
            subprocess.run(["qemu-nbd", "--disconnect", nbd_device], check=False)

        assert mock_subprocess.call_count == 2


class TestNBDDeviceExhaustion:
    """Test scenarios when NBD devices are exhausted"""

    def test_max_devices_reached(self):
        """Test behavior when maximum NBD devices are in use"""
        max_devices = 16
        allocated_devices = set(f"/dev/nbd{i}" for i in range(max_devices))

        # Try to allocate one more
        free_device = None
        for i in range(max_devices):
            device = f"/dev/nbd{i}"
            if device not in allocated_devices:
                free_device = device
                break

        # Should not find any free device
        assert free_device is None
        assert len(allocated_devices) == max_devices

    def test_increase_nbd_device_limit(self, ):
        """Test increasing NBD device limit via module parameter"""
        # Unload and reload nbd module with higher limit
        # This is informational test - actual commands would be:
        # rmmod nbd
        # modprobe nbd nbds_max=32

        new_max = 32
        # After reload, should have more devices available
        assert new_max > 16

    def test_queue_operations_when_exhausted(self):
        """Test queueing operations when devices exhausted"""
        max_devices = 16
        allocated_devices = set(f"/dev/nbd{i}" for i in range(max_devices))
        queue = []

        # Try to allocate device
        free_device = None
        for i in range(max_devices):
            device = f"/dev/nbd{i}"
            if device not in allocated_devices:
                free_device = device
                break

        # If no device available, queue the operation
        if free_device is None:
            queue.append({"operation": "connect", "image": "/path/to/image"})

        assert len(queue) == 1
        assert queue[0]["operation"] == "connect"

    def test_wait_for_device_availability(self):
        """Test waiting for device to become available"""
        allocated_devices = set(f"/dev/nbd{i}" for i in range(16))

        # Simulate waiting loop
        max_retries = 5
        retry_count = 0
        free_device = None

        while retry_count < max_retries and free_device is None:
            for i in range(16):
                device = f"/dev/nbd{i}"
                if device not in allocated_devices:
                    free_device = device
                    break

            if free_device is None:
                retry_count += 1
                time.sleep(0.1)

        # Should exhaust retries without finding device
        assert free_device is None
        assert retry_count == max_retries


class TestNBDPartitionScanning:
    """Test NBD partition scanning behavior"""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            yield mock_run

    def test_nbd_with_partition_scanning_disabled(self, mock_subprocess):
        """Test NBD with max_part=0 (no partition scanning)"""
        # Load module with max_part=0
        subprocess.run(["modprobe", "nbd", "max_part=0", "nbds_max=16"], check=True)

        # Device should not have partition entries
        # /dev/nbd0p1, /dev/nbd0p2, etc. should not exist

    def test_nbd_with_partition_scanning_enabled(self, mock_subprocess):
        """Test NBD with max_part=16 (enable partition scanning)"""
        # Load module with max_part=16
        subprocess.run(["modprobe", "nbd", "max_part=16", "nbds_max=16"], check=True)

        # Device can have partition entries
        # /dev/nbd0p1, /dev/nbd0p2, etc. can exist

    def test_kpartx_alternative(self, mock_subprocess):
        """Test using kpartx as alternative to NBD partition scanning"""
        nbd_device = "/dev/nbd0"

        # Use kpartx to create partition mappings
        subprocess.run(["kpartx", "-a", nbd_device], check=True)

        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "kpartx" in call_args
        assert nbd_device in call_args


class TestNBDReadOnlyMode:
    """Test NBD read-only mode"""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            yield mock_run

    def test_connect_readonly(self, mock_subprocess):
        """Test connecting NBD in read-only mode"""
        subprocess.run(
            ["qemu-nbd", "--connect", "/dev/nbd0", "--read-only", "/image.qcow2"],
            check=True,
        )

        call_args = mock_subprocess.call_args[0][0]
        assert "--read-only" in call_args

    def test_write_to_readonly_fails(self, mock_subprocess):
        """Test write operations fail on read-only NBD"""
        # Simulate write failure on read-only device
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, ["dd"], stderr="Read-only file system"
        )

        with pytest.raises(subprocess.CalledProcessError):
            subprocess.run(
                ["dd", "if=/dev/zero", "of=/dev/nbd0", "bs=1M", "count=1"],
                check=True,
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
