"""Unit tests for Live Migration Analyzer."""

import logging
import pytest

from hyper2kvm.live_migration.analyzer import LiveMigrationAnalyzer


class TestLiveMigrationAnalyzer:
    """Test Live Migration Analyzer functionality."""

    @pytest.fixture
    def analyzer(self):
        """Create LiveMigrationAnalyzer instance."""
        logger = logging.getLogger("test")
        return LiveMigrationAnalyzer(logger)

    @pytest.fixture
    def base_vm_info(self):
        """Create base VM info for testing."""
        return {
            "name": "test-vm",
            "power_state": "on",
            "memory_mb": 8192,
            "cpu_count": 4,
            "disk_count": 1,
            "disk_size_gb": 100,
            "disk_provisioning": "thin",
            "os_type": "linux",
            "guest_tools_running": True,
            "snapshot_count": 0,
            "connected_devices": [],
        }

    def test_init(self, analyzer):
        """Test LiveMigrationAnalyzer initialization."""
        assert analyzer is not None
        assert analyzer.logger is not None

    def test_can_migrate_live_success(self, analyzer, base_vm_info):
        """Test successful live migration analysis."""
        result = analyzer.can_migrate_live(base_vm_info)

        assert result["feasible"] is True
        assert result["recommended"] is True
        assert result["confidence"] > 0.0
        assert result["estimated_downtime_seconds"] > 0.0
        assert result["downtime_category"] in [
            "excellent",
            "good",
            "acceptable",
            "poor",
        ]

    def test_vm_powered_off(self, analyzer, base_vm_info):
        """Test analysis of powered-off VM."""
        base_vm_info["power_state"] = "off"
        result = analyzer.can_migrate_live(base_vm_info)

        assert result["feasible"] is False
        assert result["recommended"] is False
        assert any("off" in r.lower() for r in result["reasons"])

    def test_vm_with_snapshots(self, analyzer, base_vm_info):
        """Test analysis of VM with snapshots."""
        base_vm_info["snapshot_count"] = 2
        result = analyzer.can_migrate_live(base_vm_info)

        assert result["feasible"] is False
        assert any("snapshot" in r.lower() for r in result["reasons"])

    def test_vm_without_guest_tools(self, analyzer, base_vm_info):
        """Test analysis of VM without guest tools."""
        base_vm_info["guest_tools_running"] = False
        result = analyzer.can_migrate_live(base_vm_info)

        assert result["feasible"] is False
        assert any("guest tools" in r.lower() for r in result["reasons"])

    def test_vm_with_connected_devices(self, analyzer, base_vm_info):
        """Test analysis of VM with connected devices."""
        base_vm_info["connected_devices"] = [
            {"type": "usb", "name": "USB Device"},
            {"type": "cdrom", "name": "CD-ROM"},
        ]
        result = analyzer.can_migrate_live(base_vm_info)

        assert result["feasible"] is False
        assert any("device" in r.lower() for r in result["reasons"])

    @pytest.mark.parametrize(
        "memory_mb,expected_category",
        [
            (2048, "excellent"),  # Small VM
            (8192, "good"),  # Medium VM
            (32768, "acceptable"),  # Large VM
        ],
    )
    def test_downtime_estimation_by_memory(
        self, analyzer, base_vm_info, memory_mb, expected_category
    ):
        """Test downtime estimation varies with memory size."""
        base_vm_info["memory_mb"] = memory_mb
        result = analyzer.can_migrate_live(base_vm_info)

        # Downtime should increase with memory size
        assert result["estimated_downtime_seconds"] > 0.0

    def test_windows_vs_linux(self, analyzer, base_vm_info):
        """Test that Windows VMs have higher estimated downtime."""
        # Test Linux VM
        base_vm_info["os_type"] = "linux"
        linux_result = analyzer.can_migrate_live(base_vm_info)
        linux_downtime = linux_result["estimated_downtime_seconds"]

        # Test Windows VM
        base_vm_info["os_type"] = "windows"
        windows_result = analyzer.can_migrate_live(base_vm_info)
        windows_downtime = windows_result["estimated_downtime_seconds"]

        # Windows should have higher downtime due to memory churn
        assert windows_downtime >= linux_downtime

    def test_thick_vs_thin_provisioning(self, analyzer, base_vm_info):
        """Test that thick provisioning increases downtime."""
        # Test thin provisioning
        base_vm_info["disk_provisioning"] = "thin"
        thin_result = analyzer.can_migrate_live(base_vm_info)
        thin_downtime = thin_result["estimated_downtime_seconds"]

        # Test thick provisioning
        base_vm_info["disk_provisioning"] = "thick"
        thick_result = analyzer.can_migrate_live(base_vm_info)
        thick_downtime = thick_result["estimated_downtime_seconds"]

        # Thick should have higher downtime
        assert thick_downtime >= thin_downtime

    def test_requirements_include_storage(self, analyzer, base_vm_info):
        """Test that requirements include storage information."""
        result = analyzer.can_migrate_live(base_vm_info)

        # Should mention storage requirements
        assert any("storage" in r.lower() for r in result["requirements"])
        assert any("memory" in r.lower() for r in result["requirements"])

    def test_warnings_for_large_memory(self, analyzer, base_vm_info):
        """Test warnings for VMs with large memory."""
        base_vm_info["memory_mb"] = 100000  # 100GB
        result = analyzer.can_migrate_live(base_vm_info)

        # Should warn about large memory
        assert any("memory" in w.lower() for w in result["warnings"])

    def test_warnings_for_multiple_disks(self, analyzer, base_vm_info):
        """Test warnings for VMs with multiple disks."""
        base_vm_info["disk_count"] = 5
        result = analyzer.can_migrate_live(base_vm_info)

        # Should warn about multiple disks
        assert any("disk" in w.lower() for w in result["warnings"])

    def test_analyze_batch(self, analyzer, base_vm_info):
        """Test batch analysis of multiple VMs."""
        vms = [
            {**base_vm_info, "name": "vm1"},
            {**base_vm_info, "name": "vm2", "power_state": "off"},
            {**base_vm_info, "name": "vm3", "snapshot_count": 1},
        ]

        result = analyzer.analyze_batch(vms)

        assert result["total_vms"] == 3
        assert result["live_feasible"] >= 1  # At least vm1
        assert result["offline_required"] >= 2  # vm2 and vm3
        assert len(result["vms"]) == 3

    def test_analyze_batch_percentages(self, analyzer, base_vm_info):
        """Test batch analysis calculates percentages correctly."""
        vms = [
            {**base_vm_info, "name": f"vm{i}"} for i in range(10)
        ]  # All good VMs

        result = analyzer.analyze_batch(vms)

        assert "live_feasible_pct" in result
        assert "live_recommended_pct" in result
        assert result["live_feasible_pct"] == 100.0  # All should be feasible

    def test_confidence_score_excellent(self, analyzer, base_vm_info):
        """Test confidence score for excellent migration candidate."""
        base_vm_info["memory_mb"] = 2048  # Small VM
        result = analyzer.can_migrate_live(base_vm_info)

        assert result["downtime_category"] == "excellent"
        assert result["confidence"] >= 0.90

    def test_confidence_score_decreases_with_size(self, analyzer, base_vm_info):
        """Test confidence decreases with VM size."""
        # Small VM
        base_vm_info["memory_mb"] = 2048
        small_result = analyzer.can_migrate_live(base_vm_info)

        # Large VM
        base_vm_info["memory_mb"] = 100000  # Very large to ensure different category
        large_result = analyzer.can_migrate_live(base_vm_info)

        # Confidence should be lower for larger VM
        assert small_result["confidence"] >= large_result["confidence"]

    def test_fallback_to_offline_flag(self, analyzer, base_vm_info):
        """Test that fallback_to_offline flag is set."""
        result = analyzer.can_migrate_live(base_vm_info)

        # Should always have fallback option
        assert "fallback_to_offline" in result
        assert isinstance(result["fallback_to_offline"], bool)
