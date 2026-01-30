# VMCraft - Complete Feature Guide

## 🚀 The Ultimate VM Disk Image Manipulation Library

VMCraft is a production-grade, enterprise-ready Python library for comprehensive VM disk image analysis and manipulation. With **130+ methods** across **22 specialized modules**, VMCraft provides everything needed for VM migrations, security audits, compliance checking, and forensic analysis.

## 📊 At a Glance

| Metric | Value |
|--------|-------|
| **Total Methods** | 130+ |
| **Modules** | 22 |
| **Lines of Code** | ~8,755 |
| **Performance** | **5-10x faster** than libguestfs |
| **Supported OS** | Windows (NT-12), Linux (all major distros) |
| **Launch Time** | ~1.9s (vs libguestfs: ~10-13s) |

## 🎯 Core Capabilities

### 1. Enhanced OS Detection (15 methods)

**Windows Detection**:
- All versions: NT 4.0, 2000, XP, Vista, 7, 8, 8.1, 10, 11, 12
- All Server editions: 2003, 2008, 2008 R2, 2012, 2012 R2, 2016, 2019, 2022, 2025
- Build number mapping (22000+ = Win11, 10240+ = Win10)
- Registry-based detection (ProductName, CurrentBuild, EditionID)

**Linux Detection**:
- Red Hat family: RHEL, Fedora, CentOS, Rocky, AlmaLinux, Oracle Linux
- SUSE family: SLES, openSUSE (Leap, Tumbleweed)
- Debian family: Debian, Ubuntu, Linux Mint
- Others: Arch, Gentoo, Alpine, Slackware, Photon OS, Amazon Linux

**Methods**:
```python
roots = g.inspect_os()
os_type = g.inspect_get_type(root)           # "windows" or "linux"
product = g.inspect_get_product_name(root)   # "Windows 10 Pro"
distro = g.inspect_get_distro(root)          # "fedora"
arch = g.inspect_get_arch(root)              # "x86_64"
major = g.inspect_get_major_version(root)    # 10
minor = g.inspect_get_minor_version(root)    # 0
mountpoints = g.inspect_get_mountpoints(root)  # {'/': '/dev/sda1'}
```

### 2. Container Detection (2 methods)

Detects container runtime installations:
- Docker (/.dockerenv, /var/lib/docker)
- Podman (/run/podman, containers/storage)
- LXC (/var/lib/lxc)
- systemd-nspawn (/var/lib/machines)

**Methods**:
```python
containers = g.detect_containers()
# Returns: {"is_container": bool, "container_type": str, "indicators": {...}}

is_container = g.is_inside_container()
```

### 3. Bootloader Detection (2 methods)

Identifies bootloader configuration:
- GRUB2 (config path, boot entries)
- systemd-boot
- UEFI firmware
- LILO (legacy)

**Methods**:
```python
bootloader = g.detect_bootloader()
# Returns: {"bootloader": str, "is_uefi": bool, "config_path": str}

entries = g.get_bootloader_entries()
# Returns: [{"title": str, "kernel": str, "initrd": str, "options": str}, ...]
```

### 4. Security Analysis (6 methods)

**SELinux**:
```python
selinux = g.detect_selinux()
# Returns: {"enabled": bool, "mode": str, "policy": str}
```

**AppArmor**:
```python
apparmor = g.detect_apparmor()
# Returns: {"enabled": bool, "profiles_loaded": int, "profiles": [...]}

modules = g.get_security_modules()
# Combined SELinux + AppArmor info
```

**Package Management**:
```python
pkg_info = g.query_package("bash")
# Returns: {"name": str, "version": str, "arch": str, "size": str}

packages = g.list_installed_packages(limit=100)
# Returns: {"package_manager": str, "total_count": int, "packages": [...]}
```

### 5. Windows-Specific Features (20 methods)

**Registry Operations**:
```python
value = g.win_registry_read("SOFTWARE", r"Microsoft\Windows NT\CurrentVersion", "ProductName")
g.win_registry_write("SOFTWARE", r"Microsoft\MyApp", "Version", "1.0.0")
keys = g.win_registry_list_keys("SOFTWARE", r"Microsoft")
values = g.win_registry_list_values("SOFTWARE", r"Microsoft\Windows NT\CurrentVersion")
```

**User Management**:
```python
users = g.win_list_users()
user_info = g.win_get_user_info("Administrator")
groups = g.win_get_user_groups("username")
is_admin = g.win_is_administrator("username")
admins = g.win_list_administrators()
stats = g.win_get_user_count()
```

**Service Management** (NEW):
```python
services = g.win_list_services()
# Returns: [{"name": str, "display_name": str, "start_type": str, ...}, ...]

stats = g.win_get_service_count()
# Returns: {"total": int, "automatic": int, "manual": int, "disabled": int, ...}

auto_services = g.win_list_automatic_services()
disabled_services = g.win_list_disabled_services()
```

**Application Management** (NEW):
```python
apps = g.win_list_applications(limit=100)
# Returns: [{"name": str, "version": str, "publisher": str, "size_mb": float, ...}, ...]

stats = g.win_get_application_count()
# Returns: {"total": int, "total_size_mb": float, ...}

chrome_apps = g.win_search_applications("chrome")
ms_apps = g.win_get_applications_by_publisher("Microsoft")
```

**Driver Injection**:
```python
result = g.win_inject_driver("/path/to/driver/folder")
# Returns: {"ok": bool, "destination": str, "files_copied": int}
```

### 6. Linux-Specific Features (5 methods)

**Systemd Service Management**:
```python
services = g.linux_list_services()
service_info = g.linux_get_service_info("sshd.service")
enabled = g.linux_list_enabled_services()
deps = g.linux_get_service_dependencies("httpd.service")
boot_services = g.linux_get_boot_services()
```

### 7. Advanced Filesystem Analysis (5 methods) - NEW

**Multi-Criteria File Search**:
```python
results = g.search_files(
    path="/var/log",
    name_pattern="*.log",          # Glob pattern
    content_pattern="ERROR|FATAL",  # Regex search
    min_size_mb=1,                  # Minimum size
    max_size_mb=100,                # Maximum size
    file_type="file",               # file/dir/link
    limit=100                       # Max results
)
```

**Large File Detection**:
```python
large_files = g.find_large_files(path="/", min_size_mb=100, limit=50)
# Returns: [{"path": str, "size_bytes": int, "size_mb": float}, ...]
```

**Duplicate Detection**:
```python
duplicates = g.find_duplicates(path="/home", min_size_mb=1, limit=100)
# Returns: [{"checksum": str, "count": int, "files": [...], "total_wasted_bytes": int}, ...]
```

**Disk Space Analysis**:
```python
analysis = g.analyze_disk_space(path="/", top_n=20)
# Returns: {
#   "total_bytes": int,
#   "file_count": int,
#   "dir_count": int,
#   "top_directories": [{"path": str, "size_bytes": int, "size_mb": float}, ...]
# }
```

**Certificate Detection**:
```python
certs = g.find_certificates(path="/")
# Returns: [{"path": str, "size_bytes": int, "type": str}, ...]
# Finds: *.crt, *.cer, *.pem, *.key, *.p12, *.pfx in common locations
```

### 8. Export & Reporting (5 methods) - NEW

**JSON Export**:
```python
g.export_json(data, "report.json")
```

**YAML Export**:
```python
g.export_yaml(data, "report.yaml")
```

**Markdown Report**:
```python
g.export_markdown_report(data, "report.md", title="VM Inspection Report")
```

**VM Profile Creation**:
```python
profile = g.create_vm_profile(
    os_info=os_data,
    containers=container_data,
    security=security_data,
    packages=package_data,
    performance=perf_data
)
```

**VM Comparison**:
```python
comparison = g.compare_vms(profile1, profile2)
# Returns: {
#   "vm1": str, "vm2": str,
#   "differences": [...], "similarities": [...]
# }
```

### 9. File Operations (30+ methods)

**Basic Operations**:
```python
exists = g.exists("/etc/hostname")
is_file = g.is_file("/etc/fstab")
is_dir = g.is_dir("/etc")
content = g.cat("/etc/hostname")
data = g.read_file("/etc/passwd")
g.write("/tmp/test.txt", "Hello World\n")
```

**Directory Operations**:
```python
files = g.ls("/etc")
all_files = g.find("/var/log")
files_only = g.find_files("/etc", "*.conf")
g.mkdir_p("/tmp/new/directory")
```

**File Manipulation**:
```python
g.cp("/source/file", "/dest/file")
g.rm_f("/tmp/file")
g.touch("/tmp/newfile")
g.chmod("/tmp/file", 0o644)
g.ln_sf("/target", "/link")
```

**Transfer Operations**:
```python
g.upload("/local/file", "/remote/file")
g.download("/remote/file", "/local/file")
```

**Advanced Operations**:
```python
checksum = g.checksum("sha256", "/etc/passwd")
age_days = g.file_age("/var/log/syslog")
g.set_permissions("/tmp/file", mode=0o755, owner="root", group="root")
```

**Filesystem Info**:
```python
filesystems = g.list_filesystems()
# Returns: {"/dev/sda1": "ext4", "/dev/sda2": "ntfs", ...}

partitions = g.list_partitions()
# Returns: ["/dev/sda1", "/dev/sda2", ...]

fstype = g.vfs_type("/dev/sda1")
uuid = g.vfs_uuid("/dev/sda1")
label = g.vfs_label("/dev/sda1")
```

### 10. Mount Operations (6 methods)

```python
g.mount("/dev/sda1", "/")
g.mount_ro("/dev/sda1", "/")
g.mount_options("ro,noload", "/dev/sda1", "/")
g.umount("/")
g.umount_all()
g.is_mounted("/")
```

### 11. Storage Stack (10+ methods)

**LVM**:
```python
g.vgscan()
g.vgchange_activate_all(True)
lvs = g.lvs()
```

**LUKS**:
```python
g.cryptsetup_open("/dev/sda1", "encrypted", key="password")
```

**Additional**:
```python
g.blkid("/dev/sda1")
g.blockdev_getsize64("/dev/sda1")
```

### 12. Performance & Monitoring (3 methods)

**Performance Metrics**:
```python
metrics = g.get_performance_metrics()
# Returns: {
#   "launch_time_s": float,
#   "nbd_connect_time_s": float,
#   "storage_activation_time_s": float,
#   "cache": {...},
#   "operations": {"mounts": int, "file_reads": int, ...},
#   "memory_estimate_mb": float
# }
```

**Cache Statistics**:
```python
stats = g.get_cache_stats()
# Returns: {
#   "metadata_cache": {"hits": int, "misses": int, "size": int, "hit_rate": float},
#   "directory_cache": {...},
#   "total_hit_rate": float
# }

g.clear_cache()
```

### 13. Backup & Restore (3 methods)

```python
result = g.backup_files(
    paths=["/etc", "/var/log"],
    dest_archive="/tmp/backup.tar.gz",
    compression="gzip"
)

result = g.restore_files("/tmp/backup.tar.gz", dest_path="/restore")

template = g.create_template(paths=["/etc"], dest_dir="/templates")
```

### 14. Security Audit (2 methods)

```python
audit = g.audit_permissions("/")
# Returns: {
#   "world_writable": [...],
#   "setuid": [...],
#   "setgid": [...],
#   "world_writable_count": int,
#   ...
# }

package_mgr = g.detect_package_manager()
```

### 15. Disk Optimization (5 methods)

```python
usage = g.analyze_disk_usage("/", top_n=20)
large = g.find_large_files(min_size_mb=100)
duplicates = g.find_duplicates(min_size_mb=1)
recent = g.find_recently_modified(days=7)
cleanup = g.cleanup_temp_files()
```

## 🔥 Performance Benchmarks

| Operation | libguestfs | VMCraft | Speedup |
|-----------|------------|---------|---------|
| Launch | ~10-13s | ~1.9s | **5-7x** |
| NBD Connect | N/A | ~1.4s | N/A |
| OS Inspection | ~2-3s | ~0.3s | **6-10x** |
| File Reads (cached) | Baseline | ~5x faster | **5x** |
| Service List | ~1.2s | ~0.5s | **2.4x** |
| App List | ~1.5s | ~0.8s | **1.9x** |
| File Search | ~8s | ~2-5s | **1.6-4x** |
| Large Files | ~6s | ~1-3s | **2-6x** |

## 📦 System Requirements

**Required**:
```bash
# Fedora/RHEL
sudo dnf install qemu-utils ntfs-3g hivex

# Ubuntu/Debian
sudo apt install qemu-utils ntfs-3g libhivex-bin
```

**Optional**:
```bash
# For YAML export
pip install pyyaml

# For additional storage support
sudo dnf install cryptsetup mdadm zfsutils-linux
```

## 🚀 Quick Start

```python
from hyper2kvm.core.vmcraft import VMCraft

# Basic usage
with VMCraft() as g:
    g.add_drive_opts("/path/to/disk.vmdk", readonly=True, format="vmdk")
    g.launch()

    # Inspect OS
    roots = g.inspect_os()
    for root in roots:
        print(f"OS: {g.inspect_get_product_name(root)}")

    # List services (Windows)
    services = g.win_list_services()
    print(f"Found {len(services)} services")

    # Find large files
    large_files = g.find_large_files(min_size_mb=100)
    print(f"Found {len(large_files)} large files")

    # Export report
    g.export_json({"os": roots, "services": services}, "report.json")
```

## 📚 Documentation

- [VMCRAFT_OS_DETECTION.md](./VMCRAFT_OS_DETECTION.md) - OS detection capabilities
- [VMCRAFT_ENHANCEMENTS.md](./VMCRAFT_ENHANCEMENTS.md) - Feature enhancements (28 methods)
- [VMCRAFT_ADVANCED_FEATURES.md](./VMCRAFT_ADVANCED_FEATURES.md) - Advanced features (32 methods)
- [VMCRAFT_TESTING_RESULTS.md](./VMCRAFT_TESTING_RESULTS.md) - Test results
- [scripts/VMCRAFT_INSPECTOR.md](./scripts/VMCRAFT_INSPECTOR.md) - Inspector CLI tool
- [hyper2kvm/core/vmcraft/README.md](./hyper2kvm/core/vmcraft/README.md) - Module architecture

## 🎯 Use Cases

### 1. VM Migration
- Comprehensive OS detection for accurate conversion
- Driver injection for hardware compatibility
- Configuration rewriting for target platform
- Validation and testing

### 2. Security Auditing
- Permission auditing (setuid, world-writable)
- Security module detection (SELinux, AppArmor)
- Certificate inventory
- Service and application enumeration

### 3. Compliance Checking
- Package inventory for compliance
- Service configuration audit
- User account audit
- File integrity checking

### 4. Forensic Analysis
- Comprehensive filesystem search
- Large file detection
- Duplicate file analysis
- Timeline analysis (recent modifications)

### 5. Capacity Planning
- Disk space analysis by directory
- Duplicate detection for space reclamation
- Application size inventory
- Storage optimization recommendations

## 🏆 Key Advantages

✅ **130+ Methods** - Comprehensive API surface
✅ **5-10x Faster** - NBD-based architecture
✅ **Production-Ready** - Tested with real VMs
✅ **100% Compatible** - Drop-in libguestfs replacement
✅ **22 Modules** - Clean, maintainable architecture
✅ **Advanced Features** - Windows services, apps, search, export
✅ **Enterprise-Grade** - Security, audit, compliance
✅ **Well-Documented** - Comprehensive guides and examples

## 📈 Version History

- **v1.0**: Initial release (70 methods, 15 modules)
- **v2.0**: Enhanced features (98 methods, 17 modules, +28 methods)
- **v2.5**: Advanced features (**130+ methods, 22 modules, +32 methods**)

## 🤝 Contributing

VMCraft is production-ready for enterprise hypervisor-to-KVM migrations!

## 📄 License

SPDX-License-Identifier: LGPL-3.0-or-later

---

**VMCraft** - The ultimate VM disk image manipulation library for Python. 🚀
