# Real VMDK Integration Tests

This directory contains integration tests that use **real VMDK disk images** to validate the complete hyper2kvm migration pipeline.

## Test Files

### `test_photon_vmdk_e2e.py`
End-to-end tests using the actual `photon.vmdk` file (882MB).

**Test Classes:**
- `TestPhotonVMDKInspection` - VMDK file inspection and format detection
- `TestPhotonVMDKConversion` - VMDK to QCOW2 conversion tests
- `TestPhotonManifestWorkflow` - Manifest creation and batch workflows
- `TestPhotonLibguestfsInspection` - Libguestfs inspection (if available)
- `TestPhotonEndToEndMigration` - Complete migration workflow
- `TestPhotonPerformance` - Performance benchmarks

**Total: 16 tests**

### `test_full_pipeline.py`
Full pipeline integration tests with progress tracking and validation.

**Test Classes:**
- `TestFullPipelineWithPhoton` - Complete pipeline with manifest, progress, validation
- `TestPhotonSpecificFeatures` - Photon OS specific configurations
- `TestPhotonConversionQuality` - Conversion quality assurance
- `TestPhotonWithActualConfig` - Tests using actual config files

**Total: 11 tests**

## Requirements

### Required Files
- `photon.vmdk` - Real Photon OS VMDK disk (882MB) in repository root
- `test-confs/04-local-photon-os-vmdk.yaml` - Photon OS configuration

### Required Tools
- `qemu-img` - For VMDK to QCOW2 conversion and inspection
- `guestfish` (optional) - For libguestfs inspection tests
- Python packages from `requirements.txt`

## Running Tests

### Run All Real VMDK Tests
```bash
pytest tests/integration/test_real_vmdk/ -v
```

### Run Quick Tests (Skip Slow Ones)
```bash
pytest tests/integration/test_real_vmdk/ -v -m "not slow"
```

### Run Only Slow/Comprehensive Tests
```bash
pytest tests/integration/test_real_vmdk/ -v -m slow
```

### Run Specific Test Classes
```bash
# Basic inspection tests
pytest tests/integration/test_real_vmdk/test_photon_vmdk_e2e.py::TestPhotonVMDKInspection -v

# Conversion tests
pytest tests/integration/test_real_vmdk/test_photon_vmdk_e2e.py::TestPhotonVMDKConversion -v

# Complete end-to-end
pytest tests/integration/test_real_vmdk/test_photon_vmdk_e2e.py::TestPhotonEndToEndMigration -v

# Full pipeline
pytest tests/integration/test_real_vmdk/test_full_pipeline.py::TestFullPipelineWithPhoton -v

# Performance tests
pytest tests/integration/test_real_vmdk/test_photon_vmdk_e2e.py::TestPhotonPerformance -v
```

### Run With Performance Metrics
```bash
pytest tests/integration/test_real_vmdk/ -v -s  # -s shows print output
```

## Test Categories

### 🔍 Inspection Tests
- VMDK file existence and readability
- Format detection with qemu-img
- VMDK header parsing
- Info extraction
- Libguestfs OS detection

### 🔄 Conversion Tests
- Basic VMDK to QCOW2 conversion
- Conversion with compression
- Data integrity verification
- Virtual size preservation
- Format correctness

### 📋 Manifest Tests
- Manifest creation for Photon VMDK
- Batch manifest with Photon VM
- Manifest-driven conversion
- Pipeline configuration

### 🏃 End-to-End Tests
- Complete migration workflow
- Progress tracking integration
- Validation framework integration
- Checkpoint/resume with real disk
- Performance benchmarking

### ⚡ Performance Tests
- Conversion speed measurement
- Compressed conversion performance
- Throughput calculations
- Size comparisons

## Test Markers

Tests are marked with pytest markers:

- `@pytest.mark.slow` - Tests that take significant time (> 30 seconds)
- `@pytest.mark.skipif` - Tests that skip if photon.vmdk not found

## Expected Behavior

### If photon.vmdk Exists
All 27 tests will run and validate:
- ✅ File inspection and format detection
- ✅ VMDK to QCOW2 conversion
- ✅ Data integrity preservation
- ✅ Complete migration workflow
- ✅ Performance metrics

### If photon.vmdk Missing
Tests will be automatically skipped with message:
```
SKIPPED [27] test_photon_vmdk_e2e.py:17: photon.vmdk not found in repository root
```

## Performance Benchmarks

Typical performance on modern hardware with 882MB Photon VMDK:

| Operation | Time | Throughput |
|-----------|------|------------|
| Uncompressed conversion | 30-60s | ~15-30 MB/s |
| Compressed conversion | 60-120s | ~7-15 MB/s |
| Format detection | < 1s | - |
| Validation | < 5s | - |

## Integration Points Tested

These tests validate integration of:
1. **VMDK Parsing** - Reading VMware disk format
2. **Conversion Engine** - qemu-img integration
3. **Manifest System** - Declarative configuration
4. **Batch Processing** - Multi-VM workflows
5. **Progress Tracking** - Real-time monitoring
6. **Checkpoint/Resume** - Interruption handling
7. **Validation Framework** - Quality assurance
8. **Libvirt Integration** - KVM domain creation

## Troubleshooting

### Tests Skip with "qemu-img not available"
Install qemu-utils:
```bash
# Ubuntu/Debian
sudo apt-get install qemu-utils

# Fedora/RHEL
sudo dnf install qemu-img

# macOS
brew install qemu
```

### Tests Timeout
Increase timeout in test decorators:
```python
@pytest.mark.timeout(300)  # 5 minutes
```

### Conversion Fails
Check disk space:
```bash
df -h /tmp  # Tests use tmp_path fixture
```

### Performance Slower Than Expected
Check system load and available resources:
```bash
top
iotop  # Check disk I/O
```

## CI/CD Considerations

### For CI Pipelines
These tests can be:
- **Included** - If CI has sufficient disk space and time
- **Marked as slow** - Run only on nightly builds
- **Skipped** - If photon.vmdk not available in CI

### Example CI Configuration
```yaml
# GitHub Actions example
- name: Run real VMDK tests
  if: github.event_name == 'schedule'  # Nightly only
  run: pytest tests/integration/test_real_vmdk/ -v -m slow
```

## Contributing

When adding new tests:
1. Mark slow tests with `@pytest.mark.slow`
2. Use `tmp_path` fixture for output files
3. Add appropriate skip conditions
4. Include performance metrics in test output
5. Clean up temporary files after tests

## Real-World Validation

These tests provide confidence that:
- ✅ Real VMDKs can be converted successfully
- ✅ Data integrity is preserved
- ✅ Performance is acceptable
- ✅ Complete workflow functions end-to-end
- ✅ All components integrate correctly

This is the ultimate validation that hyper2kvm works with actual VMware disk images, not just synthetic test data.
