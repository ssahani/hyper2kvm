# hyper2kvm 🚀

[![PyPI version](https://badge.fury.io/py/hyper2kvm.svg)](https://pypi.org/project/hyper2kvm/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/hyper2kvm)](https://pypi.org/project/hyper2kvm/)
[![License: LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/hyper2kvm/hyper2kvm.svg?style=social&label=Star&maxAge=2592000)](https://github.com/hyper2kvm/hyper2kvm/stargazers/)

[![Tests](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/tests.yml/badge.svg)](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/tests.yml)
[![Security](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/security.yml/badge.svg)](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/security.yml)
[![Pylint](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/pylint.yml/badge.svg)](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/pylint.yml)
[![RPM Packaging](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/rpm-packaging.yml/badge.svg)](https://github.com/hyper2kvm/hyper2kvm/actions/workflows/rpm-packaging.yml)
[![codecov](https://codecov.io/gh/hyper2kvm/hyper2kvm/branch/main/graph/badge.svg)](https://codecov.io/gh/hyper2kvm/hyper2kvm)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

**Production-Grade Hypervisor to KVM/QEMU Migration Toolkit** ⚡

`hyper2kvm` is a comprehensive toolkit for migrating virtual machines from multiple hypervisors and disk ecosystems (VMware, Hyper-V, cloud images, raw artifacts, physical exports) into reliable, bootable KVM/QEMU systems.

**Key Differentiator:** Unlike traditional migration tools that rely on "boot and hope," hyper2kvm applies deterministic offline fixes to ensure first-boot success through deep inspection, bootloader repair, driver injection, and network stabilization.

### 🎩 Built for the Enterprise Linux Ecosystem

**hyper2kvm** is designed with **Fedora** and **Red Hat Enterprise Linux (RHEL)** as first-class platforms, leveraging the powerful open-source virtualization stack that powers cloud infrastructure worldwide.

**Why Fedora/RHEL? 🚀**

- **Native KVM Integration:** Red Hat invented and maintains KVM - the Linux kernel virtualization module that powers AWS, Google Cloud, and OpenStack
- **libguestfs Excellence:** Deep integration with libguestfs (also Red Hat-originated) for safe, offline VM manipulation
- **SELinux Security:** First-class support for SELinux-enabled migrations - critical for enterprise deployments
- **Dracut Framework:** Advanced initramfs handling for RHEL/Fedora/CentOS systems
- **Enterprise DNA:** Built on the same stack that powers mission-critical workloads globally

**Perfect Fit for:**
- 🏢 RHEL 9/10 infrastructure migrations
- 🔄 VMware to OpenStack transitions (RH OpenStack, RDO)
- ☁️ Hybrid cloud deployments (AWS ← → On-Premises RHEL)
- 🐧 Fedora workstation/server consolidation
- 🎯 CentOS Stream development environments

Whether you're running **Fedora 43**, **RHEL 10**, **CentOS Stream**, or **Rocky Linux**, hyper2kvm speaks your language natively - from NetworkManager to systemd-networkd, from dracut to grub2-mkconfig.

---

## Quick Start 🎯

### Installation

#### From PyPI (Recommended)

```bash
# Install system dependencies (Fedora/RHEL)
sudo dnf install -y python3-libguestfs libguestfs-tools qemu-img qemu-system-x86

# Minimal installation (works on RHEL 10 without additional repos)
pip install hyper2kvm

# Or with UI enhancements (recommended, requires rich library)
pip install hyper2kvm[ui]

# With vSphere support
pip install hyper2kvm[vsphere]

# Full installation with all features
pip install hyper2kvm[full]
```

> **Note for RHEL 10**: The Rich library for progress bars is not available in RHEL 10 base repositories. hyper2kvm works perfectly without it, falling back to simple progress logging. See [Optional Dependencies](docs/99-Optional-Dependencies.md) for details.

#### From Source

```bash
# Install system dependencies (Fedora/RHEL)
sudo dnf install -y python3-libguestfs libguestfs-tools qemu-img qemu-system-x86

# Clone and install
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm
pip install -e .
```

#### Package Locations

- **PyPI:** https://pypi.org/project/hyper2kvm/ (v0.1.0+)
- **GitHub:** https://github.com/hyper2kvm/hyper2kvm (primary development)
- **GitLab:** https://gitlab.com/hyper2kvm/hyper2kvm (auto-synced mirror)
- **Documentation:** [docs/](docs/)
- **Examples:** [examples/](examples/)

See [docs/INSTALL.md](docs/02-Installation.md) for Ubuntu/Debian, Arch, Alpine, macOS, and Windows (WSL).

#### Shell Completion (Optional)

Enable intelligent tab completion for bash, zsh, or fish shells:

```bash
# Install argcomplete
pip install argcomplete

# Install completion for your shell (interactive)
./completions/install-completions.sh

# Or install for a specific shell
./completions/install-completions.sh bash
./completions/install-completions.sh zsh
./completions/install-completions.sh fish
```

After installation, you can use tab completion:

```bash
hyper2kvm --<TAB>              # Shows all available options
hyper2kvm --vm<TAB>            # Completes to --vmdk, --vm-name, etc.
hyper2kvm --vmdk /path/<TAB>   # Path completion
```

See [completions/README.md](completions/README.md) for detailed installation instructions and troubleshooting.

### Basic Usage

```bash
# Convert local VMDK to qcow2 with automatic fixes
sudo python -m hyper2kvm local \
  --vmdk /path/to/disk.vmdk \
  --to-output /output/disk.qcow2 \
  --flatten --compress

# Migrate from vSphere with full inspection and fixes
# (powered by hypersdk for enterprise-grade VMware API integration)
sudo python -m hyper2kvm vsphere \
  --vcenter vcenter.example.com \
  --username admin@vsphere.local \
  --vm-name "Production-VM" \
  --vs-action export \
  --to-output /output/

# Live fix a running Linux VM via SSH
sudo python -m hyper2kvm live-fix \
  --host 192.168.1.100 \
  --user root \
  --fix-fstab --fix-grub --fix-network
```

For more examples, see [docs/QUICKSTART.md](docs/03-Quick-Start.md) and [examples/README.md](examples/README.md).

### High-Performance vSphere Exports (Optional) ⚡

For **3-5x faster** VM exports from vSphere/ESXi, install the optional [hypersdk](https://github.com/ssahani/hypersdk) daemon:

```bash
# Install hypersdk (Fedora/RHEL)
sudo dnf install hypersdk
sudo systemctl start hypervisord
sudo systemctl enable hypervisord

# Or from source
git clone https://github.com/ssahani/hypersdk
cd hypersdk
go build -o hypervisord ./cmd/hypervisord
sudo ./install.sh
```

Once installed, hyper2kvm automatically detects and uses hyperctl for exports:

```python
from hyper2kvm.vmware.transports import HYPERCTL_AVAILABLE, export_vm_hyperctl

if HYPERCTL_AVAILABLE:
    # Use high-performance daemon (parallel downloads, resume support)
    result = export_vm_hyperctl(
        vm_path="/datacenter/vm/my-vm",
        output_path="/output/",
        parallel_downloads=8,  # Concurrent downloads
    )
```

**Benefits:**
- ⚡ **3-5x faster** exports via parallel downloads
- 🔄 **Resumable downloads** with automatic retry
- 📊 **Real-time progress** tracking
- 🚀 **Background daemon** mode for automation
- 📦 **Batch processing** for multiple VMs

See [docs/HYPERCTL_INTEGRATION.md](docs/HYPERCTL_INTEGRATION.md) and [INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md) for details.

---

## Features ✨

### Core Capabilities 💪

- **Multi-Hypervisor Support:** VMware (vSphere, ESXi, Workstation), Hyper-V, AWS AMI, cloud images, raw disks 🔄
- **Offline Fixing:** Deterministic repairs using libguestfs without booting the VM 🛠️
- **Windows VirtIO Injection:** Automated driver injection with two-phase boot strategy 🪟
- **Linux Bootloader Repair:** GRUB/GRUB2 regeneration for BIOS and UEFI systems 🐧
- **Network Stabilization:** Remove MAC pinning, clean VMware artifacts, support multiple network managers 🌐
- **Snapshot Handling:** Intelligent flattening of VMware snapshot chains 📸
- **Format Conversion:** VMDK, VHD/VHDX, QCOW2, RAW, VDI with compression support 💾
- **Validation:** Boot smoke tests via libvirt or direct QEMU ✅

### Production-Ready Features 🏭

- **YAML Configuration:** Version-controlled, mergeable configuration files 📝
- **Batch Processing:** Parallel multi-VM migrations ⚙️
- **Resume Support:** Crash recovery with checkpointing 🔄
- **Dry-Run Mode:** Preview changes without applying them 👀
- **Detailed Reporting:** Comprehensive migration reports and logs 📊
- **vSphere Integration:** Native API support via govc, pyvmomi, and hyperctl (high-performance provider) ☁️

### V2V-Style Migration Features 🚚

**Enterprise-grade batch migration capabilities for large-scale VM conversions:**

- **Batch Orchestration:** Multi-VM parallel conversions with configurable worker limits 🔄
- **Migration Profiles:** 7 built-in profiles (production, testing, minimal, fast, windows, archive, debug) + custom profile support with inheritance 📋
- **Pre/Post Hooks:** Execute custom scripts, Python functions, or HTTP webhooks at 7 pipeline stages ⚡
  - Hook stages: pre_extraction, post_extraction, pre_fix, post_fix, pre_convert, post_convert, post_validate
  - Retry logic with exponential backoff
  - Template variable substitution (15+ variables)
- **Libvirt XML Import:** Parse and convert existing libvirt VMs with automatic domain creation 🔄
- **Network & Storage Mapping:** Transform source networks/storage to target infrastructure 🗺️
  - Source network to target bridge mapping
  - MAC address policies (preserve/regenerate/custom)
  - Per-disk storage pool mappings
- **Direct Libvirt Integration:** Automatic domain definition, disk import to storage pools, snapshot creation 🔗
- **Checkpoint/Resume:** Crash-safe batch conversions with atomic checkpoint saves 💾
- **Progress Tracking:** Real-time progress persistence to JSON for external monitoring 📊
- **Validation Framework:** Extensible validation with 4 severity levels (INFO, WARNING, ERROR, CRITICAL) ✅
- **Profile Caching:** Performance optimization with mtime-based invalidation 🚀

**See:** [Batch Migration Guide](docs/Batch-Migration-Features-Guide.md) | [Quick Reference](docs/Batch-Migration-Quick-Reference.md)

### Safety Mechanisms 🔒

- Automatic backups (unless explicitly disabled) 💾
- Atomic file operations ⚛️
- Validation at every pipeline stage ✓
- Rollback capability for critical operations 🔙
- Security scanning (Bandit, pip-audit) via GitHub Actions 🛡️

---

## Documentation 📚

### Getting Started 🚀

- **[Quick Start Guide](docs/03-Quick-Start.md)** - Get migrating in 5 minutes ⚡
- **[Installation Guide](docs/02-Installation.md)** - Comprehensive installation for all platforms 🔧
- **[CLI Reference](docs/04-CLI-Reference.md)** - Complete command-line documentation 📖
- **[YAML Examples](docs/05-YAML-Examples.md)** - Configuration file templates 📝

### Deep Dive 🔬

- **[Architecture](docs/01-Architecture.md)** - System design and internal structure 🏗️
- **[Cookbook](docs/06-Cookbook.md)** - Common migration scenarios and solutions 👨‍🍳
- **[Failure Modes](docs/90-Failure-Modes.md)** - Troubleshooting guide 🔧

### Platform-Specific 🖥️

- **[Windows Migrations](docs/10-Windows-Guide.md)** - Windows-specific guide and VirtIO driver injection 🪟
- **[PhotonOS](docs/21-Photon-OS.md)** - VMware PhotonOS specific notes 🐧
- **[RHEL 10](docs/20-RHEL-10.md)** - RHEL 10 migration guide 🎩

### Examples 💡

- **[Example Configurations](examples/README.md)** - 40+ working examples 📦

---

## Table of Contents
1. Scope and Non-Goals
2. Design Principles
3. Codebase Architecture
4. Supported Inputs and Execution Modes
5. Pipeline Model
6. Control-Plane vs Data-Plane
7. Linux Fixes
8. Windows Handling
9. Snapshots and Flattening
10. Output Formats and Validation
11. YAML Configuration Model
12. Multi-VM and Batch Processing
13. Live-Fix Mode (SSH)
14. ESXi and vSphere Integration
15. Safety Mechanisms
16. Daemon Mode and Automation
17. Testing and Verification
18. Failure Modes and Troubleshooting
19. When Not to Use This Tool
20. Documentation Index and References  

---

## 1. Scope and Non-Goals

### What This Tool **Does**
- Converts hypervisor disks into KVM-usable formats
- Repairs Linux and Windows guests **offline**
- Applies selected Linux fixes **live over SSH**
- Stabilizes storage and network identifiers across hypervisors
- Injects Windows VirtIO drivers safely (**storage first, always**)
- Uses a **two-phase Windows boot strategy** (SATA bootstrap → VirtIO final) to guarantee driver activation
- Flattens snapshot chains deterministically
- Enables repeatable, automatable migrations via mergeable YAML
- Validates results using libvirt / QEMU smoke tests

While VMware remains the deepest and most battle-tested integration,  
`hyper2kvm` is intentionally **disk-centric**, not platform-centric.

If it can be reduced to **disks + metadata**, it can enter the pipeline.

---

## 2. Installation 🔧

### Quick Install ⚡

```bash
# 1. Install system dependencies (Fedora/RHEL/CentOS)
sudo dnf install -y python3-libguestfs libguestfs-tools qemu-img

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install hyper2kvm
pip install -e .
```

**Important:** `libguestfs` and `hivex` are system packages, NOT pip packages. They must be installed via your OS package manager (dnf, apt, zypper).

See [docs/INSTALL.md](docs/02-Installation.md) for detailed installation instructions for all Linux distributions, macOS, and Windows (WSL).

---

## 3. Design Principles

`hyper2kvm` is built around a small set of non-negotiable principles:

* **Determinism over luck**  
  Every action should be repeatable, inspectable, and explainable.  
  If a migration “just happens to boot,” something is missing.

* **Disk-centric, not platform-centric**  
  Hypervisors are treated as *sources of disks and metadata*, not as sacred systems.

* **Control-plane separated from data-plane**  
  Decisions are made before bytes move.  
  Byte movers never guess.

* **Offline-first repairs**  
  Guests should boot correctly on first power-on in KVM, without emergency console work.

* **Explicit plans over implicit behavior**  
  Snapshot flattening, driver injection, and boot strategy are always planned, never inferred mid-flight.

* **Safety by default**  
  Backups, atomic writes, and reversible changes are standard—not optional.

These principles are enforced structurally, not by convention.

---

## 3. Codebase Architecture

`hyper2kvm` is organized into **14 logical packages** with clear separation of concerns, making it easy to navigate, extend, and maintain.

### Package Structure

```
hyper2kvm/
├── cli/
│   └── args/              # CLI argument parsing (6 modules)
│       ├── builder.py     # HelpFormatter + epilog builder
│       ├── groups.py      # 21 argument group builders
│       ├── validators.py  # 18 validation functions
│       ├── helpers.py     # Helper functions (_merged_*, _require, etc.)
│       ├── parser.py      # Main parser orchestration
│       └── __init__.py    # Package exports
│
├── config/                # YAML configuration loading and merging
│
├── converters/            # Format conversion
│   ├── extractors/        # Disk format extractors (4 modules)
│   │   ├── ami.py         # AWS AMI extraction (1,019 lines)
│   │   ├── ovf.py         # OVF/OVA handling (567 lines)
│   │   ├── raw.py         # RAW disk processing (646 lines)
│   │   └── vhd.py         # VHD/VHDX handling (669 lines)
│   └── qemu/              # QEMU conversion (1 module)
│       └── converter.py   # qemu-img wrapper (879 lines)
│
├── core/                  # Core utilities and logging
│
├── fixers/                # Guest OS repair modules
│   ├── bootloader/        # Bootloader fixes (2 modules)
│   │   ├── fixer.py       # Generic bootloader fixer (641 lines)
│   │   └── grub.py        # GRUB-specific fixes (1,102 lines)
│   ├── filesystem/        # Filesystem fixes (2 modules)
│   │   ├── fixer.py       # Filesystem repair (923 lines)
│   │   └── fstab.py       # /etc/fstab rewriting (178 lines)
│   ├── live/              # Live migration (SSH) (2 modules)
│   │   ├── mode.py        # Live-fix orchestrator
│   │   └── ssh_client.py  # SSH connection handling
│   ├── network/           # Network configuration fixes (6 modules)
│   │   ├── model.py       # Data models and enums (434 lines)
│   │   ├── discovery.py   # Config file discovery (362 lines)
│   │   ├── topology.py    # Topology graph building (417 lines)
│   │   ├── validation.py  # Post-fix validation (131 lines)
│   │   ├── backend.py     # Backend-specific fixers (859 lines)
│   │   └── core.py        # Main orchestrator (418 lines)
│   ├── offline/           # Offline helper utilities (5 modules)
│   │   ├── mount.py       # Disk mounting (566 lines)
│   │   ├── vmware_tools_remover.py  # VMware Tools cleanup (454 lines)
│   │   ├── fstab_crypttab_rewriter.py
│   │   ├── spec_converter.py
│   │   └── validation_manager.py
│   └── windows/           # Windows fixes (3-tier structure, 18 modules)
│       ├── registry/      # Registry manipulation (6 modules)
│       │   ├── base.py    # Base registry operations
│       │   ├── driver.py  # Driver registry edits
│       │   ├── bcd.py     # BCD handling
│       │   └── ...
│       └── virtio/        # VirtIO driver injection (7 modules)
│           ├── injector.py  # Driver injection orchestrator
│           ├── scanner.py   # Driver file discovery
│           └── ...
│
├── modes/                 # Operational modes
│   ├── inventory_mode.py  # VM inventory scanning (318 lines)
│   └── plan_mode.py       # Migration planning (161 lines)
│
├── orchestrator/          # Pipeline orchestration
│   ├── orchestrator.py    # Main pipeline coordinator (358 lines)
│   ├── disk_processor.py  # Disk processing (335 lines)
│   ├── vsphere_exporter.py # vSphere export (264 lines)
│   └── disk_discovery.py  # Disk discovery (247 lines)
│
└── vmware/                # VMware integration
    ├── clients/           # VMware API clients (3 modules)
    │   ├── client.py      # VMwareClient (vSphere API)
    │   ├── vddk_client.py # VDDK client (1,245 lines)
    │   └── govc_client.py # govc wrapper
    ├── transports/        # Download/export methods (8 modules)
    │   ├── http_client.py # HTTPS download with progress
    │   ├── ssh_client.py  # SSH/SCP fallback
    │   ├── ovftool_client.py  # ovftool wrapper
    │   ├── session_cookie.py  # vSphere session management
    │   └── ...
    ├── vsphere/           # vSphere-specific implementations (4 modules)
    │   ├── mode.py        # Main vSphere orchestrator (1,470 lines)
    │   ├── command.py     # vSphere CLI commands
    │   └── ...
    └── utils/             # VMware utilities (4 modules)
        ├── vmdk_parser.py # VMDK descriptor parsing
        ├── vmx_parser.py  # VMX file parsing
        └── ...
```

### Package Descriptions

#### `cli/args/`
**Purpose:** CLI argument parsing split into focused modules
- **builder.py** - Custom HelpFormatter and epilog generation
- **groups.py** - 21 functions adding argument groups (vsphere, OVF, AMI, etc.)
- **validators.py** - 18 validation functions for command-line arguments
- **helpers.py** - Utility functions for config merging and resolution
- **parser.py** - Main `build_parser()` and `parse_args_with_config()` orchestration

**Key Pattern:** Backward compatibility maintained via `__init__.py` re-exports

#### `converters/`
**Purpose:** Disk format conversion and extraction

**extractors/** - Format-specific extraction logic:
- **ami.py** - AWS AMI extraction with partition handling
- **ovf.py** - OVF/OVA parsing and disk extraction
- **raw.py** - RAW disk format processing
- **vhd.py** - VHD/VHDX extraction (Hyper-V disks)

**qemu/** - QEMU-based conversion:
- **converter.py** - qemu-img wrapper for format conversion (vmdk → qcow2, etc.)

#### `fixers/`
**Purpose:** Guest OS repair modules (Linux and Windows)

**bootloader/** - Bootloader repair:
- **fixer.py** - Generic bootloader detection and fixing
- **grub.py** - GRUB-specific fixes (BIOS and UEFI)

**filesystem/** - Filesystem repairs:
- **fixer.py** - Filesystem check and repair (fsck, etc.)
- **fstab.py** - `/etc/fstab` rewriting with UUID stabilization

**network/** - Network configuration fixes (7 backends supported):
- **model.py** - Data models (`NetworkConfig`, `FixLevel`, enums)
- **discovery.py** - Config file discovery across distros
- **topology.py** - Dependency graph building for interface renames
- **validation.py** - Post-fix validation
- **backend.py** - Backend-specific fixers (netplan, systemd-networkd, ifcfg-rh, etc.)
- **core.py** - Main `NetworkFixer` orchestrator

**offline/** - Offline repair utilities:
- **mount.py** - Disk mounting and inspection via libguestfs
- **vmware_tools_remover.py** - VMware Tools cleanup
- **fstab_crypttab_rewriter.py** - fstab/crypttab rewriting
- **spec_converter.py** - Device specifier conversion (LABEL → UUID)
- **validation_manager.py** - Validation orchestration

**windows/** - Windows-specific fixes (3-tier structure):
- **registry/** - Windows registry manipulation (6 modules)
  - `base.py` - Base registry operations
  - `driver.py` - Driver registry edits
  - `bcd.py` - BCD (Boot Configuration Database) handling
- **virtio/** - VirtIO driver injection (7 modules)
  - `injector.py` - Main driver injection orchestrator
  - `scanner.py` - Driver file discovery and validation

**live/** - Live migration over SSH:
- **mode.py** - Live-fix orchestrator (apply fixes to running VMs)
- **ssh_client.py** - SSH connection and command execution

#### `modes/`
**Purpose:** Operational modes (inventory, planning)
- **inventory_mode.py** - VM inventory scanning and risk assessment (318 lines)
- **plan_mode.py** - Migration planning and preview (161 lines)

**Note:** Both files are small, focused, and require no further refactoring.

#### `orchestrator/`
**Purpose:** Pipeline orchestration (FETCH → FLATTEN → FIX → CONVERT → VALIDATE)
- **orchestrator.py** - Main pipeline coordinator (358 lines)
- **disk_processor.py** - Disk processing logic (335 lines)
- **vsphere_exporter.py** - vSphere export coordination (264 lines)
- **disk_discovery.py** - Disk discovery and metadata extraction (247 lines)

#### `vmware/`
**Purpose:** VMware integration (vSphere, ESXi, govc, VDDK)

**clients/** - VMware API clients:
- **client.py** - Main VMwareClient (pyvmomi/pyVim wrapper)
- **vddk_client.py** - VDDK (VMware Virtual Disk Development Kit) client
- **govc_client.py** - govc CLI wrapper

**transports/** - Data-plane download/export methods:
- **http_client.py** - HTTPS download with progress and resume support
- **hyperctl_common.py** - hyperctl CLI wrapper (hypersdk daemon, 3-5x faster than govc)
- **ssh_client.py** - SSH/SCP fallback transport
- **ovftool_client.py** - ovftool wrapper for OVF/OVA export
- **session_cookie.py** - vSphere session cookie management
- **vddk_transport.py** - VDDK-based disk export

**vsphere/** - vSphere-specific orchestration:
- **mode.py** - Main vSphere mode orchestrator (1,470 lines)
- **command.py** - vSphere CLI command implementations

**utils/** - VMware utilities:
- **vmdk_parser.py** - VMDK descriptor parsing
- **vmx_parser.py** - VMX configuration file parsing

### Import Patterns

#### Package-Level Imports (Recommended)
```python
# Network fixer
from hyper2kvm.fixers.network import NetworkFixer

# Converters
from hyper2kvm.converters.extractors import AMI, OVF, RAW, VHD
from hyper2kvm.converters.qemu import Convert

# VMware clients
from hyper2kvm.vmware.clients import VMwareClient
from hyper2kvm.vmware.transports import HTTPDownloadClient

# CLI args
from hyper2kvm.cli.args import build_parser, validate_args
```

#### Backward Compatibility (Still Works)
```python
# Old-style imports still work via wrapper modules
from hyper2kvm.fixers.network_fixer import NetworkFixer
from hyper2kvm.vmware.vmware_client import VMwareClient
from hyper2kvm.cli.argument_parser import build_parser
```

All modules maintain backward compatibility via wrapper files in original locations.

### Developer Guide

#### Where to Add New Functionality

**New network backend (e.g., Alpine Linux `interfaces` format):**
→ `fixers/network/backend.py` - Add new `fix_alpine_interfaces()` method

**New disk format extractor (e.g., Parallels `.pvm`):**
→ `converters/extractors/parallels.py` - Create new extractor class
→ `converters/extractors/__init__.py` - Export new class

**New VMware transport method (e.g., NFS datastore access):**
→ `vmware/transports/nfs_client.py` - Implement new transport
→ Update `vmware/vsphere/mode.py` to use new transport

**New Windows driver injection strategy:**
→ `fixers/windows/virtio/` - Add new injection module
→ Update `fixers/windows/virtio/injector.py` to orchestrate

**New CLI validation:**
→ `cli/args/validators.py` - Add new `_validate_*()` function
→ Update `cli/args/validators.py:validate_args()` to call it

#### Code Quality Standards

All modules follow these standards:
- **Type annotations:** 100% coverage in new code (network package standard)
- **Imports:** `from __future__ import annotations` for forward references
- **Dependencies:** Zero circular dependencies (enforced)
- **Docstrings:** Comprehensive module and function docstrings
- **Single Responsibility:** Each module has one clear purpose
- **Size limit:** Modules over 1,000 lines should be considered for splitting

### Architecture Highlights

**Zero Circular Dependencies:**
All packages have clean dependency graphs. The refactoring specifically eliminated circular dependencies by:
- Separating data models from business logic
- Using composition over inheritance
- Keeping interfaces in base modules

**Composition Over Inheritance:**
Rather than deep class hierarchies, modules use composition:
```python
# NetworkFixer composes specialized components
class NetworkFixer:
    def __init__(self):
        self.discovery = NetworkDiscovery()
        self.topology = NetworkTopology()
        self.validation = NetworkValidation()
        self.backend = NetworkFixersBackend()
```

**Backward Compatibility:**
All reorganizations maintain 100% backward compatibility via wrapper modules that re-export from new locations.

**Package Exports:**
Each package has an `__init__.py` that exports public APIs, allowing clean imports:
```python
# fixers/network/__init__.py
from .core import NetworkFixer
from .model import FixLevel, NetworkConfig, InterfaceType

__all__ = ["NetworkFixer", "FixLevel", "NetworkConfig", "InterfaceType"]
```

---

## 4. Supported Inputs and Execution Modes

### Hypervisor-Agnostic by Design

`hyper2kvm` is **not a VMware-only tool**.

VMware happens to be the most deeply integrated source today because it is:
- Common in enterprises
- Snapshot-heavy
- Full of sharp edges

Architecturally, **hyper2kvm does not care about hypervisors**.  
It cares about:

- Disks
- Firmware assumptions
- Boot chains
- Drivers
- Metadata quality

Any platform that can ultimately produce **block devices + minimal metadata**
can be migrated.

```mermaid
flowchart LR
  HV1[VMware]
  HV2[Hyper-V]
  HV3[Cloud / AMI]
  HV4[Physical / Raw]
  HV5[Other Hypervisors]

  HV1 --> D[Disks + Metadata]
  HV2 --> D
  HV3 --> D
  HV4 --> D
  HV5 --> D

  D --> P[hyper2kvm Pipeline]
  P --> K[KVM / QEMU]

  style HV1 fill:#FF9800,stroke:#E65100,color:#fff
  style HV2 fill:#FF9800,stroke:#E65100,color:#fff
  style HV3 fill:#FF9800,stroke:#E65100,color:#fff
  style HV4 fill:#FF9800,stroke:#E65100,color:#fff
  style HV5 fill:#FF9800,stroke:#E65100,color:#fff
  style D fill:#9C27B0,stroke:#6A1B9A,color:#fff
  style P fill:#4CAF50,stroke:#2E7D32,color:#fff
  style K fill:#2196F3,stroke:#1565C0,color:#fff
```

The moment disks are available, **all inputs converge**.

---

### Primary: VMware (Deep Integration)

* Descriptor VMDK
* Monolithic VMDK
* Multi-extent snapshot chains
* OVA
* OVF + extracted disks
* ESXi over SSH / SCP
* vCenter / ESXi via:

  * **govc** (primary control-plane)
  * **pyvmomi / pyVim** (fallback and deep inspection)

Used for:

* Inventory
* Snapshot planning
* CBT discovery
* Datastore browsing
* Artifact resolution

This is the most mature path in `hyper2kvm`.

---

### Hyper-V / Microsoft Disk Formats (Disk-Level)

Supported as **artifact inputs**, without Hyper-V APIs:

* VHD
* VHDX

Handled via offline inspection, repair, and deterministic driver transitions.

---

### Cloud Images / AMIs (Artifact-Level)

Supported once reduced to disks:

* AWS AMI / EBS snapshots (exported to raw / qcow2)
* Generic cloud images

Fixes include:

* NVMe vs virtio assumptions
* initramfs completeness
* Network configs bound to cloud metadata
* Bootloader defaults that fail off-cloud

No cloud lifecycle or IAM handling is included.

---

### Generic Disk Artifacts

Any block-attachable format:

* raw
* qcow2
* vdi
* vmdk
* vhd / vhdx

Once inside, all inputs are treated equally.

---

## 5. Pipeline Model

All execution modes map to a single internal pipeline:

```
FETCH → FLATTEN → INSPECT → FIX → CONVERT → VALIDATE
```

Stages are optional. **Order is not.**

| Stage    | Purpose                     |
| -------- | --------------------------- |
| FETCH    | Obtain disks and metadata   |
| FLATTEN  | Collapse snapshot chains    |
| INSPECT  | Detect OS, layout, firmware |
| FIX      | Apply deterministic repairs |
| CONVERT  | Produce qcow2 / raw / etc   |
| VALIDATE | Boot-test and verify        |

The pipeline is explicit, inspectable, and restart-safe.

---

## 6. Control-Plane vs Data-Plane (Architecture)

This separation is the **spine** of `hyper2kvm`.

* **Control-Plane** decides *what exists* and *what should happen*
* **Data-Plane** moves bytes and produces artifacts

If you mix them, you get “it worked once” migrations.
If you separate them, you get repeatable ones.

```mermaid
flowchart TB
  subgraph CP["CONTROL PLANE (decide)"]
    GOVC["govc (primary)"]
    HYPERCTL["hyperctl → hypervisord<br/>high-performance daemon"]
    PYVM["pyvmomi / pyVim<br/>fallback / deep inspection"]
    INV["Inventory: VM, disks,<br/>firmware, snapshots"]
    PLAN["Plans: snapshot flatten,<br/>disk map, export intent"]
    DS["Datastore browsing &<br/>artifact resolution"]
    CBT["CBT discovery +<br/>changed ranges planning"]

    GOVC --> INV
    HYPERCTL --> INV
    GOVC --> DS
    GOVC --> CBT
    HYPERCTL --> CBT
    PYVM --> INV
    PYVM --> CBT
    INV --> PLAN
    DS --> PLAN
    CBT --> PLAN
  end

  META["plans + metadata<br/>explicit, auditable"]

  subgraph DP["DATA PLANE (move bytes)"]
    GOVCEXP["govc export.ovf /<br/>export.ova"]
    HYPEREXP["hypervisord export<br/>parallel downloads<br/>3-5x faster, resumable"]
    OVFTOOL["ovftool<br/>OVF/OVA export/import"]
    HTTP["HTTP /folder +<br/>Range requests"]
    VDDK["VDDK<br/>high-throughput disk reads"]
    SSH["SSH / SCP<br/>fallback"]
    RESUME["resume + verify +<br/>atomic publish"]
  end

  CP --> META --> DP
  GOVCEXP --> RESUME
  HYPEREXP --> RESUME
  OVFTOOL --> RESUME
  HTTP --> RESUME
  VDDK --> RESUME
  SSH --> RESUME

  style CP fill:#2196F3,stroke:#1565C0,color:#fff
  style DP fill:#4CAF50,stroke:#2E7D32,color:#fff
  style META fill:#9C27B0,stroke:#6A1B9A,color:#fff
  style GOVC fill:#FF9800,stroke:#E65100,color:#fff
  style HYPERCTL fill:#F44336,stroke:#C62828,color:#fff
  style HYPEREXP fill:#F44336,stroke:#C62828,color:#fff
  style PYVM fill:#FFC107,stroke:#F57C00,color:#000
  style RESUME fill:#00BCD4,stroke:#006064,color:#fff
```

**Rule**

* Control-plane never moves bulk data
* Data-plane never makes inventory decisions

The bridge is always **explicit plans + metadata**.

---

## 7. Linux Fixes

* `/etc/fstab` rewrite (`UUID=` / `PARTUUID=` preferred)
* GRUB root stabilization (BIOS + UEFI)
* initramfs regeneration (distro-aware)
* Network cleanup (MAC pinning, hypervisor artifacts)

---

## 8. Windows Handling

Windows is a **first-class citizen**.

* VirtIO storage injected as **BOOT_START**
* Offline registry and hive edits
* `CriticalDeviceDatabase` fixes
* BCD handling with backups
* Two-phase boot: SATA bootstrap → VirtIO final
* Driver plans are **data-driven** (JSON/YAML)

No blind binary patching. Everything is logged and reversible.

---

## 9. Snapshots and Flattening

* Recursive descriptor resolution
* Parent-chain verification
* Flatten **before** conversion
* Atomic outputs

---

## 10. Output Formats and Validation

**Formats**

* qcow2 (recommended)
* raw
* vdi

**Validation**

* Checksums
* libvirt smoke boots
* Direct QEMU boots
* BIOS and UEFI
* Headless supported

---

## 11. YAML Configuration Model

YAML is treated as **code**:

* Mergeable
* Reviewable
* Rerunnable

```bash
--config base.yaml --config vm.yaml --config overrides.yaml
```

---

## 12–20. Advanced Topics

* Batch processing
* Live-fix mode (SSH)
* ESXi and vSphere integration
* Safety mechanisms
* Daemon and automation modes
* Testing and failure analysis
* Explicit non-goals

---

## 21. Documentation Index and References

Complete documentation is available in the [`docs/`](docs/) directory:

- **Getting Started:** [QUICKSTART.md](docs/03-Quick-Start.md), [INSTALL.md](docs/02-Installation.md)
- **Reference:** [CLI_REFERENCE.md](docs/04-CLI-Reference.md), [YAML-EXAMPLES.md](docs/05-YAML-Examples.md)
- **Architecture:** [ARCHITECTURE.md](docs/01-Architecture.md), [orchestrator/README.md](hyper2kvm/orchestrator/README.md)
- **Platform Guides:** [WINDOWS.md](docs/10-Windows-Guide.md), [PHOTONOS.md](docs/21-Photon-OS.md), [RHEL10.md](docs/20-RHEL-10.md)
- **Troubleshooting:** [FAILURE_MODES.md](docs/90-Failure-Modes.md), [cookbook.md](docs/06-Cookbook.md)
- **Development:** [BUILDING.md](docs/BUILDING.md) - Build, test, and development guide

---

## Contributing

We welcome contributions! Here's how to get started:

### Development Setup

```bash
# Clone the repository
git clone https://github.com/ssahani/hyper2kvm.git
cd hyper2kvm

# Quick start (recommended)
make quickstart

# Or manually
pip install hatch
pip install -e .[dev,full]

# Run tests
make test          # Using Make
hatch run test     # Using Hatch

# Run linting and security checks
make lint          # Using Make
make security      # Security scans
hatch run ci       # Full CI pipeline using Hatch
```

See [BUILDING.md](docs/BUILDING.md) for complete build and testing documentation.

### Contribution Guidelines

1. **Fork and Branch:** Create a feature branch from `main`
2. **Code Standards:**
   - Follow PEP 8 style guidelines
   - Add type annotations for all new code
   - Write comprehensive docstrings
   - Keep modules under 1,000 lines when possible
3. **Testing:**
   - Add unit tests for new features
   - Ensure all tests pass (`pytest tests/`)
   - Run security scans (`bandit -r hyper2kvm/`)
4. **Documentation:**
   - Update relevant documentation in `docs/`
   - Add examples to `examples/README.md` if applicable
   - Update `ARCHITECTURE.md` for structural changes
5. **Pull Requests:**
   - Write clear commit messages
   - Reference related issues
   - Ensure CI passes (tests, linting, security)

See [ARCHITECTURE.md](docs/01-Architecture.md) for detailed architecture guidelines.

### Reporting Issues

- **Bugs:** Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
- **Features:** Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md)
- **Security:** Email security issues privately (see SECURITY.md if available)

---

## License

This project is licensed under the **GNU Lesser General Public License v3.0 (LGPL-3.0)**.

See [LICENSE](LICENSE) for full license text.

**Key Points:**
- You can use hyper2kvm in proprietary software without making your code open source
- Modifications to hyper2kvm itself must be released under LGPL-3.0
- No warranty provided (see license for details)

---

## Support

### Community Support

- **GitHub Discussions:** Ask questions and share experiences
- **Issue Tracker:** Report bugs and request features
- **Documentation:** Comprehensive guides in [`docs/`](docs/)

### Professional Support

For enterprise support, consulting, or custom development:
- Open a [support request issue](https://github.com/ssahani/hyper2kvm/issues/new?template=support.md)
- Contact the maintainers directly

---

## Acknowledgments

hyper2kvm builds on excellent open-source projects:

- **[libguestfs](https://libguestfs.org/)** - Offline disk inspection and modification
- **[QEMU](https://www.qemu.org/)** - Disk format conversion and virtualization
- **[govc](https://github.com/vmware/govmomi/tree/master/govc)** - vSphere CLI
- **[pyvmomi](https://github.com/vmware/pyvmomi)** - VMware vSphere API Python SDK
- **[hypersdk](https://github.com/ssahani/hypersdk)** - High-performance multi-cloud provider daemon (optional, 3-5x faster exports)
- **[libvirt](https://libvirt.org/)** - Virtualization management

Special thanks to all [contributors](https://github.com/ssahani/hyper2kvm/graphs/contributors).

---

## Project Status

**Current Status:** Active development

- **Latest Release:** Check [releases](https://github.com/ssahani/hyper2kvm/releases)
- **Build Status:** [![CI](https://github.com/ssahani/hyper2kvm/workflows/tests/badge.svg)](https://github.com/ssahani/hyper2kvm/actions)
- **Security:** [![Security](https://github.com/ssahani/hyper2kvm/workflows/security/badge.svg)](https://github.com/ssahani/hyper2kvm/actions)

---

**Made with ❤️ for reliable VM migrations**
