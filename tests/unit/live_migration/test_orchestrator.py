"""Unit tests for Live Migration Orchestrator."""

import logging
import pytest
from pathlib import Path

from hyper2kvm.live_migration.orchestrator import LiveMigrationOrchestrator


class TestLiveMigrationOrchestrator:
    """Test Live Migration Orchestrator functionality."""

    @pytest.fixture
    def orchestrator(self):
        """Create LiveMigrationOrchestrator instance."""
        logger = logging.getLogger("test")
        return LiveMigrationOrchestrator(logger)

    @pytest.fixture
    def sample_vm_info(self):
        """Create sample VM info."""
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

    def test_init(self, orchestrator):
        """Test LiveMigrationOrchestrator initialization."""
        assert orchestrator is not None
        assert orchestrator.logger is not None
        assert orchestrator.analyzer is not None
        assert orchestrator.hypersdk is not None
        assert orchestrator.hybrid_mgr is not None

    def test_generate_migration_report(self, orchestrator, tmp_path):
        """Test migration report generation."""
        migration_result = {
            "vm_id": "test-vm",
            "success": True,
            "mode_selected": "live",
            "mode_recommended": "live",
            "analysis": {
                "feasible": True,
                "recommended": True,
                "confidence": 0.95,
                "estimated_downtime_seconds": 3.5,
                "downtime_category": "excellent",
                "reasons": ["Low memory usage", "No snapshots"],
                "warnings": [],
                "requirements": ["Network connectivity"],
            },
            "migration": {
                "success": True,
                "actual_downtime_ms": 3500,
                "total_time_seconds": 45.0,
            },
        }

        report_path = tmp_path / "migration-report.md"
        orchestrator.generate_migration_report(migration_result, report_path)

        assert report_path.exists()

        # Verify report content
        content = report_path.read_text()
        assert "Live Migration Report" in content
        assert "test-vm" in content
        assert "SUCCESS" in content
        assert "3500" in content  # Actual downtime

    def test_build_report_with_error(self, orchestrator, tmp_path):
        """Test report generation with migration error."""
        migration_result = {
            "vm_id": "failed-vm",
            "success": False,
            "mode_selected": "live",
            "error": "Connection timeout",
            "analysis": {},
            "migration": {},
        }

        report_path = tmp_path / "failed-migration.md"
        orchestrator.generate_migration_report(migration_result, report_path)

        assert report_path.exists()
        content = report_path.read_text()
        assert "FAILED" in content
        assert "Connection timeout" in content
