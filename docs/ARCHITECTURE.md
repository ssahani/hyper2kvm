# ARCHITECTURE.md — vmdk2kvm Internal Architecture 🚀🔧💥
## Purpose 🎯✨
This document dives deep into the **module-level architecture**, execution flow, and unbreakable invariants powering `vmdk2kvm`. 💥🔍  
It's crafted for contributors, reviewers, and power users who crave insight into:  
* **Where the magic (and logic) lives** 🧙‍♂️🛠️  
* **How data and state flow like a well-oiled machine** ⚙️💨🔄  
* **Why these boundaries are ironclad defenses against chaos** 🛡️🚫⚠️  

The repo is laser-focused on fixing those sneaky "successful" conversions that still flop at boot, network, or stability post-migration. 😵💥🔥  
This isn't random complexity—it's a fortress of containment for reliable, repeatable results. 🏰🔄✅  

---
## The Canonical Pipeline 🛤️🚆⚡
At the heart of everything is this unbreakable flow:  
**FETCH 📥 → FLATTEN 📸 → INSPECT 🔍 → PLAN 📝 → FIX 🛠️ → CONVERT 🔄 → VALIDATE / TEST ✅**  

Not every command hits every stage, but the **order is sacred—never messed with**. 🚫🔀😈  
Skip stages if needed, but permutation? Heresy. 🔥🚫  

### What Each Stage Means (In This Repo's Universe) 🌌🪐  
* **FETCH 📥**  
  Grab source disks *and* metadata from anywhere—vSphere APIs, ESXi via SSH, or local files. Think of it as the hunter-gatherer phase. 🏹📂💾  

* **FLATTEN 📸**  
  Tame wild snapshot chains, delta extents, and quirky formats into clean, single-image beasts. No more tangled messes! 🧹🔗📏  

* **INSPECT 🔍**  
  Offline deep-dive using libguestfs to uncover: OS family (Linux? Windows?), firmware (BIOS or UEFI?), mount layouts, bootloader setups, and key files. Ground truth, no guesses. 🕵️‍♂️🖥️🔬  

* **PLAN 📝**  
  Strategize *what needs doing* before lifting a finger. Home to inventory scans, dry-runs, and blueprinting. Plan smart, execute once. 🧠📊🗺️  

* **FIX 🛠️**  
  Drop deterministic patches to ensure bootability and sanity. Offline by default—because who needs runtime drama? 🔧🚑🩹  

* **CONVERT 🔄**  
  Handle the heavy lifting: image format swaps and resizing via qemu-img wizardry. Transform VMDK into qcow2 glory. ⚡💿🔥  

* **VALIDATE / TEST ✅**  
  Ruthless verification with boot smoke tests (libvirt or raw qemu). Does it boot? Network? Survive? Prove it. 🔥🧪✅  

This pipeline isn't just a suggestion—it's the law of the land for every migration. 📜💪🔒  

---
## Actual Repo Layout (Authoritative Blueprint) 🗺️📂🔥
This mirrors the real-deal project structure—your single source of truth:  
```
vmdk2kvm/ 🌳🚀
├── main.py 🚀🔥 (Entry point for all the action—kickstarts the magic)
├── __init__.py 🔌⚡ (Package initializer, wiring everything up)
├── cli/ 🛠️📜 (Command-line interface goodies for user-friendly interactions)
│ ├── argument_parser.py 📜🔍 (Parses your commands like a pro, handling args with precision)
│ └── help_texts.py ❓💡 (Friendly help and usage docs—because clarity rocks)
├── config/ 📄🗂️ (Configuration mastery for customizable migrations)
│ ├── config_loader.py 🔄📥 (Loads and merges YAML configs seamlessly)
│ └── systemd_template.py 🛡️🛠️ (Templates for systemd injections into guests)
├── core/ 💥🧰 (Foundational utilities and safeguards— the backbone)
│ ├── cred.py 🔑🔒 (Credential handling—secure and smart, no leaks)
│ ├── exceptions.py ⚠️🚨 (Custom errors for graceful failures and debugging)
│ ├── logger.py 📝📊 (Logging that's verbose yet elegant, with timestamps and levels)
│ ├── recovery_manager.py 🔄🛡️ (Resume from crashes like a boss, checkpointing progress)
│ ├── sanity_checker.py ✅🔬 (Pre-flight checks to avoid disasters and ensure compatibility)
│ ├── utils.py 🧰🔧 (Handy helpers for everything—string utils, file ops, and more)
│ └── validation_suite.py 🧪✅ (Suite of tests for ironclad validation across stages)
├── orchestrator/ 🎻🧠 (The conductor of the symphony, tying it all together)
│ └── orchestrator.py 🧠⚙️ (Runs the pipeline, coordinates chaos, and enforces invariants)
├── converters/ 🔄⚡ (Transformation engines for disk handling)
│ ├── fetch.py 📥🌐 (Fetches disks from afar, unifying remote/local sources)
│ ├── flatten.py 📸📏 (Squashes snapshots flat, resolving chains deterministically)
│ ├── qemu_converter.py ⚡💿 (QEMU image magic—conversions to qcow2/raw/etc.)
│ ├── disk_resizer.py 📏🔄 (Resizes disks dynamically, handling expansions/shrinks)
│ ├── ovf_extractor.py 📦🔓 (Unpacks OVF/OVA archives, extracting disks and metadata)
│ ├── ami_extractor.py ☁️🛠️ (Handles AWS AMI exports—experimental edge for cloud migrations)
│ └── vhd_extractor.py 💿🔧 (VHD format wrangling for Azure/Hyper-V crossovers)
├── fixers/ 🛠️🔥 (Repair wizards for guest OS stability)
│ ├── base_fixer.py 🧱🛡️ (Base class for all fixers, defining common interfaces)
│ ├── offline_fixer.py 🔧🛑 (Offline mutations via libguestfs—no runtime needed)
│ ├── live_fixer.py 🔴🌐 (Live SSH fixes for running guests, with safety checks)
│ ├── fstab_rewriter.py 📄🔄 (Rewrites /etc/fstab for stable UUID/PARTUUID mounts)
│ ├── grub_fixer.py 🔄🥾 (GRUB bootloader savior, handling BIOS/UEFI modes)
│ ├── bootloader_fixer.py 🥾🛠️ (General bootloader repairs, distro-agnostic)
│ ├── network_fixer.py 🌐🧹 (Cleans up NICs, MAC pinning, and VMware artifacts)
│ ├── windows_fixer.py 🪟🔪 (Windows-specific VirtIO injections, registry edits)
│ ├── cloud_init_injector.py ☁️📥 (Injects cloud-init for cloud readiness and automation)
│ ├── offline_vmware_tools_remover.py 🧹🚫 (Purges VMware tools offline, no traces left)
│ ├── live_grub_fixer.py 🔴🔧 (Live GRUB tweaks via SSH for immediate fixes)
│ └── report_writer.py 📊📝 (Generates migration reports, logs, and summaries)
├── modes/ 📈🔍 (Specialized workflows for non-destructive ops)
│ ├── inventory_mode.py 🔍📋 (Read-only inventory scans of VMs and disks)
│ └── plan_mode.py 📝🗺️ (Dry-run planning mode for what-if simulations)
├── testers/ 🧪🔥 (Verification powerhouses to prove success)
│ ├── qemu_tester.py ⚡🚀 (Direct QEMU boot tests, headless or interactive)
│ └── libvirt_tester.py 🌐✅ (Libvirt domain validations, XML generation)
├── ssh/ 🔑🌐 (Secure remote access for ESXi and live fixes)
│ ├── ssh_client.py 🌐🔒 (SSH connections and commands, with paramiko under the hood)
│ └── ssh_config.py 📄🛡️ (SSH config management, key handling, timeouts)
└── vmware/ 🌐🛠️ (VMware ecosystem integration—control and data planes)
    ├── vsphere_mode.py 🛡️⚙️ (vSphere-specific modes for inventory/export)
    ├── vsphere_command.py 🛠️📜 (vSphere CLI wrappers, govc integration)
    ├── vmware_client.py 🔌🔍 (pyvmomi client for deep dives, API calls)
    ├── vddk_client.py ⚡💨 (VDDK for high-speed data pulls, throughput optimized)
    └── vmdk_parser.py 📄🔬 (VMDK descriptor parsing, chain resolution)
```  
This layout keeps concerns separated, making it scalable and maintainer-friendly. No spaghetti code here! 🍝🚫💪  

---
## Control-Plane vs Data-Plane (VMware Paths) ⚙️🌐🔥  
VMware integration is split into two unbreakable realms—because mixing them leads to migration madness. 😵‍💫🚫  
This divide ensures correctness, auditability, and no "it worked once" surprises. 🎲❌🔄  

---
### Control-Plane: Inventory, Intent, Planning 🧠📝🔍  
Answers: *What exists? Where? What’s the plan?*  
Never touches bulk data—keeps it lean and mean. ⚡🛡️  

#### Control-Plane Implementations  
**Primary (Go-To Hero): govc 🛠️✨🔥**  
* Powers:  
  * VM hunts (by name, UUID, MoRef) 🔍🖥️🕵️  
  * Snapshot tree dissections 📸🌳🔗  
  * Disk path resolutions (backings, controllers, device keys) 📂💿📏  
  * Firmware sniffing (BIOS/UEFI) 🥾🔬  
  * CBT setup and range queries 🔄📏⚙️  
  * Datastore/folder explorations 📂🗺️🗂️  
* Why it rocks: Stable CLI, scriptable outputs (JSON/structured), minimal leaks, real-world vSphere coverage. 💪📜  
* Integration: Wrapped in `vmware/vsphere_command.py` for seamless invocation, error handling, and output parsing.  

**Secondary / Fallback: pyvmomi / pyVim 🔍🕵️🛠️**  
* Kicks in for: govc gaps, deep graph traversals (e.g., full object hierarchies), API-exclusive treasures like advanced property queries or custom vCenter extensions. 🌌🔮  
* Housed in: `vmware/vmware_client.py`—uses pyvmomi for SOAP API connections, pyVim for task management and session handling.  
* Details: Establishes secure connections via `SmartConnect`, queries Managed Objects (MoRefs), and traverses properties with `RetrievePropertiesEx`. Handles authentication, SSL verification, and retry logic for flaky vCenter responses. ⚙️🔒  

**CLI Glue Layer**  
* `vmware/vsphere_mode.py` & `vmware/vsphere_command.py`  
  Translate user commands (e.g., `vsphere inventory`, `vsphere plan`) into **pure plans**—no data hauling. 📜🚫💾  
  Supports credential injection from env vars or YAML configs.  

---
### Data-Plane: Moving Bytes Safely 📦💨⚡  
Answers: *How to shuttle bytes without fibbing or failing?*  
No inventory smarts here—just reliable transport. 🚚🛡️  

#### Data-Plane Implementations  
* **ovftool 🔧📦🚀** (VMware's Official OVF/OVA Workhorse)  
  * Integrated as an external CLI call for OVF/OVA exports/imports.  
  * Used when: Compatibility quirks needed (e.g., vendor-specific flags, import symmetry), or for artifact-first exports beyond govc's scope. ⚙️🔄  
  * Details: Invoked via subprocess in `converters/ovf_extractor.py`, with flags for compression, network mapping, and progress tracking. Supports resumable exports and validation of OVF manifests. Treated purely as byte-mover—no planning logic. 📦💾  
  * Why included: Provides symmetry for OVF/OVA handling, especially in hybrid environments or when govc export.ovf/ova isn't sufficient.  

* **VDDK ⚡🚀💥**  
  * `vmware/vddk_client.py`  
  * Blazing-fast disk reads for performance hogs, leveraging VMware's Virtual Disk Development Kit.  
  * Details: Uses libvddk for direct disk access over NBD or SAN transports, with multi-threaded I/O for throughput. Handles CBT for incremental pulls.  

* **HTTP `/folder` 🌐📡🔄**  
  * Datastore downloads with range support for CBT increments. Resumable and stateless—perfect for partial retries.  

* **SSH / SCP 🔑🔒🛡️**  
  * `ssh/` modules  
  * Fallback for API-blackout zones—simple, secure, universal. Supports key-based auth and file transfers.  

* **Local Copy 📁🔧**  
  * Routed via `converters/fetch.py`—unifies all paths, with checksum verification.  

Post-fetch, VMware vibes vanish. Disks become neutral territory. 🌍❌💿  

---
## Where the Pipeline Actually Runs 🎻🧠⚙️  
### The Orchestrator is the Boss 💥🧠  
`orchestrator/orchestrator.py` calls the shots:  
* Enforces sacred ordering 🛡️🔒  
* Manages resumes/recoveries 🔄🛡️  
* Triggers sanity checks ✅🔬  
* Dispatches converters, fixers, testers 🛠️🧪🔄  
* Compiles epic reports 📊📝  

It dictates **when**—the modules handle **how**. Perfect harmony. 🎶💪  

---
### Fix Orchestration: Offline vs Live is a Firewall 🧱🔥🚫  
* **Offline (Default Fortress) 🔧🛑🛡️**  
  `fixers/offline_fixer.py`  
  Leverages libguestfs—no boot reqs, no services, pure disk ops. Mounts images read-write for safe mutations.  

* **Live (Opt-In Adventure) 🔴🌐⚡**  
  `fixers/live_fixer.py`  
  Needs a running Linux guest via SSH—keeps runtime assumptions quarantined. Executes scripts remotely with sudo support.  

This wall stops leaks: Offline stays pure, live stays contained. 🚫💧🔥  

---
## Key Architectural Invariants (Laws of Physics) 📜💪🔒  
These are non-negotiable—break them, and migrations crumble. ⚠️💥  

### 1) Offline is the Default Truth 🔧🛑🛡️  
Unless explicitly live, fixers assume:  
* No systemd vibes 🚫⚙️  
* No efivars or kernel tricks 🚫🔮  
* Disk images + libguestfs only 📂🔍  
Runtime needs? Banished to live mode.  

### 2) Inspection Beats Assumptions 🔍🏆🚫  
libguestfs rules supreme: Derive OS, mounts, firmware, bootloaders—never guess. 🤔🚫🔬  

### 3) `/dev/disk/by-path` is Radioactive ☢️🚫⚠️  
Any code near fstab, boot cmdlines, initramfs, crypttab **must nuke by-path** and swap in UUID/PARTUUID/labels from real disks. Stability first! 🔄🛡️  

### 4) Windows Logic is Hermetically Sealed 🪟🔒🚫  
Contained solely in `fixers/windows_fixer.py`. Linux fixers detect and dip— no touching! Cross-pollution? Forbidden. 🚫🧪  

### 5) Best-Effort, Idempotent-Ish Behavior 🔄✅💪  
* Tolerate re-runs like a champ  
* Contain failures, report loud 📢🚨  
* Only must-haves halt the train  

Repair tool mindset: Iterative, not explosive. 💣❌🔄  

---
## Module Responsibilities (Ownership Map) 🗺️🛡️🔥  
### `cli/` 🛠️📜  
Owns: CLI facade, help docs, YAML showcases. Logic? Not here.  

### `config/` 📄🗂️  
Owns: Merging magic, defaults, guest-injection templates.  

### `core/` 💥🧰  
Owns: Logs, errors, subprocesses, sanity gates, recovery, validations.  

### `vmware/` & `ssh/` 🌐🔑  
Own: Remotes, inventories, disk grabs. Guest tweaks? Nope.  

### `converters/` 🔄⚡  
Own: QEMU ops, flattening, conversions, container extractions (including ovftool calls).  

### `fixers/` 🛠️🔥  
Own: Mutations, offline/live split, reports.  

### `modes/` 📈🔍  
Own: Read-only modes, inventories, plans.  

### `testers/` 🧪🔥  
Own: Boot tests, harnesses, validations.  

---
## Why This Architecture Holds Up 🏗️💪🔥  
Because failures become predictable and dull:  
* No flaky disk IDs 😩🚫  
* No busted root= 🔄🛠️  
* No missing drivers 🛠️⚠️  
* No stale NICs 🌐🧹  
* No VMware ghosts 👻🚫  
* Surgical Windows fixes 🪟🔪  

You get:  
* **Determinism** (inspection rules) 🔍🛡️  
* **Repeatability** (plans + recovery) 🔄✅  
* **Containment** (isolated realms) 🧱🔒  
* **Composability** (mix-and-match stages) 🔗⚙️  

Migrations turn boring—and boring wins. 🏆😎🚀  

---
## Adding a New Feature (Design Rule) ➕🛠️🔥  
Slot it into **one** bucket:  
1. **Fetch Path** 📥 → `vmware/`, `ssh/`, or `converters/fetch.py`  
2. **Flatten / Convert** 🔄 → `converters/` (e.g., new extractors like ovftool enhancements)  
3. **Inspect / Plan** 🔍📝 → `modes/` + helpers (e.g., pyvmomi deep queries)  
4. **Fix** 🛠️ → `fixers/` (offline priority)  
5. **Validate / Test** ✅ → `testers/` + `core/validation_suite.py`  

Doesn't fit? Orchestrator coordination only—no bloat. 🚫🧱  

---
### Final Note 📝✨🔥  
`govc` delivers a **pristine, auditable control-plane**. 🛠️🔍📜  
`ovftool` powers robust OVF/OVA data-plane exports. 🔧📦⚡  
`pyvmomi / pyVim` unlocks deep API insights for fallbacks. 🔍🛡️  
libguestfs supplies **unassailable ground truth**. 🕵️‍♂️🔬  
The rest? Smart plumbing, strict discipline, and zero guesses.  
This is how migrations become routine—and routine is victory. 🎉🚀💥
