# vmdk2kvm

**VMware → KVM/QEMU conversion, repair, and automation toolkit**

`vmdk2kvm` is a production-oriented toolkit for migrating VMware virtual machines
(VMDK / OVA / OVF / ESXi / vCenter) into **KVM/QEMU-bootable images**
**without relying on boot-time luck**.

This project exists to solve the problems that show up *after* a “successful” conversion:

* broken boots
* unstable device naming
* missing or misordered drivers
* corrupted or misleading snapshot chains
* Windows guests that blue-screen on first KVM boot

This repository is intentionally **not** “click migrate and pray”.
It is **convert, repair, validate — and make it repeatable**.

---

## Table of contents

1. Scope and non-goals
2. Design principles
3. Supported inputs and execution modes
4. Pipeline model
5. Control-plane vs data-plane (vSphere, govc, OVF/OVA exports, VDDK, HTTP, SSH)
6. Linux fixes
7. Windows handling
8. Snapshots and flattening
9. Output formats and validation
10. YAML configuration model
11. Multi-VM and batch processing
12. Live-fix mode (SSH)
13. ESXi and vSphere integration
14. virt-v2v integration strategy (experimental)
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
* Applies selected Linux fixes **live over SSH**
* Stabilizes storage and network identifiers across hypervisors
* Injects Windows VirtIO drivers safely (**storage first, always**)
* Flattens VMware snapshot chains deterministically
* Enables repeatable, automatable migrations via mergeable YAML
* Validates results using libvirt / QEMU smoke tests

### What this tool **does not**

* No GUI wizard
* No cloud importer
* No promise of zero-touch Windows fixes
* No attempt to hide complexity

If you want *fast over correct*, this repo will argue with you — politely, and with logs.

---

## 2. Design principles

1. Boot failures are configuration problems, not copy problems
2. Device naming must survive hypervisor changes
3. Snapshot chains lie unless flattened or verified
4. Windows storage must be **BOOT_START** before first KVM boot
5. Every destructive step needs a safe mode
6. Configurations must be replayable
7. Control-plane and data-plane must never be mixed

These rules are enforced structurally, not by convention.

---

## 3. Supported inputs and execution modes

### Offline / local

* Descriptor VMDK
* Monolithic VMDK
* Multi-extent snapshot chains

### Remote

* ESXi over SSH / SCP
* Recursive snapshot fetch

### Archives

* OVA
* OVF + extracted disks

### Live systems

* SSH access to running Linux guests (**live-fix mode**)

### API and CLI based (vSphere)

vCenter / ESXi via:

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

````

Stages are optional.
**Order is not.**

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

## 5. Control-plane vs data-plane

This separation is the **spine** of `vmdk2kvm`.

- **Control-plane** decides *what exists* and *what should happen*.
- **Data-plane** moves *bytes* and produces *artifacts*.

If you mix them, you get “it worked once” migrations.  
If you separate them, you get repeatable ones.

```mermaid
flowchart TB
  subgraph CP["CONTROL PLANE (decide)"]
    GOVC["govc (primary)"]
    PYVM["pyvmomi / pyVim (fallback / deep inspection)"]
    INV["Inventory: VM, disks, firmware, snapshots"]
    PLAN["Plans: snapshot flatten, disk map, export intent"]
    DS["Datastore browsing & artifact resolution"]
    CBT["CBT discovery + changed ranges planning"]

    GOVC --> INV
    GOVC --> DS
    GOVC --> CBT
    PYVM --> INV
    PYVM --> CBT
    INV --> PLAN
    DS --> PLAN
    CBT --> PLAN
  end

  META["plans + metadata (explicit, auditable)"]

  subgraph DP["DATA PLANE (move bytes)"]
    GOVCEXP["govc export.ovf / export.ova"]
    OVFTOOL["ovftool (OVF/OVA export/import)"]
    HTTP["HTTP /folder + Range (artifact + CBT pulls)"]
    VDDK["VDDK (high-throughput disk reads)"]
    SSH["SSH / SCP (locked-down fallback)"]
    V2V["virt-v2v (experimental option)"]
    RESUME["resume + verify + atomic publish"]
  end

  CP --> META --> DP

  GOVCEXP --> RESUME
  OVFTOOL --> RESUME
  HTTP --> RESUME
  VDDK --> RESUME
  SSH --> RESUME
  V2V --> RESUME
````

### The rule

* Control-plane **never** moves bulk data.
* Data-plane **never** makes inventory decisions.

The “bridge” between them is always **explicit plans + metadata** (never implicit guesses).

---

### 5.1 Control-plane responsibilities (govc-first)

`govc` is treated as a **first-class control-plane**, not a convenience wrapper.

Used for:

* VM discovery (name, UUID, MoRef)
* Disk inventory + backing path resolution (datastore paths, controllers, device keys)
* Snapshot tree inspection + flatten planning
* CBT discovery + changed-range planning
* Datastore browsing and folder artifact enumeration
* Safety checks (power state, attached ISOs, device layout)

`pyvmomi` remains available when:

* API-only fields are required
* deeper object-graph traversal is needed
* govc output shapes aren’t sufficient for a specific edge case

Control-plane output is **a plan**:
“export this VM, from this source, using these disks, with these safety edits, into these artifacts.”

---

### 5.2 Data-plane transports (byte-moving only)

The data-plane answers one question:

**How do bytes move safely, reproducibly, and restartably?**

Supported transports:

#### A) Managed vSphere exports (artifact-first)

* **govc `export.ovf` / `export.ova`** — vSphere-managed export flow.

  * Best when you want a clean **OVF/OVA artifact boundary**.
  * `export.ova` = single tarball convenience
  * `export.ovf` = directory layout (OVF + VMDKs) that’s friendlier for large disks and partial re-runs

* **ovftool** — VMware/Broadcom’s OVF/OVA workhorse.

  * Useful when you need ovftool’s compatibility quirks, import/export symmetry, or vendor-specific flags.
  * Treated as data-plane because it primarily **produces artifacts** (OVF/OVA + disks).

#### B) Raw pulls (fast, surgical, resumable)

* **HTTP `/folder` + Range** — deterministic artifact downloads and CBT-driven incremental pulls.
* **VDDK** — high-throughput disk reads when you want speed and you can satisfy VDDK runtime + transport constraints.
* **SSH / SCP** — fallback for constrained environments.

#### C) Guest-aware conversion (experimental option)

* **virt-v2v** — available as an optional integration path, but **not the core philosophy** of this project.

  * Marked experimental because it can be great in the happy path, but it’s not the foundation of the “repair + determinism” model here.

All of these routes feed the same downstream pipeline stages.

---

### 5.3 Export choices: OVF vs OVA (and why we care)

Think of OVF/OVA as **packaging formats**, not “conversion”.

* **OVA**: single file; easy to move/store; harder to resume mid-stream; large reruns hurt.
* **OVF**: directory of artifacts; easier partial retries; friendlier for inspection and selective reuse.

In `vmdk2kvm` terms:

* Choose **OVA** when you want a portable, single-object handoff.
* Choose **OVF** when you want restartability, transparency, and large-disk practicality.

Both are still *data-plane outputs* that then feed **INSPECT → FIX → CONVERT → VALIDATE**.

---

### 5.4 Decision matrix (pragmatic, not dogmatic)

| Goal                                               | Preferred method                |
| -------------------------------------------------- | ------------------------------- |
| Inventory + planning                               | govc                            |
| Export as artifacts (simple)                       | govc export.ovf / export.ova    |
| Export as artifacts (compat-heavy / special flags) | ovftool                         |
| Download specific datastore files                  | HTTP `/folder`                  |
| Fast raw disk extraction                           | VDDK                            |
| No vCenter access / restricted                     | SSH / SCP                       |
| Incremental sync                                   | CBT plan (CP) + HTTP Range (DP) |
| Guest-aware conversion                             | virt-v2v (experimental option)  |

---

### 5.5 Incremental migration (CBT) stays honest

CBT usage is explicit and auditable:

```
CONTROL PLANE:
  govc / pyvmomi → changed block ranges
        ↓
DATA PLANE:
  HTTP Range GET → local patch application
        ↓
VERIFY:
  size / range coverage / optional checksums
```

If CBT lies, the tool **flags it**. It does not pretend.

---

### 5.6 Resume, integrity, and checkpoints

All data-plane operations are built around recovery:

* resumable transfers
* `.part → final` promotion (atomic publish)
* size verification
* optional hashing
* rerun safety (idempotent “skip if complete” semantics)

Same config in. Same result out. No roulette-wheel boots.

---

## 6. Linux fixes

* `/etc/fstab` rewrite (`UUID=` / `PARTUUID=` preferred)
* GRUB root stabilization (BIOS + UEFI)
* initramfs regeneration (distro-aware)
* network cleanup (MAC pinning, VMware artifacts)

---

## 7. Windows handling

Windows is a **first-class citizen**, not an afterthought.

* VirtIO storage injected as **BOOT_START**
* Offline registry and hive edits
* `CriticalDeviceDatabase` fixes
* BCD handling with backups
* No blind binary patching

---

## 8. Snapshots and flattening

* Recursive descriptor resolution
* Parent-chain verification
* Flatten **before** conversion
* Atomic outputs

Snapshot flattening is strongly recommended.

---

## 9. Output formats and validation

**Formats**

* qcow2 (recommended)
* raw
* vdi

**Validation**

* checksums
* libvirt smoke boots
* direct QEMU boots
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
* ESXi + vSphere integration
* virt-v2v coordination (experimental)
* safety mechanisms
* daemon and automation modes
* testing and failure analysis
* explicit non-goals

---

## 20. Documentation index

All detailed documentation, workflows, examples, and references live here:

👉 **[https://github.com/ssahani/vmdk2kvm/tree/main/docs](https://github.com/ssahani/vmdk2kvm/tree/main/docs)**

---

**Convert with intent. Repair with evidence. Boot without luck.**

