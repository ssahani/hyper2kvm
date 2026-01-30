# hyper2kvm: Pipeline Architecture

## Core Concept

**hyper2kvm is a multi-stage pipeline** that transforms VMs from any hypervisor to KVM-ready format.

Think of it like an assembly line: each stage does one job, passes the result to the next stage.

---

## The Pipeline Flow

```mermaid
graph LR
    FETCH[1. FETCH<br/>Get Disks] --> FLATTEN[2. FLATTEN<br/>Collapse Chains]
    FLATTEN --> INSPECT[3. INSPECT<br/>Detect OS]
    INSPECT --> PLAN[4. PLAN<br/>Strategy]
    PLAN --> FIX[5. FIX<br/>Patch Guest]
    FIX --> CONVERT[6. CONVERT<br/>Format Change]
    CONVERT --> VALIDATE[7. VALIDATE<br/>Boot Test]

    classDef stage fill:#4CAF50,stroke:#2E7D32,color:#fff
    class FETCH,FLATTEN,INSPECT,PLAN,FIX,CONVERT,VALIDATE stage
```

### Pipeline Rules

✓ **Sequential** - Stages run in strict order
✓ **Deterministic** - Same input → same output
✓ **Isolated** - Each stage has clear inputs/outputs
✓ **Recoverable** - Can resume from checkpoint

---

## Stage Details

### Stage 1: FETCH
**Purpose:** Acquire source VM disks

**Sources:**
- vSphere (VDDK, HTTP, SSH)
- Azure (Managed Disk download)
- Hyper-V (VHD/VHDX files)
- Local filesystem

**Output:** Raw disk files on local storage

```mermaid
graph LR
    S1[vSphere] --> FETCH[FETCH Stage]
    S2[Azure] --> FETCH
    S3[Local Files] --> FETCH
    FETCH --> O[/tmp/disk.vmdk]

    classDef source fill:#FFF3E0,stroke:#F57C00
    classDef stage fill:#4CAF50,stroke:#2E7D32,color:#fff
    classDef output fill:#E3F2FD,stroke:#1565C0

    class S1,S2,S3 source
    class FETCH stage
    class O output
```

---

### Stage 2: FLATTEN
**Purpose:** Collapse snapshot chains into single files

**Problem Solved:**
- VMware snapshots = multiple delta files
- Can't convert fragmented chains directly

**Process:**
- Parse VMDK descriptors
- Read extent chain: base → delta1 → delta2
- Merge into single flat image

**Output:** Single flat disk file

```mermaid
graph TD
    I1[base.vmdk] --> FLATTEN[FLATTEN Stage]
    I2[delta1.vmdk] --> FLATTEN
    I3[delta2.vmdk] --> FLATTEN
    FLATTEN --> O[flat-disk.vmdk<br/>Single File]

    classDef input fill:#FFEBEE,stroke:#C62828
    classDef stage fill:#4CAF50,stroke:#2E7D32,color:#fff
    classDef output fill:#E3F2FD,stroke:#1565C0

    class I1,I2,I3 input
    class FLATTEN stage
    class O output
```

---

### Stage 3: INSPECT
**Purpose:** Detect guest OS and configuration

**Technology:** libguestfs (offline disk mounting)

**Detects:**
- OS type (Linux distro, Windows version)
- Firmware (BIOS vs UEFI)
- Bootloader (GRUB, GRUB2, systemd-boot)
- Init system (systemd, sysv)
- Partition layout
- Filesystem types
- Network manager

**Output:** GuestIdentity object

```python
GuestIdentity(
    os_type="linux",
    os_distro="rhel",
    os_version="9.3",
    firmware="uefi",
    bootloader="grub2",
    init_system="systemd",
    network_manager="NetworkManager"
)
```

---

### Stage 4: PLAN
**Purpose:** Decide what fixes are needed

**Planning Logic:**
```
IF Windows:
    - Need VirtIO driver injection
    - Need registry modifications
ELSE IF Linux:
    - Check fstab for /dev/disk/by-path
    - Check initramfs for virtio modules
    - Check network config for MAC pinning
```

**Output:** Fix plan (list of required operations)

---

### Stage 5: FIX
**Purpose:** Apply offline fixes to ensure boot on KVM

**The Critical Stage** - This is what makes hyper2kvm unique!

#### Fix Subsystems

```mermaid
graph TD
    FIX[FIX Stage] --> FS[Filesystem Fixer]
    FIX --> BL[Bootloader Fixer]
    FIX --> NET[Network Fixer]
    FIX --> WIN[Windows Fixer]

    FS --> F1[Fix /etc/fstab<br/>by-path → UUID]
    BL --> F2[Rebuild initramfs<br/>Add virtio drivers]
    BL --> F3[Regenerate GRUB<br/>Remove HW refs]
    NET --> F4[Clean MAC pinning<br/>Remove VMware artifacts]
    WIN --> F5[Inject VirtIO drivers<br/>Registry changes]

    classDef stage fill:#4CAF50,stroke:#2E7D32,color:#fff
    classDef subsystem fill:#9C27B0,stroke:#6A1B9A,color:#fff
    classDef fix fill:#FF9800,stroke:#E65100,color:#fff

    class FIX stage
    class FS,BL,NET,WIN subsystem
    class F1,F2,F3,F4,F5 fix
```

#### Offline vs Live Fixing

| Mode | When | How |
|------|------|-----|
| **Offline** | Default | Mount disk with libguestfs, modify files directly |
| **Live** | Opt-in | SSH to running guest, execute commands |

**Offline is safer** → No runtime dependencies, works on broken VMs

---

### Stage 6: CONVERT
**Purpose:** Transform disk format

**Technology:** qemu-img

**Conversions:**
- VMDK → qcow2 (default)
- VHD → qcow2
- Raw → qcow2
- Any → raw

**Options:**
- Compression (smaller files)
- Sparse allocation (thin provisioning)

**Output:** KVM-native disk format

```bash
# Example conversion
qemu-img convert \
  -f vmdk \              # Input format
  -O qcow2 \             # Output format
  -c \                   # Compress
  input.vmdk \
  output.qcow2
```

---

### Stage 7: VALIDATE
**Purpose:** Verify VM boots on KVM

**Tests:**
- Boot test (QEMU or libvirt)
- Console output analysis
- Kernel panic detection
- Network interface presence

**Output:** Pass/Fail + boot log

---

## Pipeline Execution Modes

### Serial Execution (Default)
```
Disk1: FETCH → FLATTEN → INSPECT → FIX → CONVERT → VALIDATE
Disk2: FETCH → FLATTEN → INSPECT → FIX → CONVERT → VALIDATE
```

### Parallel Execution (Multi-disk VMs)
```
Disk1: FETCH → FLATTEN → INSPECT → FIX → CONVERT
                                                   ↓
Disk2: FETCH → FLATTEN → INSPECT → FIX → CONVERT → VALIDATE
```

---

## Data Flow Example

### Input: VMware RHEL 9 VM

```mermaid
graph TD
    START[rhel9.vmdk<br/>VMware Format] --> FETCH

    FETCH[FETCH<br/>Download from vSphere] --> F1[/tmp/rhel9.vmdk]

    F1 --> FLATTEN[FLATTEN<br/>Has 2 snapshots] --> F2[/tmp/rhel9-flat.vmdk]

    F2 --> INSPECT[INSPECT<br/>Mount with libguestfs] --> F3[GuestIdentity:<br/>RHEL 9.3, UEFI, systemd]

    F3 --> PLAN[PLAN<br/>Determine fixes] --> F4[Fix Plan:<br/>- fstab UUID<br/>- initramfs virtio<br/>- GRUB regen]

    F4 --> FIX[FIX<br/>Apply offline patches] --> F5[Fixed disk:<br/>KVM-ready configs]

    F5 --> CONVERT[CONVERT<br/>qemu-img] --> F6[/kvm/rhel9.qcow2<br/>Compressed]

    F6 --> VALIDATE[VALIDATE<br/>Boot test] --> END[✓ Boots successfully<br/>Network up]

    classDef stage fill:#4CAF50,stroke:#2E7D32,color:#fff
    classDef data fill:#E3F2FD,stroke:#1565C0

    class FETCH,FLATTEN,INSPECT,PLAN,FIX,CONVERT,VALIDATE stage
    class START,F1,F2,F3,F4,F5,F6,END data
```

---

## Orchestrator Architecture

The **Orchestrator** coordinates the pipeline:

```mermaid
graph TD
    USER[User Command] --> ORCH[Orchestrator]

    ORCH --> DISC[Disk Discovery<br/>Find source disks]
    DISC --> PROC[Disk Processor<br/>Run pipeline stages]

    PROC --> P1[Worker 1:<br/>FETCH→FLATTEN→INSPECT]
    PROC --> P2[Worker 2:<br/>FIX→CONVERT]

    P1 --> RES[Results Collector]
    P2 --> RES

    RES --> ORCH
    ORCH --> OUT[Output:<br/>- Converted disks<br/>- Domain XML<br/>- Report]

    classDef orchestrator fill:#9C27B0,stroke:#6A1B9A,color:#fff
    classDef worker fill:#FF9800,stroke:#E65100,color:#fff
    classDef result fill:#4CAF50,stroke:#2E7D32,color:#fff

    class ORCH,DISC,RES orchestrator
    class PROC,P1,P2 worker
    class OUT result
```

### Orchestrator Components

**1. DiskDiscovery**
- Finds input disks
- Classifies types (VMDK, VHD, OVA)

**2. DiskProcessor**
- Executes pipeline stages
- Handles errors per-stage
- Parallel or serial execution

**3. VsphereExporter** (optional)
- vSphere-specific export logic
- VDDK/HTTP transport

---

## Recovery & Checkpointing

Pipeline supports resume from failure:

```mermaid
graph LR
    S1[Stage 1<br/>✓ Complete] --> S2[Stage 2<br/>✓ Complete]
    S2 --> S3[Stage 3<br/>✗ Failed]
    S3 --> CHK[Checkpoint Saved]

    CHK --> RESUME[Resume from<br/>Stage 3]
    RESUME --> S3B[Stage 3<br/>Retry]
    S3B --> S4[Stage 4<br/>Continue]

    classDef done fill:#4CAF50,stroke:#2E7D32,color:#fff
    classDef failed fill:#F44336,stroke:#C62828,color:#fff
    classDef checkpoint fill:#FF9800,stroke:#E65100,color:#fff

    class S1,S2 done
    class S3 failed
    class CHK,RESUME checkpoint
```

**Checkpoint file example:**
```json
{
  "completed_stages": ["fetch", "flatten"],
  "current_stage": "inspect",
  "resume_from": "/tmp/rhel9-flat.vmdk",
  "timestamp": "2024-01-29T10:30:00Z"
}
```

---

## CLI vs Daemon Pipeline Execution

### CLI Mode: Single Pipeline Run
```
User Command → Pipeline Execution → Exit
```

### Daemon Mode: Continuous Pipeline Loop
```
Watch Queue → Detect File → Run Pipeline → Archive → Loop
```

### CLI Mode Flow
```mermaid
graph LR
    C1[CLI: Command] --> C2[Pipeline] --> C3[Exit]

    classDef cli fill:#2196F3,stroke:#1565C0,color:#fff
    class C1,C2,C3 cli
```

### Daemon Mode Flow
```mermaid
graph LR
    D1[Daemon: Watch] --> D2[Detect]
    D2 --> D3[Pipeline]
    D3 --> D4[Archive]
    D4 --> D1

    classDef daemon fill:#4CAF50,stroke:#2E7D32,color:#fff
    class D1,D2,D3,D4 daemon
```

---

## Key Architectural Principles

### 1. **Stage Isolation**
Each stage has clear responsibilities:
```
FETCH:   Sources → Local disks
FLATTEN: Multi-file → Single file
INSPECT: Disk → Metadata
FIX:     Broken configs → KVM configs
CONVERT: Any format → KVM format
```

### 2. **No Stage Skipping**
Pipeline order is sacred:
```
✓ ALLOWED:   Skip entire pipeline stage (if not needed)
✗ FORBIDDEN: Reorder stages (FIX before INSPECT)
```

### 3. **Deterministic Behavior**
Same inputs → Same outputs:
```
rhel9.vmdk → Always produces identical qcow2
```

### 4. **Fail-Fast Per Stage**
Each stage validates:
```
INSPECT: Can't detect OS? → FAIL (don't proceed to FIX)
FIX:     Can't mount disk? → FAIL (don't proceed to CONVERT)
```

---

## Why Pipeline Architecture?

### ✓ **Modularity**
Add new sources = new FETCH implementation
Add new OS = new FIX rules
Add new format = new CONVERT handler

### ✓ **Testability**
Test each stage independently:
```python
def test_flatten_stage():
    input = "multi-extent.vmdk"
    output = flatten(input)
    assert is_single_file(output)
```

### ✓ **Debuggability**
Pipeline failures are easy to locate:
```
FETCH:   ✓ Success
FLATTEN: ✓ Success
INSPECT: ✓ Success
FIX:     ✗ Failed at fstab rewrite
```

### ✓ **Extensibility**
New pipeline stage = plug it in:
```
FETCH → FLATTEN → INSPECT → [NEW STAGE] → FIX → CONVERT
```

---

## Summary

**hyper2kvm = 7-stage pipeline that makes any VM boot on KVM**

```
Source VM → FETCH → FLATTEN → INSPECT → PLAN → FIX → CONVERT → VALIDATE → KVM-ready VM
```

**Each stage does one thing well.**
**Stages run in strict order.**
**Pipeline is deterministic and recoverable.**

**Result:** Reliable, repeatable VM migrations.
