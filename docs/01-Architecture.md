# ARCHITECTURE.md — hyper2kvm Internal Architecture

## Purpose

This document provides an in-depth exploration of **hyper2kvm's module-level architecture**, execution flow, and core architectural principles.

It's designed for:
* **Contributors** wanting to understand the codebase structure
* **Reviewers** evaluating design decisions and implementation quality
* **Power users** seeking to extend or customize the migration pipeline

hyper2kvm is laser-focused on fixing "successful" conversions that fail at boot, lose network connectivity, or exhibit instability post-migration. This architecture document explains how the modular design achieves reliability through:

* **Deterministic inspection** over assumption-based heuristics
* **Offline-first fixing** to avoid runtime dependencies
* **Strict separation** between control-plane and data-plane operations
* **Composable pipeline stages** that enforce predictable ordering

---

## The Canonical Pipeline

At the heart of every migration is this invariant flow:

**FETCH → FLATTEN → INSPECT → PLAN → FIX → CONVERT → VALIDATE / TEST**

Not every command executes every stage, but **the order is sacred**. Stages can be skipped, but never reordered or interleaved.

### Pipeline Stages Explained

#### FETCH
Acquire source disks and metadata from any source:
- vSphere APIs (via pyvmomi or govc)
- ESXi hosts via SSH/SCP
- Local filesystem paths
- HTTP datastore downloads
- VDDK high-speed transfers
- OVA/OVF archives

**Key principle:** Source-agnostic acquisition with unified interface.

#### FLATTEN
Transform complex disk chains into single-image files:
- Collapse VMware snapshot chains (delta extents)
- Resolve VMDK descriptor file references
- Merge linked clones into standalone images
- Normalize quirky vendor formats

**Output:** Clean, single-file disk images ready for inspection.

#### INSPECT
Offline deep-dive using libguestfs to extract ground truth:
- OS family detection (Linux vs Windows)
- Firmware type (BIOS vs UEFI)
- Partition layouts and mount points
- Bootloader configuration (GRUB, GRUB2, systemd-boot)
- Network interface configurations
- Installed drivers and kernel modules
- Critical system files (/etc/fstab, initramfs, etc.)

**Philosophy:** Derive facts, never guess. Inspection over assumption.

#### PLAN
Strategic planning before execution:
- Inventory scans (read-only VM discovery)
- Dry-run simulations (what-if analysis)
- Dependency resolution
- Resource requirement calculation

**Value:** Plan smart, execute once. No trial-and-error.

#### FIX
Apply deterministic patches to ensure bootability:
- **Offline fixes** (default): libguestfs-based disk mutations, no boot required
- **Live fixes** (opt-in): SSH-based corrections on running guests
- fstab rewriting (UUID/PARTUUID over by-path)
- Bootloader regeneration (GRUB config, initramfs)
- Network cleanup (remove MAC pinning, VMware artifacts)
- Windows VirtIO driver injection
- VMware Tools removal

**Guarantee:** Idempotent operations that tolerate re-runs.

#### CONVERT
Image format transformation via qemu-img:
- VMDK → qcow2 (default)
- Support for raw, VDI, VHDX
- Compression and sparse allocation
- Disk resizing (expansion/shrinkage)

**Integration:** Optional virt-v2v pre/post-processing hooks.

#### VALIDATE / TEST
Ruthless verification:
- Boot smoke tests (QEMU direct or libvirt domains)
- Network connectivity checks
- Filesystem integrity validation
- Performance benchmarking

**Motto:** Does it boot? Does it network? Does it survive? Prove it.

---

## Repository Structure (Authoritative)

This reflects the **actual codebase structure** as of the latest refactor:

```
hyper2kvm/
├── __init__.py                       # Package root
├── __main__.py                       # Entry point (python -m hyper2kvm)
│
├── cli/                              # Command-line interface layer
│   ├── __init__.py
│   ├── argument_parser.py            # Main argument parser (legacy entry)
│   ├── help_texts.py                 # User-facing help documentation
│   └── args/                         # Refactored argument parsing (modular)
│       ├── __init__.py
│       ├── builder.py                # Argument builder pattern
│       ├── groups.py                 # Argument group definitions
│       ├── helpers.py                # Parsing utilities
│       ├── parser.py                 # Core parser logic
│       └── validators.py             # Argument validation rules
│
├── config/                           # Configuration management
│   ├── __init__.py
│   ├── config_loader.py              # YAML config loading and merging
│   └── systemd_template.py          # Systemd unit templates for guest injection
│
├── core/                             # Foundational utilities and infrastructure
│   ├── __init__.py
│   ├── cred.py                       # Credential handling (secure storage)
│   ├── exceptions.py                 # Custom exception hierarchy
│   ├── file_ops.py                   # File operation utilities
│   ├── guest_identity.py             # Guest OS identity detection
│   ├── guest_utils.py                # Guest-specific utilities
│   ├── list_utils.py                 # List manipulation helpers
│   ├── logger.py                     # Structured logging (rich console)
│   ├── logging_utils.py              # Logging configuration helpers
│   ├── optional_imports.py           # Graceful optional dependency handling
│   ├── recovery_manager.py           # Crash recovery and checkpointing
│   ├── retry.py                      # Retry logic with exponential backoff
│   ├── sanity_checker.py             # Pre-flight sanity checks
│   ├── utils.py                      # General-purpose utilities
│   ├── validation_suite.py           # Validation test suites
│   └── xml_utils.py                  # XML parsing and generation utilities
│
├── converters/                       # Disk transformation engines
│   ├── __init__.py
│   ├── disk_resizer.py               # Disk resizing operations
│   ├── fetch.py                      # Unified disk fetching interface
│   ├── flatten.py                    # Snapshot chain flattening
│   ├── extractors/                   # Archive/container extractors
│   │   ├── __init__.py
│   │   ├── ami.py                    # AWS AMI tarball extractor
│   │   ├── ovf.py                    # OVF/OVA unpacker
│   │   ├── raw.py                    # RAW/tarball extractor with security checks
│   │   └── vhd.py                    # VHD/VHDX handler (Azure/Hyper-V)
│   └── qemu/                         # QEMU image operations
│       ├── __init__.py
│       └── converter.py              # qemu-img wrapper (convert, resize, info)
│
├── fixers/                           # Guest OS repair and modification layer
│   ├── __init__.py
│   ├── base_fixer.py                 # Base class defining fixer interface
│   ├── cloud_init_injector.py        # Cloud-init metadata injection
│   ├── network_fixer.py              # Top-level network fixer coordinator
│   ├── offline_fixer.py              # Top-level offline fixer coordinator
│   ├── report_writer.py              # Migration report generation
│   │
│   ├── bootloader/                   # Bootloader fixing subsystem
│   │   ├── __init__.py
│   │   ├── fixer.py                  # Bootloader fixer orchestration
│   │   └── grub.py                   # GRUB/GRUB2 specific fixes
│   │
│   ├── filesystem/                   # Filesystem fixing subsystem
│   │   ├── __init__.py
│   │   ├── fixer.py                  # Filesystem fixer orchestration
│   │   └── fstab.py                  # /etc/fstab rewriting (UUID conversion)
│   │
│   ├── live/                         # Live (SSH-based) fixing subsystem
│   │   ├── __init__.py
│   │   ├── fixer.py                  # Live SSH fixer
│   │   └── grub_fixer.py             # Live GRUB regeneration via SSH
│   │
│   ├── network/                      # Network fixing subsystem
│   │   ├── __init__.py
│   │   ├── backend.py                # Network backend abstraction
│   │   ├── core.py                   # Core network fixing logic
│   │   ├── discovery.py              # Network interface discovery
│   │   ├── model.py                  # Network configuration models
│   │   ├── topology.py               # Network topology analysis
│   │   └── validation.py             # Network config validation
│   │
│   ├── offline/                      # Offline (libguestfs) fixing subsystem
│   │   ├── __init__.py
│   │   ├── config_rewriter.py        # System config file rewriting
│   │   ├── mount.py                  # Guest filesystem mounting
│   │   ├── spec_converter.py         # Spec file format conversions
│   │   ├── validation.py             # Offline fix validation
│   │   └── vmware_tools_remover.py   # Offline VMware Tools purge
│   │
│   └── windows/                      # Windows-specific fixing subsystem
│       ├── __init__.py
│       ├── fixer.py                  # Main Windows fixer orchestrator
│       ├── network_fixer.py          # Windows network fixing
│       ├── registry_core.py          # Registry manipulation core
│       ├── registry/                 # Windows Registry subsystem
│       │   ├── __init__.py
│       │   ├── encoding.py           # Registry value encoding/decoding
│       │   ├── firstboot.py          # First-boot registry tweaks
│       │   ├── io.py                 # Registry file I/O (hivex wrapper)
│       │   ├── mount.py              # Registry hive mounting
│       │   ├── software.py           # HKLM\Software modifications
│       │   └── system.py             # HKLM\System modifications
│       └── virtio/                   # Windows VirtIO driver injection
│           ├── __init__.py
│           ├── config.py             # VirtIO configuration
│           ├── core.py               # Core VirtIO injection logic
│           ├── detection.py          # VirtIO ISO detection
│           ├── discovery.py          # Driver discovery in VirtIO ISO
│           ├── install.py            # Driver installation to registry
│           ├── paths.py              # VirtIO ISO path resolution
│           └── utils.py              # VirtIO utilities
│
├── libvirt/                          # LibVirt integration layer
│   ├── domain_emitter.py             # Generic domain XML emitter
│   ├── libvirt_utils.py              # LibVirt utility functions
│   ├── linux_domain.py               # Linux-specific domain XML generation
│   └── windows_domain.py             # Windows-specific domain XML generation
│
├── modes/                            # Specialized operational modes
│   ├── __init__.py
│   ├── inventory_mode.py             # Read-only VM/disk inventory scanning
│   └── plan_mode.py                  # Dry-run planning mode (what-if)
│
├── orchestrator/                     # Pipeline orchestration layer
│   ├── __init__.py
│   ├── README.md                     # Refactoring documentation
│   ├── orchestrator.py               # Main pipeline coordinator (refactored)
│   ├── disk_discovery.py             # Input disk discovery logic
│   ├── disk_processor.py             # Disk processing pipeline executor
│   ├── virt_v2v_converter.py         # virt-v2v integration wrapper
│   └── vsphere_exporter.py           # vSphere VM export orchestration
│
├── ssh/                              # SSH/SCP transport layer
│   ├── __init__.py
│   ├── ssh_client.py                 # Paramiko-based SSH client
│   └── ssh_config.py                 # SSH connection configuration
│
├── testers/                          # Post-migration validation layer
│   ├── __init__.py
│   ├── libvirt_tester.py             # LibVirt domain boot testing
│   └── qemu_tester.py                # Direct QEMU boot testing
│
└── vmware/                           # VMware ecosystem integration
    ├── __init__.py
    ├── clients/                      # VMware API clients
    │   ├── __init__.py
    │   ├── client.py                 # pyvmomi SmartConnect wrapper
    │   ├── extensions.py             # vSphere API extensions
    │   └── nfc_lease.py              # NFC lease management for exports
    │
    ├── transports/                   # Data-plane transport implementations
    │   ├── __init__.py
    │   ├── govc_common.py            # govc CLI wrapper utilities
    │   ├── govc_export.py            # govc export operations
    │   ├── http_client.py            # HTTP datastore download client
    │   ├── http_progress.py          # HTTP download progress tracking
    │   ├── ovftool_client.py         # VMware ovftool wrapper
    │   ├── ovftool_loader.py         # ovftool dynamic loader
    │   ├── vddk_client.py            # VDDK high-speed transfer client
    │   └── vddk_loader.py            # VDDK dynamic library loader
    │
    ├── utils/                        # VMware utilities
    │   ├── __init__.py
    │   ├── datastore.py              # Datastore path parsing
    │   ├── utils.py                  # General VMware utilities
    │   ├── v2v.py                    # virt-v2v VMware integration
    │   └── vmdk_parser.py            # VMDK descriptor file parser
    │
    └── vsphere/                      # vSphere control-plane operations
        ├── __init__.py
        ├── command.py                # vSphere command abstraction
        ├── errors.py                 # vSphere error handling
        ├── govc.py                   # govc-specific operations
        └── mode.py                   # vSphere operational modes
```

**Total:** 27 directories, 117+ Python modules

---

## Orchestrator Architecture (Refactored)

The orchestrator was refactored from a single 1,197-line monolithic class into **5 focused components**, each under 300 lines and following the Single Responsibility Principle.

### Component Breakdown

#### 1. **Orchestrator** (`orchestrator/orchestrator.py`)
**Responsibility:** Main pipeline coordinator

**Key Methods:**
- `run()` - Execute full migration pipeline
- `_setup_recovery()` - Initialize crash recovery
- `_discover_disks()` - Delegate to DiskDiscovery
- `_process_disks()` - Delegate to DiskProcessor
- `_run_pre_v2v()` / `_run_post_v2v()` - Optional virt-v2v stages
- `_run_tests()` - Execute validation tests
- `_emit_domain_xml()` - Generate libvirt domain XML

**Philosophy:** Coordinate, don't implement. Delegate to specialists.

#### 2. **DiskDiscovery** (`orchestrator/disk_discovery.py`)
**Responsibility:** Input disk detection and preparation

**Supported Sources:**
- Local VMDK files
- Remote SSH fetch-and-fix
- OVA/OVF archives
- VHD/VHDX files
- RAW/IMG files
- AMI tarballs
- Live-fix mode (SSH to running guest)

**Output:** List of discovered disk paths + optional temp directory

#### 3. **DiskProcessor** (`orchestrator/disk_processor.py`)
**Responsibility:** Per-disk processing pipeline

**Pipeline Stages:**
1. Flatten (optional snapshot collapse)
2. Offline fixes (libguestfs modifications)
3. Convert to output format (qemu-img)
4. Validation (sanity checks)

**Features:**
- Serial or parallel processing
- Progress tracking
- Error isolation per-disk

#### 4. **VirtV2VConverter** (`orchestrator/virt_v2v_converter.py`)
**Responsibility:** virt-v2v integration

**Features:**
- Single or parallel conversion
- LUKS key handling (passphrase/keyfile)
- Automatic output discovery
- Temp file cleanup
- Retry logic

**Use Cases:**
- Pre-conversion for complex formats
- Post-conversion for additional fixes
- Standalone virt-v2v mode

#### 5. **VsphereExporter** (`orchestrator/vsphere_exporter.py`)
**Responsibility:** vSphere VM export orchestration

**Export Modes:**
- virt-v2v direct export
- Download-only (no conversion)
- VDDK high-speed transfer

**Features:**
- Snapshot management (create/delete)
- Credential resolution (env vars, YAML configs)
- Batch export with failure tracking
- VM name pattern matching

### Refactoring Benefits

| Aspect | Before (Monolithic) | After (Refactored) |
|--------|---------------------|-------------------|
| **Lines of Code** | 1,197 lines, 50+ methods | 5 files, each < 310 lines |
| **Testability** | Difficult to test in isolation | Each component independently testable |
| **Maintainability** | All concerns mixed | Single Responsibility Principle |
| **Reusability** | Tightly coupled | Components usable independently |
| **Debugging** | Hard to isolate failures | Clear component boundaries |

---

## Control-Plane vs Data-Plane (VMware)

VMware integration enforces strict separation between **what to do** (control) and **how to move bytes** (data).

### Control-Plane: Inventory, Planning, Orchestration

**Purpose:** Answer "what exists, where, and what's the plan?"

**Never touches bulk data** - keeps operations lean, fast, and auditable.

#### Implementation 1: govc (Primary)
**Tool:** VMware's official CLI (`govc`)

**Capabilities:**
- VM discovery (by name, UUID, MoRef)
- Snapshot tree traversal
- Disk path resolution (backings, controllers)
- Firmware detection (BIOS/UEFI)
- CBT (Changed Block Tracking) management
- Datastore browsing

**Why govc:**
- Stable, scriptable CLI
- Structured output (JSON)
- Real-world vSphere coverage
- Minimal memory footprint

**Integration:** `vmware/vsphere/govc.py` + `vmware/vsphere/command.py`

#### Implementation 2: pyvmomi / pyVim (Fallback)
**Library:** VMware's official Python SDK

**Use Cases:**
- Deep object graph traversals
- Advanced property queries
- Custom vCenter extensions
- Gaps in govc functionality

**Integration:** `vmware/clients/client.py` - SmartConnect wrapper with retry logic

**Details:**
- SOAP API connections via `SmartConnect`
- MoRef (Managed Object Reference) traversal
- Property retrieval via `RetrievePropertiesEx`
- SSL verification and authentication

#### CLI Glue Layer
**Modules:** `vmware/vsphere/mode.py` + `vmware/vsphere/command.py`

**Function:** Translate user commands (`vsphere inventory`, `vsphere plan`) into pure metadata operations. No data hauling.

---

### Data-Plane: Byte Movement

**Purpose:** Answer "how do we safely move disk data?"

**No inventory logic** - pure transport layer.

#### Transport 1: VDDK (Highest Performance)
**Library:** VMware Virtual Disk Development Kit

**Module:** `vmware/transports/vddk_client.py`

**Features:**
- Direct disk access over NBD or SAN
- Multi-threaded I/O
- CBT support for incremental transfers
- Throughput-optimized

**When to Use:** Large VMs, bandwidth-constrained environments

#### Transport 2: ovftool (Official VMware Export)
**Tool:** VMware OVF Tool

**Module:** `vmware/transports/ovftool_client.py`

**Features:**
- OVF/OVA export/import
- Compression and progress tracking
- OVF manifest validation
- Resumable exports

**When to Use:** Need OVF compatibility, vendor-specific flags

#### Transport 3: HTTP `/folder` (Datastore Downloads)
**Protocol:** HTTPS datastore browsing

**Module:** `vmware/transports/http_client.py`

**Features:**
- Range request support (resume partial downloads)
- CBT incremental downloads
- Stateless (no session management)

**When to Use:** Simple downloads, no VDDK available

#### Transport 4: SSH/SCP (Universal Fallback)
**Protocol:** SSH with SCP/SFTP

**Module:** `ssh/ssh_client.py`

**Features:**
- Key-based authentication
- File transfers with progress
- Command execution on ESXi hosts

**When to Use:** API access unavailable, ESXi direct access

#### Transport 5: govc export (CLI-Based)
**Tool:** govc export.ovf / export.ova

**Module:** `vmware/transports/govc_export.py`

**Features:**
- Simple CLI-based export
- Progress tracking
- Structured error handling

**When to Use:** Lightweight exports, scripting

---

## Fixer Subsystems (Deep Dive)

### Offline Fixing (Default Strategy)

**Module:** `fixers/offline/`

**Philosophy:** Modify disk images without booting. No runtime dependencies.

**Technology:** libguestfs (QEMU + kernel appliance)

**Advantages:**
- No systemd/init requirements
- No kernel module loading
- Works on corrupted/unbootable guests
- Deterministic outcomes

**Subsystems:**

#### 1. Filesystem Fixing (`fixers/filesystem/`)
- `/etc/fstab` rewriting (by-path → UUID/PARTUUID)
- Mount point validation
- Filesystem consistency checks

#### 2. Bootloader Fixing (`fixers/bootloader/`)
- GRUB configuration regeneration
- Initramfs rebuilding
- Kernel command-line updates
- UEFI boot entry management

#### 3. Config Rewriting (`fixers/offline/config_rewriter.py`)
- Systemd unit modifications
- Network configuration updates
- Service enablement/disablement

#### 4. VMware Tools Removal (`fixers/offline/vmware_tools_remover.py`)
- Package removal (offline dpkg/rpm manipulation)
- Service cleanup
- Artifact deletion

---

### Live Fixing (Opt-In Strategy)

**Module:** `fixers/live/`

**Philosophy:** Execute fixes on running Linux guests via SSH.

**Use Cases:**
- Fixes requiring running kernel (GRUB regeneration)
- Runtime-dependent operations
- Interactive troubleshooting

**Safety:**
- Explicit opt-in required
- Dry-run mode available
- Rollback mechanisms

---

### Windows Fixing (Hermetically Sealed)

**Module:** `fixers/windows/`

**Principle:** Windows logic **never leaks** into Linux fixers. Complete isolation.

#### Registry Subsystem (`fixers/windows/registry/`)

**Purpose:** Modify Windows Registry offline (no Windows boot required)

**Technology:** hivex (libguestfs registry manipulation)

**Operations:**
- Driver installation (VirtIO, storage, network)
- Service configuration
- First-boot scripts
- Hardware profile updates

**Modules:**
- `io.py` - Registry hive I/O (read/write)
- `encoding.py` - Registry value encoding
- `mount.py` - Hive mounting (SYSTEM, SOFTWARE, SAM)
- `firstboot.py` - First-boot tweaks
- `software.py` - HKLM\Software modifications
- `system.py` - HKLM\System modifications (drivers, services)

#### VirtIO Subsystem (`fixers/windows/virtio/`)

**Purpose:** Inject VirtIO drivers for KVM compatibility

**Challenge:** Windows won't boot on KVM without VirtIO drivers, but drivers can't be installed without booting.

**Solution:** Offline registry modification to pre-install drivers.

**Workflow:**
1. **Detection** (`detection.py`) - Locate VirtIO ISO (local/remote)
2. **Discovery** (`discovery.py`) - Extract drivers matching guest OS version
3. **Installation** (`install.py`) - Add driver registry entries
4. **Configuration** (`config.py`) - Configure driver load order

**Drivers Injected:**
- `viostor` - Storage controller
- `netkvm` - Network adapter
- `vioscsi` - SCSI controller
- `viorng` - RNG device
- `balloon` - Memory ballooning

---

### Network Fixing (Cross-Platform)

**Module:** `fixers/network/`

**Architecture:** Modular backend system supporting multiple network managers.

**Backends Supported:**
- NetworkManager (RHEL/Fedora/CentOS)
- netplan (Ubuntu/Debian)
- systemd-networkd
- ifupdown (legacy Debian)
- Windows network stack (separate module)

**Components:**

#### Discovery (`discovery.py`)
- Detect network interfaces (physical/virtual)
- Identify MAC addresses and interface names
- Detect existing configuration files

#### Topology (`topology.py`)
- Build network topology map
- Detect bridging/bonding
- VLAN detection

#### Core (`core.py`)
- Apply network fixes
- Generate new configurations
- Remove VMware-specific settings

#### Validation (`validation.py`)
- Validate network configurations
- Check for conflicts
- Ensure bootability

#### Backend (`backend.py`)
- Abstract network manager differences
- Unified configuration API
- Backend auto-detection

**Fixes Applied:**
- Remove MAC address pinning
- Delete VMware-specific routes
- Clean up stale interface configs
- Regenerate predictable interface names
- Configure for DHCP (default)

---

## LibVirt Integration

**Module:** `libvirt/`

**Purpose:** Generate libvirt domain XML for migrated VMs

**Components:**

### Domain Emitter (`domain_emitter.py`)
Generic XML generation framework

### Linux Domain (`linux_domain.py`)
Linux-specific domain XML:
- Virtio devices (disk, network, RNG)
- CPU topology
- Memory configuration
- BIOS/UEFI firmware selection

### Windows Domain (`windows_domain.py`)
Windows-specific domain XML:
- Hyper-V enlightenments
- QEMU guest agent
- VirtIO device configuration
- UEFI with Secure Boot support

**Output:** Ready-to-import libvirt XML (`virsh define domain.xml`)

---

## Core Utilities

**Module:** `core/`

The foundational layer providing infrastructure for all other modules.

### Essential Utilities

#### Guest Identity (`guest_identity.py`)
- OS detection (Linux distro, Windows version)
- Architecture detection (x86_64, aarch64)
- Kernel version parsing

#### Recovery Manager (`recovery_manager.py`)
- Crash recovery checkpoints
- Resume from partial migrations
- Cleanup on abort

#### Retry Logic (`retry.py`)
- Exponential backoff
- Configurable retry limits
- Exception filtering

#### Validation Suite (`validation_suite.py`)
- Pre-flight sanity checks
- Post-migration validation
- Regression test framework

#### File Operations (`file_ops.py`)
- Safe file I/O with atomic writes
- Temporary file management
- Checksum verification

#### Logging (`logger.py`, `logging_utils.py`)
- Rich console output (colors, progress bars)
- Structured logging (JSON)
- Log level management

---

## Key Architectural Invariants

These principles are **non-negotiable**. Violating them leads to unreliable migrations.

### 1. Offline is the Default Truth

Unless explicitly marked `live`, all fixers assume:
- **No systemd** or init systems running
- **No kernel modules** can be loaded
- **Only libguestfs** disk access

**Runtime dependencies belong in `fixers/live/`.**

### 2. Inspection Over Assumption

Never guess. Always derive facts from:
- libguestfs inspection
- Partition table analysis
- Filesystem examination
- Bootloader configuration parsing

**Code must handle "unexpected but valid" configurations gracefully.**

### 3. `/dev/disk/by-path` is Radioactive

VMware uses by-path references extensively. KVM **does not**.

**All fixer code must:**
- Detect by-path references in fstab, GRUB configs, crypttab
- Replace with UUID or PARTUUID
- Verify replacement correctness

**This is the #1 cause of boot failures if missed.**

### 4. Windows Logic is Hermetically Sealed

**Windows-specific code lives exclusively in `fixers/windows/`.**

Linux fixers:
- Detect Windows guests
- Immediately return / skip
- **Never attempt** Windows-specific operations

**Cross-contamination is forbidden.**

### 5. Control-Plane and Data-Plane Never Mix

**Control-plane** (`vmware/vsphere/`, `vmware/clients/`):
- Inventory queries
- Metadata operations
- Planning and orchestration

**Data-plane** (`vmware/transports/`):
- Disk downloads
- Byte transfer
- Bandwidth optimization

**No module should perform both.** Separation ensures:
- Auditability (what metadata was collected?)
- Performance (control-plane doesn't bottleneck on I/O)
- Security (minimize attack surface for credential use)

### 6. Idempotent, Best-Effort Behavior

Fixers should:
- **Tolerate re-runs** (detect already-applied fixes)
- **Contain failures** (one fixer failure doesn't abort entire pipeline)
- **Report loudly** (log all actions, successes, and failures)

**Only critical failures (unbootable guest) should halt the pipeline.**

---

## Module Ownership and Responsibilities

### `cli/`
**Owns:** User-facing command-line interface, argument parsing, help text.
**Does NOT own:** Business logic, execution.

### `config/`
**Owns:** Configuration file loading (YAML), merging, defaults.
**Does NOT own:** Configuration validation (done in `core/sanity_checker.py`).

### `core/`
**Owns:** Cross-cutting concerns (logging, errors, retries, recovery, validation).
**Does NOT own:** Domain-specific logic.

### `converters/`
**Owns:** Format conversions (VMDK→qcow2), extractions (OVA, AMI, VHD), disk operations.
**Does NOT own:** Guest OS modifications (that's `fixers/`).

### `fixers/`
**Owns:** Guest OS modifications (offline and live), bootloader fixes, network cleanup, Windows drivers.
**Does NOT own:** Disk format conversions (that's `converters/`).

### `libvirt/`
**Owns:** LibVirt domain XML generation.
**Does NOT own:** QEMU execution (that's `testers/qemu_tester.py`).

### `modes/`
**Owns:** Read-only operational modes (inventory, planning).
**Does NOT own:** Write operations (migrations).

### `orchestrator/`
**Owns:** Pipeline coordination, stage ordering, component delegation.
**Does NOT own:** Stage implementation (delegates to specialists).

### `ssh/`
**Owns:** SSH/SCP transport, remote command execution.
**Does NOT own:** What commands to execute (that's `fixers/live/`).

### `testers/`
**Owns:** Post-migration validation (boot tests, network tests).
**Does NOT own:** Migration itself.

### `vmware/`
**Owns:** VMware-specific integrations (vSphere API, VDDK, govc).
**Does NOT own:** Generic disk operations (that's `converters/`).

---

## Why This Architecture Works

### Predictability
- **Fixed pipeline order** eliminates non-deterministic behavior
- **Inspection-based fixes** remove guesswork
- **Idempotent operations** allow safe retries

### Reliability
- **Offline-first** means no runtime dependencies
- **Hermetic isolation** (Windows, VMware, etc.) prevents cross-contamination
- **Component separation** isolates failures

### Maintainability
- **Single Responsibility Principle** (refactored orchestrator)
- **Clear module boundaries** (ownership table above)
- **Focused components** (all under 300 lines)

### Extensibility
- **Pluggable fixers** (add new fixer, register in orchestrator)
- **Pluggable transports** (add new VMware transport)
- **Pluggable network backends** (add new network manager)

### Debuggability
- **Structured logging** with timestamps and context
- **Component isolation** (easy to trace failures)
- **Validation at every stage** (fail fast with clear errors)

---

## Adding New Features

### Where Does My Feature Go?

#### 1. New Disk Source (e.g., Azure Blob, S3)
**Location:** `converters/extractors/azure.py` or `converters/fetch.py`
**Hook:** Register in `orchestrator/disk_discovery.py`

#### 2. New Fix (e.g., SELinux relabeling)
**Location:** `fixers/offline/selinux_fixer.py` or extend `fixers/offline/config_rewriter.py`
**Hook:** Call from `orchestrator/disk_processor.py`

#### 3. New Network Manager (e.g., wicked for SUSE)
**Location:** `fixers/network/backend.py` (add backend class)
**Hook:** Auto-detected via backend discovery

#### 4. New Validation Test (e.g., storage performance)
**Location:** `testers/storage_tester.py`
**Hook:** Call from `orchestrator/orchestrator.py:_run_tests()`

#### 5. New VMware Transport (e.g., NBD direct)
**Location:** `vmware/transports/nbd_client.py`
**Hook:** Register in `vmware/transports/__init__.py`

### Feature Addition Checklist

1. **Identify module boundary** (don't violate separation of concerns)
2. **Check for existing extension point** (don't duplicate)
3. **Write unit tests** (isolated component tests)
4. **Update this ARCHITECTURE.md** (document new component)
5. **Add integration test** (end-to-end validation)
6. **Update user documentation** (if user-visible feature)

---

## Performance Considerations

### Parallel Processing

#### Disk Processing
**Module:** `orchestrator/disk_processor.py`

**Option:** `args.parallel_processing = True`

**Implementation:** ThreadPoolExecutor (multiple disks processed concurrently)

**When to Use:** Multi-disk VMs (e.g., VM with OS disk + data disks)

#### virt-v2v Conversion
**Module:** `orchestrator/virt_v2v_converter.py`

**Option:** `args.v2v_parallel = True` + `args.v2v_concurrency = N`

**Implementation:** ProcessPoolExecutor (avoid GIL for CPU-bound work)

**When to Use:** Batch conversion of multiple VMs

### I/O Optimization

#### VDDK (VMware)
**Benefit:** 3-5x faster than HTTP downloads
**Trade-off:** Requires VDDK installation, complex setup

#### Compression
**Benefit:** Smaller output files, faster network transfers
**Trade-off:** CPU overhead during conversion

**Recommendation:** Use compression for network transfers, skip for local migrations.

---

## Testing Strategy

### Unit Tests
**Location:** `tests/unit/`

**Coverage:**
- Core utilities (`core/`)
- Converters (`converters/`)
- Fixers (`fixers/`)
- Network backends (`fixers/network/`)

**Technology:** pytest, pytest-mock

### Integration Tests
**Location:** `tests/integration/`

**Coverage:**
- End-to-end pipelines
- Multi-stage workflows
- VMware integration (mocked vSphere API)

### Security Tests
**Runs:** GitHub Actions (Bandit, pip-audit)

**Focus:**
- Path traversal prevention (`converters/extractors/raw.py`)
- Symlink attacks
- Command injection
- Credential leakage

---

## Future Architecture Directions

### Plugin System
Allow third-party fixers, transports, and validators without modifying core code.

**Design:**
- Entry point discovery (setuptools entry points)
- Plugin registration API
- Isolated plugin execution (sandboxing)

### Cloud-Native Integration
Direct export to cloud providers without intermediate storage.

**Candidates:**
- AWS (EC2 import, S3 streaming)
- Azure (Managed Disk import, Blob streaming)
- GCP (Compute Engine import, GCS streaming)

**Module:** `converters/cloud/` (new)

### Advanced Recovery
Transactional migrations with automatic rollback on failure.

**Design:**
- Snapshot source VM before migration
- Checkpoint every pipeline stage
- Rollback to last good state on failure

**Module:** Enhanced `core/recovery_manager.py`

### Metrics and Telemetry
Real-time progress tracking and performance metrics.

**Design:**
- Prometheus exporter
- JSON logs for structured analysis
- Performance profiling hooks

**Module:** `core/metrics.py` (new)

---

## Glossary

**libguestfs:** Library for accessing and modifying virtual machine disk images offline.

**VDDK:** VMware Virtual Disk Development Kit - high-performance API for disk access.

**govc:** VMware's official CLI for vSphere operations.

**pyvmomi:** VMware's official Python SDK for vSphere SOAP API.

**VirtIO:** Paravirtualized I/O drivers for KVM (storage, network, RNG, balloon).

**hivex:** Library for reading and writing Windows Registry hive files.

**NBD:** Network Block Device - protocol for accessing block devices over network.

**CBT:** Changed Block Tracking - VMware feature for incremental backups.

**MoRef:** Managed Object Reference - vSphere API identifier for objects.

**NFC:** Network File Copy - VMware protocol for efficient VM export.

---

## Contributing

When proposing architectural changes:

1. **Open an issue first** (discuss design before implementation)
2. **Follow existing patterns** (don't introduce new paradigms without justification)
3. **Respect module boundaries** (don't mix concerns)
4. **Add tests** (unit + integration)
5. **Update documentation** (this file + module docstrings)
6. **Keep classes focused** (under 300 lines when possible)

---

## Summary

hyper2kvm's architecture achieves **reliable, repeatable VM migrations** through:

1. **Deterministic pipeline** (FETCH → FLATTEN → INSPECT → PLAN → FIX → CONVERT → TEST)
2. **Offline-first fixing** (libguestfs, no runtime dependencies)
3. **Strict separation** (control-plane vs data-plane, offline vs live, Windows vs Linux)
4. **Modular components** (Single Responsibility Principle)
5. **Inspection over assumption** (derive facts, never guess)
6. **Idempotent operations** (safe to retry)

**The result:** Migrations that "just work" - boring, predictable, and successful.

**Boring migrations are successful migrations.**
