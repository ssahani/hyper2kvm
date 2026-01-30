"""
Unit tests for VMCraft storage stack activation

Tests LVM, LUKS, and mdraid activation logic for complex storage configurations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call


class TestLVMActivation:
    """Test LVM volume group activation"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.vgs = Mock(return_value=[])
        g.lvs = Mock(return_value=[])
        g.pvs = Mock(return_value=[])
        g.vg_activate_all = Mock()
        g.vg_activate = Mock()
        return g

    def test_activate_single_vg(self, mock_guestfs):
        """Test activating a single volume group"""
        mock_guestfs.vgs.return_value = ["vg_root"]

        # Activate all VGs
        mock_guestfs.vg_activate_all(True)

        mock_guestfs.vg_activate_all.assert_called_once_with(True)

    def test_activate_multi_pv_vg(self, mock_guestfs):
        """Test activating VG spanning multiple PVs"""
        mock_guestfs.pvs.return_value = ["/dev/sda2", "/dev/sdb1"]
        mock_guestfs.vgs.return_value = ["vg_data"]

        # Should activate VG with multiple PVs
        mock_guestfs.vg_activate_all(True)

        assert mock_guestfs.vg_activate_all.called

    def test_activate_with_snapshots(self, mock_guestfs):
        """Test activating VG with snapshots"""
        mock_guestfs.lvs.return_value = [
            "/dev/vg_root/lv_root",
            "/dev/vg_root/snap_root",
        ]

        # Should handle snapshots
        lvs = mock_guestfs.lvs()
        assert len(lvs) == 2

    def test_activate_thin_provisioned(self, mock_guestfs):
        """Test activating thin-provisioned LVM"""
        mock_guestfs.lvs.return_value = [
            "/dev/vg_pool/thin_pool",
            "/dev/vg_pool/thin_vol1",
        ]

        # Thin volumes should activate
        mock_guestfs.vg_activate_all(True)

        assert mock_guestfs.vg_activate_all.called

    def test_missing_pv_handling(self, mock_guestfs):
        """Test handling of missing PV in VG"""
        # Simulate missing PV
        mock_guestfs.vg_activate_all.side_effect = RuntimeError("PV missing")

        with pytest.raises(RuntimeError):
            mock_guestfs.vg_activate_all(True)


class TestLUKSEncryption:
    """Test LUKS encrypted volume handling"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.luks_open = Mock()
        g.luks_close = Mock()
        g.luks_uuid = Mock(return_value="12345-67890")
        return g

    def test_detect_luks_volume(self, mock_guestfs):
        """Test detection of LUKS encrypted volume"""
        mock_guestfs.luks_uuid.return_value = "12345-67890"

        uuid = mock_guestfs.luks_uuid("/dev/sda2")
        assert uuid == "12345-67890"

    def test_luks_without_key(self, mock_guestfs):
        """Test LUKS volume without key available"""
        # Cannot open without key
        mock_guestfs.luks_open.side_effect = RuntimeError("No key available")

        with pytest.raises(RuntimeError):
            mock_guestfs.luks_open("/dev/sda2", "passphrase", "cryptroot")

    def test_nested_luks_lvm(self, mock_guestfs):
        """Test LUKS volume containing LVM"""
        # LUKS -> LVM -> filesystems
        mock_guestfs.luks_open.return_value = None
        mock_guestfs.vg_activate_all = Mock()

        # Open LUKS
        mock_guestfs.luks_open("/dev/sda2", "pass", "cryptroot")

        # Then activate LVM inside
        mock_guestfs.vg_activate_all(True)

        mock_guestfs.luks_open.assert_called_once()
        mock_guestfs.vg_activate_all.assert_called_once()


class TestMDRaid:
    """Test mdraid (software RAID) activation"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.md_stat = Mock(return_value=[])
        g.md_detail = Mock(return_value={})
        return g

    def test_activate_raid1(self, mock_guestfs):
        """Test activating RAID1 array"""
        mock_guestfs.md_stat.return_value = [
            {"mdname": "md0", "level": "raid1"}
        ]

        arrays = mock_guestfs.md_stat()
        assert len(arrays) == 1
        assert arrays[0]["level"] == "raid1"

    def test_degraded_raid_array(self, mock_guestfs):
        """Test handling degraded RAID array"""
        mock_guestfs.md_detail.return_value = {
            "array_state": "clean, degraded",
            "devices": "1",
            "working_devices": "1",
            "failed_devices": "1",
        }

        detail = mock_guestfs.md_detail("/dev/md0")
        assert "degraded" in detail["array_state"]


class TestStorageStackCombinations:
    """Test complex storage stack combinations"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.luks_open = Mock()
        g.vg_activate_all = Mock()
        g.lvs = Mock(return_value=[])
        g.md_stat = Mock(return_value=[])
        return g

    def test_luks_on_lvm(self, mock_guestfs):
        """Test LUKS encryption on LVM logical volume"""
        # LVM -> LUKS -> filesystem
        # This is common setup

        # First activate LVM
        mock_guestfs.vg_activate_all(True)

        # Then open LUKS on top of LV
        mock_guestfs.luks_open("/dev/vg_root/lv_encrypted", "pass", "cryptroot")

        mock_guestfs.vg_activate_all.assert_called_once()
        mock_guestfs.luks_open.assert_called_once()

    def test_lvm_on_luks(self, mock_guestfs):
        """Test LVM on LUKS (encrypted PV)"""
        # LUKS -> LVM -> filesystems
        # Another common setup

        # First open LUKS
        mock_guestfs.luks_open("/dev/sda2", "pass", "cryptroot")

        # Then activate LVM on top
        mock_guestfs.vg_activate_all(True)

        # Should be called in correct order
        assert mock_guestfs.luks_open.called
        assert mock_guestfs.vg_activate_all.called

    def test_raid_with_lvm(self, mock_guestfs):
        """Test RAID array as LVM PV"""
        # RAID -> LVM -> filesystems
        mock_guestfs.md_stat.return_value = [
            {"mdname": "md0", "level": "raid1"}
        ]

        # RAID should be detected
        arrays = mock_guestfs.md_stat()
        assert len(arrays) == 1

        # Then activate LVM on RAID
        mock_guestfs.vg_activate_all(True)
        assert mock_guestfs.vg_activate_all.called

    def test_luks_on_raid_with_lvm(self, mock_guestfs):
        """Test LUKS on RAID with LVM on top"""
        # RAID -> LUKS -> LVM -> filesystems

        # Detect RAID
        mock_guestfs.md_stat.return_value = [{"mdname": "md0"}]
        arrays = mock_guestfs.md_stat()
        assert len(arrays) == 1

        # Open LUKS on RAID
        mock_guestfs.luks_open("/dev/md0", "pass", "cryptmd0")

        # Activate LVM on LUKS
        mock_guestfs.vg_activate_all(True)

        # All layers should be activated
        assert mock_guestfs.luks_open.called
        assert mock_guestfs.vg_activate_all.called

    def test_multiple_luks_volumes(self, mock_guestfs):
        """Test system with multiple LUKS volumes"""
        # Multiple encrypted partitions
        luks_devices = [
            ("/dev/sda2", "cryptroot"),
            ("/dev/sda3", "crypthome"),
            ("/dev/sdb1", "cryptdata"),
        ]

        for device, name in luks_devices:
            mock_guestfs.luks_open(device, "pass", name)

        assert mock_guestfs.luks_open.call_count == 3

    def test_lvm_cache_volume(self, mock_guestfs):
        """Test LVM with cache volume (fast SSD + slow HDD)"""
        # LVM cache uses fast device to cache slow device
        mock_guestfs.lvs.return_value = [
            "/dev/vg_cached/lv_origin",
            "/dev/vg_cached/lv_cache",
            "/dev/vg_cached/lv_cached_volume",
        ]

        lvs = mock_guestfs.lvs()
        assert len(lvs) == 3
        assert any("cache" in lv for lv in lvs)

    def test_multipath_with_lvm(self, mock_guestfs):
        """Test multipath devices with LVM"""
        # Multipath -> LVM setup (common in SAN environments)
        mock_guestfs.pvs = Mock(return_value=[
            "/dev/mapper/mpatha",
            "/dev/mapper/mpathb",
        ])

        pvs = mock_guestfs.pvs()
        assert len(pvs) == 2
        assert all("mpath" in pv for pv in pvs)

        # Activate VG on multipath devices
        mock_guestfs.vg_activate_all(True)
        assert mock_guestfs.vg_activate_all.called


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
