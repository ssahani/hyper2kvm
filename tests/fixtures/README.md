# Test Fixtures 🧪

This directory contains test fixtures and helper utilities for hyper2kvm testing.

## Test Images 💾

### Creating Test Images

Generate realistic VM disk images for testing:

```bash
# Option 1: Using Python script (recommended)
python3 create_test_images.py

# Option 2: Using shell script (requires sudo for filesystem creation)
sudo bash create_test_images.sh
```

This creates test images in `images/` directory:
- `test-linux-qcow2.qcow2` - Linux VM with ext4 filesystem, fstab, grub, network config
- `test-linux-raw.img` - RAW format Linux disk
- `test-linux-vmdk.vmdk` - VMDK format (converted from QCOW2)

### Using Test Images in Tests

Test images are available as pytest fixtures:

```python
def test_disk_inspection(test_linux_qcow2_image):
    """test_linux_qcow2_image is automatically provided by pytest"""
    assert test_linux_qcow2_image.exists()

    # Use with guestfs
    import guestfs
    g = guestfs.GuestFS()
    g.add_drive_opts(str(test_linux_qcow2_image), format="qcow2", readonly=True)
    g.launch()
    g.mount("/dev/sda1", "/")

    # Test fstab exists
    assert g.exists("/etc/fstab")
    fstab_content = g.cat("/etc/fstab")
    assert "UUID" in fstab_content
```

Available fixtures:
- `test_linux_qcow2_image` - Linux QCOW2 with full filesystem
- `test_linux_raw_image` - Linux RAW format
- `test_linux_vmdk_image` - Linux VMDK format
- `test_windows_qcow2_image` - Minimal Windows image
- `test_images_dir` - Directory containing all images
- `cleanup_test_image` - Create temporary images that auto-cleanup

### Test Image Contents

Each Linux test image contains:

```
/
├── boot/
│   └── grub2/
│       └── grub.cfg           # Test GRUB configuration
├── etc/
│   ├── fstab                  # UUID-based mounts
│   ├── hostname              # test-linux-vm
│   ├── hosts                 # Localhost entries
│   ├── test-marker           # Marker file for verification
│   └── sysconfig/
│       └── network-scripts/
│           ├── ifcfg-eth0    # DHCP interface
│           └── ifcfg-eth1    # Static IP interface
├── var/
├── usr/
└── home/
```

## Fake Modules 🎭

### fake_guestfs.py

Mock libguestfs module for testing without actual libguestfs:

```python
from tests.fixtures.fake_guestfs import FakeGuestFS

def test_without_real_guestfs():
    g = FakeGuestFS()
    g.add_drive_opts("/path/to/disk.qcow2")
    g.launch()
    # ... test your code ...
```

### fake_logger.py

Mock logger for testing logging behavior:

```python
from tests.fixtures.fake_logger import FakeLogger

def test_logging():
    logger = FakeLogger()
    logger.info("test message")
    assert "test message" in logger.messages
```

## Manual Test Image Creation

If you want to create custom test images:

```bash
# Create a 1GB QCOW2 image
qemu-img create -f qcow2 custom-test.qcow2 1G

# Create with guestfs (Python)
python3 << 'EOF'
import guestfs
g = guestfs.GuestFS()
g.disk_create("custom-test.qcow2", "qcow2", 1024*1024*1024)
g.add_drive_opts("custom-test.qcow2", format="qcow2", readonly=False)
g.launch()
g.part_disk("/dev/sda", "mbr")
g.mkfs("ext4", "/dev/sda1")
g.mount("/dev/sda1", "/")
g.mkdir_p("/boot")
g.mkdir_p("/etc")
g.write("/etc/fstab", "/dev/sda1 / ext4 defaults 0 1\n")
g.umount("/")
g.shutdown()
g.close()
EOF
```

## Requirements

For full test image creation:
- `python3-libguestfs` (system package)
- `qemu-utils` or `qemu-img`
- For Windows images: additional setup required

Install on Fedora:
```bash
sudo dnf install python3-libguestfs qemu-img
```

Install on Ubuntu:
```bash
sudo apt-get install python3-guestfs qemu-utils
```

## CI/CD Integration

In GitHub Actions, test images are created automatically:

```yaml
- name: Create test images
  run: |
    sudo apt-get install python3-guestfs qemu-utils
    python3 tests/fixtures/create_test_images.py
```

## Troubleshooting

**Issue: Permission denied creating images**
```bash
# Make script executable
chmod +x create_test_images.sh

# Run with sudo if needed
sudo python3 create_test_images.py
```

**Issue: libguestfs not found**
```bash
# Install system package (NOT pip)
sudo dnf install python3-libguestfs  # Fedora
sudo apt-get install python3-guestfs  # Ubuntu
```

**Issue: Test images too large for CI**
- Test images are in `.gitignore`
- Created fresh in CI environment
- Kept minimal (1-2GB each)
