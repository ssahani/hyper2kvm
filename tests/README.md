# hyper2kvm Test Suite

Comprehensive test suite for hyper2kvm VM conversion tool.

## Quick Start

```bash
# Run all tests
pytest tests/unit/

# Run with coverage
pytest tests/unit/ --cov=hyper2kvm --cov-report=html

# Run specific test file
pytest tests/unit/test_vmware/test_vmdk_integration.py -v
```

## Test Suite Status

- **Total Tests:** 149
- **Passing:** 144 (96.6%)
- **Skipped:** 5 (3.4% - optional modules)
- **Failing:** 0
- **Execution Time:** ~0.90 seconds

## Directory Structure

```
tests/
├── make-test-images.py          # VMDK test image generator
├── make-test-vm-image.py        # Simple VM image generator
├── make-bootable-test-vm.py     # Bootable VM image generator (libguestfs)
├── test-data/                   # Generated test images
│   ├── README.md
│   ├── .gitignore
│   ├── test.vmdk               # VMDK descriptor
│   ├── test-flat.vmdk          # Flat extent
│   ├── test-multi.vmdk         # Multi-extent descriptor
│   ├── test-s{001,002,003}.vmdk # Extent files
│   ├── malicious/              # Security test images
│   ├── subdir/                 # Subdirectory test
│   ├── large.vmdk              # Large descriptor test
│   └── binary.vmdk             # Binary file test
└── unit/                        # Unit tests
    ├── test_cli/               # CLI tests
    ├── test_config/            # Configuration tests
    ├── test_converters/        # Converter tests
    ├── test_core/              # Core functionality tests
    ├── test_fixers/            # Fixer tests
    ├── test_libvirt/           # LibVirt tests
    ├── test_orchestrator/      # Orchestrator tests
    ├── test_ssh/               # SSH tests
    ├── test_testers/           # QEMU tester tests
    └── test_vmware/            # VMWARE tests
        ├── test_vmdk_info.py        # VMDK info parser (10 tests)
        ├── test_vmdk_parser.py      # VMDK parser (14 tests)
        ├── test_vmdk_security.py    # Security tests (16 tests)
        └── test_vmdk_integration.py # Integration tests (13 tests)
```

## Test Image Generators

See [VM_IMAGE_GENERATORS.md](VM_IMAGE_GENERATORS.md) for comprehensive documentation.

### Quick Reference

```bash
# Generate VMDK test images
python make-test-images.py all test-data/

# Generate simple VM image
python make-test-vm-image.py minimal test.qcow2

# Generate bootable VM (requires libguestfs)
python make-bootable-test-vm.py ubuntu --output ubuntu.img
```

## Running Tests

```bash
# All tests
pytest tests/unit/

# Specific category
pytest tests/unit/test_vmware/ -v

# With coverage
pytest tests/unit/ --cov=hyper2kvm --cov-report=html
```

## Documentation

- **[VM_IMAGE_GENERATORS.md](VM_IMAGE_GENERATORS.md)** - Image generator guide
- **[TEST_IMAGE_INTEGRATION.md](../TEST_IMAGE_INTEGRATION.md)** - Integration summary
- **[TEST_SUMMARY.md](../TEST_SUMMARY.md)** - Test suite status
- **[test-data/README.md](test-data/README.md)** - Test data info

## Prerequisites

```bash
# Minimal (unit tests only)
pip install pytest pytest-cov

# For integration tests
python make-test-images.py all test-data/

# For bootable images (optional)
sudo apt install python3-guestfs libguestfs-tools  # Debian/Ubuntu
sudo dnf install python3-libguestfs libguestfs-tools  # Fedora/RHEL
```

See full documentation in [VM_IMAGE_GENERATORS.md](VM_IMAGE_GENERATORS.md).
