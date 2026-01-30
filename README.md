# vmdk2kvm

**VMware → KVM/QEMU conversion, repair, and automation toolkit**

`vmdk2kvm` is a production-oriented toolkit for migrating VMware virtual machines
(VMDK / OVA / OVF / ESXi / vCenter)
into **KVM/QEMU-bootable images**
**without relying on boot-time luck**.

It exists to solve the problems that appear *after* a “successful” conversion:

* broken boots
* unstable device naming
* missing or misordered drivers
* corrupted snapshot chains
* Windows guests that blue-screen on first KVM boot

This repository is intentionally **not** “click migrate and pray”.

---

## Table of contents

1. Scope and non-goals
2. Design principles
3. Supported inputs and execution modes
4. Pipeline model
5. Control-plane vs data-plane (vSphere, govc, VDDK, HTTP, SSH)
6. Linux fixes
7. Windows handling
8. Snapshots and flattening
9. Output formats and validation
10. YAML configuration model
11. Multi-VM and batch processing
12. Live-fix mode (SSH)
13. ESXi and vSphere integration (govc + APIs)
14. virt-v2v integration strategy
15. Safety mechanisms
16. Daemon mode and automation
17. Testing and verification
18. Failure modes and troubleshooting
19. When not to use this tool
20. Documentation index

---

## 1. Scope and non-goals

### What this tool **does**

* Converts VMware disks into KVM-usable formats
* Repairs Linux and Windows guests **offline**
* Applies some Linux fixes **live over SSH**
* Stabilizes storage and network identifiers
* Injects Windows VirtIO drivers safely (storage first, always)
* Flattens VMware snapshot chains deterministically
* Enables repeatable, automatable migrations via mergeable YAML
* Validates results using libvirt / qemu smoke tests

### What this tool **does not**

* Not a GUI wizard
* Not a cloud importer
* Not a thin wrapper around virt-v2v
* Not a promise of zero-touch Windows fixes
* Not a complexity hider

If you want *fast over correct*, this repo will argue with you (politely, with logs).

---

## 2. Design principles

1. **Boot failures are configuration problems, not copy problems**
2. **Device naming must survive hypervisor changes**
3. **Snapshot chains lie unless flattened**
4. **Windows storage must be BOOT_START before first KVM boot**
5. **Every destructive step needs a safe mode**
6. **Configurations must be replayable**
7. **Control-plane and data-plane must not be mixed**

These rules are enforced structurally, not by convention.

---

## 3. Supported inputs and execution modes

### Offline / local

* Descriptor VMDK
* Monolithic VMDK
* Multi-extent snapshot chains

### Remote

* ESXi over SSH/SCP
* Recursive snapshot fetch

### Archives

* OVA
* OVF + extracted disks

### Live systems

* SSH access to running Linux guests (**live-fix mode**)

### API and CLI based (vSphere)

* vCenter / ESXi via:

  * **govc** (primary CLI control-plane)
  * pyvmomi / pyVim (API fallback and deep inspection)

Used for:

* inventory
* snapshot planning
* CBT discovery
* datastore browsing
* artifact resolution

---

## 4. Pipeline model

All execution modes map to a **single internal pipeline**:

```
FETCH → FLATTEN → INSPECT → FIX → CONVERT → VALIDATE
```

Stages are optional.
**Order is not.**

| Stage    | Meaning                     |
| -------- | --------------------------- |
| FETCH    | Obtain disks and metadata   |
| FLATTEN  | Collapse snapshot chains    |
| INSPECT  | Detect OS, layout, firmware |
| FIX      | Apply deterministic repairs |
| CONVERT  | Produce qcow2/raw/etc       |
| VALIDATE | Boot-test and verify        |

The pipeline is explicit and inspectable.

---

## 5. Control-plane vs data-plane

This separation is the *spine* of the project.

### High-level view

```
            ┌────────────────────────────┐
            │        CONTROL PLANE        │
            │  (what exists, what to do)  │
            │                              │
            │  govc                       │
            │  pyvmomi / pyVim            │
            │  inventory + snapshots      │
            │  CBT planning               │
            │  datastore inspection       │
            └─────────────┬──────────────┘
                          │
                          │ plans, ranges, metadata
                          │
            ┌─────────────▼──────────────┐
            │         DATA PLANE          │
            │    (move bytes reliably)    │
            │                              │
            │  virt-v2v                   │
            │  VDDK reads                 │
            │  HTTP /folder downloads     │
            │  SSH/SCP                    │
            │  resume + verify            │
            └────────────────────────────┘
```

* Control-plane **never** moves large data
* Data-plane **never** makes inventory decisions

---

### 5.1 Control-plane responsibilities (govc-first)

`govc` is treated as a **first-class control-plane tool**, not a convenience hack.

Used for:

* VM discovery (name, UUID, MoRef)
* Disk and backing path resolution
* Snapshot tree inspection
* CBT enablement and range queries
* Datastore browsing
* Folder-level artifact enumeration

Why govc?

* Stable CLI semantics
* Excellent coverage of vSphere features
* Predictable output (JSON-friendly)
* Easier to reason about than opaque SDK state

pyvmomi remains available when:

* API-only fields are required
* govc coverage is insufficient
* deeper object graph traversal is needed

---

### 5.2 Data-plane transports

Data-plane answers one question only:

**How do bytes move safely?**

Supported transports:

#### virt-v2v

Semantic conversion engine.

Use when:

* you want qcow2/raw output
* you want guest-aware conversion
* you want fewer moving parts

#### HTTP `/folder` (via vCenter)

Use when:

* you want download-only
* you want datastore artifacts
* you want ranged reads (CBT)

#### VDDK

Use when:

* throughput matters
* VDDK is permitted
* large disks are involved

#### SSH/SCP

Use when:

* no API access exists
* networks are locked down
* only ESXi shell access is available

---

### 5.3 Decision matrix

| Goal                  | Recommended      |
| --------------------- | ---------------- |
| Convert and boot VM   | virt-v2v         |
| Inventory + planning  | govc             |
| Download VM artifacts | HTTP `/folder`   |
| Fast disk extraction  | VDDK             |
| No vCenter access     | SSH/SCP          |
| Incremental sync      | CBT + HTTP Range |

---

### 5.4 Incremental migration (CBT)

CBT is explicit and audited.

```
CONTROL PLANE:
  govc → query changed block ranges
        ↓
DATA PLANE:
  HTTP Range GETs
        ↓
LOCAL DISK PATCH
```

Used for:

* warm migrations
* large disks
* controlled cutover windows

If CBT lies, the tool tells you.
It does not pretend.

---

### 5.5 Resume, integrity, and checkpoints

Every data-plane operation supports failure recovery:

* resumable transfers
* `.part → final` promotion
* size verification
* optional SHA256
* rerun safety

Same config in, same result out.

---

## 6. Linux fixes

* fstab rewrite (`UUID=` / `PARTUUID=` preferred)
* GRUB root stabilization (BIOS + UEFI)
* initramfs regeneration (distro-aware)
* network cleanup (MAC pinning, VMware artifacts)

---

## 7. Windows handling

Windows is a **first-class citizen**, not an afterthought.

* VirtIO storage injected as BOOT_START
* registry edits via offline hives
* CriticalDeviceDatabase fixes
* BCD handling with backups
* no blind binary patching

---

## 8. Snapshots and flattening

* recursive descriptor resolution
* parent chain verification
* flatten **before** conversion
* atomic outputs

Snapshot flattening is strongly recommended.

---

## 9. Output formats and validation

Formats:

* qcow2 (recommended)
* raw
* vdi

Validation:

* checksums
* libvirt smoke boots
* qemu direct boots
* BIOS and UEFI
* headless supported

---

## 10. YAML configuration model

YAML is treated as **code**:

* mergeable
* reviewable
* rerunnable

```bash
--config base.yaml --config vm.yaml --config overrides.yaml
```

---

## 11–19

* batch processing
* live-fix mode
* ESXi + vSphere via govc
* virt-v2v integration
* safety mechanisms
* daemon / automation
* testing and failure analysis
* explicit non-goals

---

---

