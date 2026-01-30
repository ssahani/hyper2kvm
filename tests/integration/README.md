# Integration Tests

Integration tests verify end-to-end functionality and component interactions.

## Directory Structure

### Feature-Based Tests

- **`batch/`** - Batch migration workflow tests
  - Batch orchestration
  - Checkpoint/resume
  - Progress tracking
  - Hook and retry logic
  - Profile caching
  - Template engine integration

- **`core/`** - Core functionality tests
  - `test_disk_conversion.py` - Disk format conversion
  - `test_manifest_workflow.py` - Manifest processing
  - `test_recovery_manager.py` - Recovery mechanisms

- **`vmcraft/`** - VMCraft library tests
  - `test_libguestfs_*.py` - Libguestfs operations (device, filesystem, inspection, mount, partition)
  - `test_vmcraft_systemd_integration.py` - Systemd integration
  - `test_fstab_fixing.py` - Fstab stabilization

- **`migration_tools/`** - Migration tools suite tests
  - `test_migration_workflow.py` - End-to-end migration workflows

- **`systemd/`** - Systemd-specific tests
  - `test_vmware_to_kvm_migration.py` - VMware to KVM service migration

- **`performance/`** - Performance and scalability tests
  - `test_performance_benchmarks.py` - Performance benchmarks
  - `test_multicloud_integration.py` - Multi-cloud integration

- **`production/`** - Production readiness tests
  - `test_production_tools.py` - Production tool validation
  - `test_photon_network_drivers.py` - Photon OS network driver testing

- **`real_vms/`** - Tests with real VM images
  - `test_full_pipeline.py` - Complete migration pipeline
  - `test_photon_vmdk_e2e.py` - Photon OS VMDK end-to-end

### Module-Based Tests

- **`test_cli/`** - CLI integration tests
- **`test_converters/`** - Converter integration tests
- **`test_fixers/`** - Fixer integration tests
- **`test_vmware/`** - VMware client integration tests

## Running Tests

### Run all integration tests
```bash
pytest tests/integration/
```

### Run specific category
```bash
pytest tests/integration/vmcraft/
pytest tests/integration/batch/
pytest tests/integration/performance/
```

### Run with markers
```bash
pytest -m integration
pytest -m slow
pytest -m "integration and not slow"
```

## Test Markers

- `@pytest.mark.integration` - Integration test
- `@pytest.mark.slow` - Slow-running test
- `@pytest.mark.skip` - Temporarily skipped test
- `@pytest.mark.requires_vmdk` - Requires real VMDK file

## Writing Integration Tests

Integration tests should:
1. Test component interactions
2. Use real or realistic test data
3. Verify end-to-end workflows
4. Include error handling scenarios
5. Clean up resources after testing

Example structure:
```python
import pytest

@pytest.mark.integration
class TestFeatureIntegration:
    def test_basic_workflow(self):
        """Test basic feature workflow."""
        # Setup
        # Execute
        # Verify
        # Cleanup
```

## Dependencies

Integration tests may require:
- qemu-utils (for disk operations)
- libguestfs-tools (for VM inspection)
- lvm2 (for LVM tests)
- systemd (for systemd integration tests)

See `docs/95-Testing-Guide.md` for complete testing documentation.
