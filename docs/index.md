# Hyper2KVM Documentation Hub

**Enterprise-Grade VM Migration from Hyper-V, VMware, and Other Hypervisors to KVM/Libvirt**

Welcome to the comprehensive documentation for Hyper2KVM, a production-ready VM migration toolkit designed for seamless hypervisor transitions.

---

## Quick Navigation

### ⚡ Quick Access & Reference
- **[Quick Reference Hub](quick-reference/)** - All quick reference materials
- **[Quick Reference Card](quick-reference/QUICK_REFERENCE.md)** - One-page command reference (printable)
- **[Navigation Map](quick-reference/NAVIGATION_MAP.md)** 🗺️ - Visual guide to finding documentation
- **[Glossary](quick-reference/GLOSSARY.md)** - Complete terminology reference (150+ terms)
- **[FAQ](quick-reference/FAQ.md)** - Frequently asked questions (25+ Q&A)

### 🎯 Decision Support Tools
- **[Decision Support Hub](guides/decision-support/)** - All decision support tools
- **[Migration Decision Tree](guides/decision-support/MIGRATION_DECISION_TREE.md)** 🌳 - Choose the right migration approach
- **[Comparison Matrix](guides/decision-support/COMPARISON_MATRIX.md)** 📊 - Compare methods, formats, and options
- **[Troubleshooting Flowchart](guides/decision-support/TROUBLESHOOTING_FLOWCHART.md)** 🔧 - Diagnose and fix issues

### 📋 Operational Guides
- **[Operations Hub](guides/operations/)** - All operational guides and tools
- **[Migration Checklist](guides/operations/MIGRATION_CHECKLIST.md)** ✅ - Complete migration checklists
- **[Pre-Flight Validation](guides/operations/PRE_FLIGHT_VALIDATION.md)** 🔍 - Verify readiness before migration
- **[Migration Runbook Template](guides/operations/MIGRATION_RUNBOOK_TEMPLATE.md)** 📖 - Customizable migration runbook
- **[Best Practices](guides/operations/BEST_PRACTICES.md)** ⭐ - Proven practices and anti-patterns to avoid
- **[Examples Library](guides/operations/EXAMPLES_LIBRARY.md)** 📚 - 23+ real-world configuration examples
- **[Automation Scripts](guides/operations/AUTOMATION_SCRIPTS.md)** 🤖 - Production-ready automation toolkit
- **[Monitoring Guide](guides/operations/MONITORING_GUIDE.md)** 📈 - Monitor and observe migrated VMs

### 📚 Documentation Resources
- **[Documentation Meta](meta/)** - Documentation about documentation
- **[Contributing to Docs](meta/CONTRIBUTING_DOCS.md)** - Documentation contribution guide
- **[Documentation Changelog](meta/DOCUMENTATION_CHANGELOG.md)** - Track documentation changes

### 🚀 Getting Started
- **[Getting Started Hub](getting-started/)** - Complete getting started guide
- **[Installation Guide](getting-started/01-Installation.md)** - Install Hyper2KVM in 5 minutes
- **[Quick Start Tutorial](getting-started/02-Quick-Start.md)** - Your first migration in 10 minutes
- **[Getting Started Guide](getting-started/03-Getting-Started.md)** - Comprehensive introduction
- **[Architecture Overview](reference/architecture.md)** - Understand how Hyper2KVM works

### 📚 Tutorials
- **[Tutorials Hub](tutorials/)** - Complete tutorials overview
- **[Beginner Tutorial](tutorials/01-beginner-migration.md)** - Step-by-step first migration
- **[Intermediate Tutorial](tutorials/02-intermediate-workflows.md)** - Batch migrations and automation
- **[Advanced Tutorial](tutorials/03-advanced-features.md)** - Live migration, DR testing, database-aware migrations
- **[Enterprise Tutorial](tutorials/04-enterprise-deployment.md)** - Production deployment strategies

### 🍳 Migration Recipes
- **[Recipes Hub](recipes/)** - All recipes overview
- **[Common Scenarios](recipes/01-common-scenarios.md)** - Frequently encountered migration patterns
- **[Migration Cookbook](guides/cookbook.md)** - Quick recipes for common tasks

### 📖 API Reference
- **[VMCraft API](reference/api/vmcraft.md)** - Complete guest filesystem manipulation API (480+ methods)
- **[API Reference](reference/api/API-Reference.md)** - Comprehensive API documentation
- **[Library API](reference/api/library-api.md)** - Python library usage
- **[Quick Reference](reference/api/quick-reference.md)** - Essential API patterns

### 🛠️ User Guides
- **[Guides Hub](guides/)** - Complete guides overview
- **[CLI Reference](guides/cli/reference.md)** - Complete command-line reference
- **[h2kvmctl Guide](guides/cli/h2kvmctl-guide.md)** - Worker job control CLI
- **[YAML Examples](guides/cli/yaml-examples.md)** - Configuration file examples
- **[YAML vs Manifests](guides/yaml-vs-manifests.md)** - Choose the right format
- **[Batch Migration Guide](guides/migration/batch-features.md)** - Migrating multiple VMs
- **[Migration Playbooks](guides/migration/playbooks.md)** - Step-by-step workflows
- **[Migration Quick Reference](guides/migration/quick-reference.md)** - Essential commands
- **[Batch Quick Reference](guides/migration/batch-quick-reference.md)** - Batch operation shortcuts
- **[Conversion Directory Configuration](guides/configuration/conversion-directory.md)** - Configure VMDK conversion temporary directory
- **[Security Best Practices](guides/security-best-practices.md)** - Secure migration workflows
- **[Troubleshooting Guide](guides/troubleshooting.md)** - Diagnose and fix issues
- **[Enhanced Features](guides/enhanced-features.md)** - Advanced capabilities
- **[HyperSDK Quickstart](guides/hypersdk-quickstart.md)** - SDK integration guide

### 🎨 TUI (Terminal UI)
- **[TUI Quickstart](guides/tui/quickstart.md)** - Get started with the dashboard
- **[Dashboard Guide](guides/tui/dashboard.md)** - Interactive terminal interface
- **[Run TUI](guides/tui/run-tui.md)** - Launch and use the TUI

### 🔧 Feature Documentation
- **[Features Hub](features/)** - Complete features overview
- **[VMCraft Complete Guide](features/vmcraft/complete-guide.md)** - Native VM manipulation engine
- **[VMCraft Advanced Features](features/vmcraft/advanced-features.md)** - Expert usage
- **[VMCraft OS Detection](features/vmcraft/os-detection.md)** - Automatic OS identification
- **[VMCraft Windows Support](features/vmcraft/windows-support.md)** - Windows-specific features
- **[VMCraft Augeas Guide](features/vmcraft-augeas-guide.md)** - Configuration file editing
- **[VMCraft LVM Guide](features/vmcraft-lvm-guide.md)** - Logical volume management
- **[VMCraft Partition Management](features/vmcraft-partition-management.md)** - Disk partitioning
- **[VMCraft Performance Guide](features/vmcraft-performance-guide.md)** - Optimization tips
- **[VMDK Inspector](features/vmdk-inspector.md)** - Analyze VMDK files
- **[VMDK Validation](features/vmdk-validation.md)** - Pre-migration checks
- **[XFS UUID Regeneration](features/xfs-uuid-regeneration.md)** - Fix cloned VMware VMs with duplicate UUIDs
- **[fstab Stabilization](features/fstab-stabilization.md)** - Automatic fstab repair and device conversion
- **[Enhanced Chroot](features/enhanced-chroot.md)** - Advanced filesystem access
- **[BusLogic Auto-Fix](features/buslogic-auto-fix.md)** - Legacy controller handling
- **[Configuration Injection](features/configuration-injection.md)** - Dynamic configuration
- **[Systemd Integration](features/systemd-integration.md)** - Service management
- **[Daemon Mode](features/daemon-mode.md)** - Background operation
- **[Daemon Architecture](features/daemon-architecture.md)** - Design and components
- **[Daemon Enhancements](features/daemon-enhancements.md)** - Advanced daemon features
- **[Daemon User Guide](features/daemon-user-guide.md)** - Using the daemon
- **[vSphere Export](features/vsphere-export.md)** - VMware integration
- **[vSphere Design](features/vsphere-design.md)** - vSphere architecture

### 🖥️ OS-Specific Documentation
- **[OS Support Hub](os-support/)** - Complete OS support overview
- **[Cloud-Native Distributions](guides/cloud-native-distros.md)** ⭐ NEW - Photon OS, CoreOS, Flatcar migration guide
- **[Windows Migration](os-support/windows/guide.md)** - Windows VM migration guide
- **[Windows Boot Cycle](os-support/windows/boot-cycle.md)** - Boot process details
- **[Windows Networking](os-support/windows/networking.md)** - Network configuration
- **[Windows Driver Injection](os-support/windows/driver-injection.md)** - VirtIO driver installation
- **[Windows Troubleshooting](os-support/windows/troubleshooting.md)** - Common issues
- **[RHEL/CentOS Migration](os-support/rhel-10.md)** - Red Hat Enterprise Linux
- **[Ubuntu Migration](os-support/ubuntu-2404.md)** - Ubuntu and Debian-based systems
- **[SUSE Migration](os-support/suse.md)** - openSUSE and SLES
- **[Photon OS Migration](os-support/photon-os.md)** - VMware Photon OS detailed guide

### 🚢 Deployment & Operations
- **[Deployment Hub](deployment/)** - Complete deployment overview
- **[Production Deployment Guide](deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)** - Enterprise deployment
- **[Deployment Quickref](deployment/DEPLOYMENT_QUICKREF.md)** - Quick reference card
- **[Deployment Status](deployment/DEPLOYMENT_STATUS.md)** - Current deployment options
- **[Kubernetes on CentOS 8 - Quick Start](deployment/KUBERNETES_CENTOS8_QUICKSTART.md)** ⭐ - Deploy on CentOS 8 in 10 minutes
- **[Kubernetes on CentOS 8 - Full Guide](deployment/kubernetes-centos8-guide.md)** ⭐ - Complete CentOS 8 deployment guide
- **[OpenShift Deployment](deployment/openshift-deployment-guide.md)** - OpenShift Container Platform
- **[OpenShift Quickstart](deployment/openshift/OPENSHIFT_QUICKSTART.md)** - Get started on OpenShift
- **[OpenShift Features](deployment/OPENSHIFT_FEATURES_SUMMARY.md)** - OpenShift integration details
- **[Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md)** - Kubernetes deployment
- **[KubeVirt Integration](deployment/KUBEVIRT_INTEGRATION.md)** - KubeVirt support
- **[Container Deployment](deployment/container-deployment-guide.md)** - Docker/Podman usage
- **[K3d Test Report](deployment/k3d-test-report.md)** - K3d testing results
- **[Phase 4 Deployment](deployment/phase4-deployment.md)** - Phase 4 features
- **[Phase 6 REST API](deployment/PHASE6_REST_API_COMPLETE.md)** - REST API documentation
- **[Production Enhancements](deployment/production-enhancements.md)** - Production features
- **[Worker Protocol Summary](deployment/WORKER_PROTOCOL_SUMMARY.md)** - Worker protocol overview

#### Version Release Notes
- **[v1.2.0 Enhancements](deployment/v1.2.0-enhancements.md)**
- **[v1.3.0 CI/CD & Ops](deployment/v1.3.0-cicd-ops.md)**
- **[v1.4.0 Operator](deployment/v1.4.0-operator.md)**
- **[v1.5.0 Webhooks & Metrics](deployment/v1.5.0-webhooks-metrics.md)**
- **[v1.6.0 Helm Chart](deployment/v1.6.0-helm-chart.md)**
- **[v1.7.0 Helm Repository](deployment/v1.7.0-helm-repository.md)**
- **[v1.8.0 Operator HA](deployment/v1.8.0-operator-ha.md)**
- **[v1.9.0 Advanced Job Scheduling](deployment/v1.9.0-advanced-job-scheduling.md)**
- **[v2.0.0 Comprehensive Features](deployment/v2.0.0-comprehensive-features.md)**
- **[v2.1.0 Release Checklist](deployment/releases/RELEASE_CHECKLIST_v2.1.0.md)**
- **[v2.1.0 Release Complete](deployment/releases/RELEASE_COMPLETE_v2.1.0.md)**
- **[v1.3.0 Release Notes](deployment/releases/RELEASE_NOTES_v1.3.0.md)**

### 🔬 Test Results & Validation
- **[Testing Hub](testing/)** ⭐ - Test plans and procedures
- **[CentOS 8 K8s Test Plan](testing/CENTOS8_TEST_PLAN.md)** ⭐ - Comprehensive test suite for Kubernetes on CentOS 8
- **[Test Results Hub](test-results/)** - Complete test results overview
- **[Test Results](test-results/TEST_RESULTS.md)** - Comprehensive test suite results
- **[CentOS 8 Migration Success](test-results/centos8-migration-success.md)**
- **[CentOS 9 Migration Success](test-results/centos9-migration-success.md)**
- **[CentOS 9 OpenShift Test](test-results/CENTOS9_OPENSHIFT_TEST_RESULTS.md)**
- **[CentOS 9 OpenShift Quick Test](test-results/CENTOS9_OPENSHIFT_QUICK_TEST.md)**
- **[CentOS Test Plan](test-results/CENTOS_TEST_PLAN.md)**
- **[Local Test Report](test-results/LOCAL_TEST_REPORT.md)**
- **[OpenShift Photon Test](test-results/OPENSHIFT_PHOTON_TEST.md)**
- **[OpenShift Test Summary](test-results/OPENSHIFT_TEST_SUMMARY.md)**

### 🔄 Worker Protocol & Job Management
- **[Worker Protocol Hub](worker/)** - Complete worker protocol overview
- **[Worker Protocol Quickstart](worker/QUICKSTART.md)** - Get started quickly
- **[Protocol Specification](worker/PROTOCOL_SPEC.md)** - Complete protocol reference
- **[REST API Documentation](worker/REST_API.md)** - REST API endpoints
- **[Worker Protocol Status](worker/WORKER_PROTOCOL_STATUS.md)** - Implementation status
- **[Worker Protocol Index](worker/INDEX.md)** - Protocol overview

### 👥 Development
- **[Contributing Guide](development/contributing.md)** - Contribute to Hyper2KVM
- **[Architecture Documentation](development/architecture.md)** - Internal architecture
- **[Testing Guide](development/testing-guide.md)** - Running and writing tests
- **[Building from Source](development/building.md)** - Build Hyper2KVM locally
- **[Publishing Guide](development/publishing.md)** - Release process
- **[TUI Implementation](development/tui-implementation.md)** - TUI architecture
- **[TUI Development](development/tui-development.md)** - TUI development guide
- **[Feature Suggestions](development/feature-suggestions.md)** - Suggest new features
- **[Live Migration Implementation Plan](development/live-migration-implementation-plan.md)** - Roadmap
- **[Windows Support Implementation Plan](development/windows-support-implementation-plan.md)** - Windows roadmap

### 📊 Project Information
- **[Project Status](project/PROJECT_STATUS.md)** - Current development status
- **[Priority Features](project/Priority-1-Features.md)** - Roadmap and priorities
- **[Ecosystem](project/ECOSYSTEM.md)** - Related tools and integrations

### 🗺️ Roadmap & Future Features
- **[Roadmap Overview](roadmap/README.md)** - Planned features and enhancements
- **[Advanced Windows Support](roadmap/Advanced-Windows-Support.md)** - Enterprise Windows features (v0.3.0+)

### 📚 Reference Documentation
- **[Reference Hub](reference/)** - Complete reference documentation overview
- **[Dependencies](reference/dependencies.md)** - Required dependencies
- **[Optional Dependencies](reference/optional-dependencies.md)** - Optional packages
- **[Installation Guide](reference/INSTALLATION.md)** - Detailed installation
- **[Quick Reference](reference/quick-reference.md)** - Quick command reference
- **[HyperCtl Integration](reference/HYPERCTL_INTEGRATION.md)** - HyperCtl CLI
- **[Integration Contract](reference/Integration-Contract.md)** - Integration specs
- **[Manifest Workflow](reference/manifest-workflow.md)** - JSON manifest usage
- **[Network Resilience](reference/network-resilience.md)** - Network failure handling
- **[Native GuestFS](reference/native-guestfs.md)** - GuestFS integration
- **[Failure Modes](reference/failure-modes.md)** - Error handling

### 🎤 Presentation Materials
- **[Daemon vs CLI Workflow](presentation/daemon-vs-cli-workflow.md)** - Workflow comparison
- **[Pipeline Architecture](presentation/pipeline-architecture.md)** - Architecture diagrams
- **[Quick Comparison](presentation/quick-comparison.md)** - Feature comparison

---

## Feature Highlights

### 🎯 Production-Ready Features

| Feature | Status | Documentation |
|---------|--------|---------------|
| **VMCraft (480+ APIs)** | ✅ Production | [Complete Guide](features/vmcraft/complete-guide.md) |
| **Local VMDK Migration** | ✅ Production | [Quick Start](getting-started/02-Quick-Start.md) |
| **Remote ESXi Fetch** | ✅ Production | [Migration Playbooks](guides/migration/playbooks.md) |
| **OVA/OVF Extraction** | ✅ Production | [CLI Reference](guides/cli/reference.md) |
| **VHD/AMI Import** | ✅ Production | [CLI Reference](guides/cli/reference.md) |
| **Live Fix (SSH)** | ✅ Production | [Migration Playbooks](guides/migration/playbooks.md) |
| **Batch Processing** | ✅ Production | [Batch Guide](guides/migration/batch-features.md) |
| **Windows Support** | ✅ Production | [Windows Guide](os-support/windows/guide.md) |
| **vSphere Operations** | ✅ Production | [vSphere Export](features/vsphere-export.md) |
| **Kubernetes Operator** | ✅ Production | [Operator Guide](deployment/v1.4.0-operator.md) |
| **OpenShift Support** | ✅ Production | [OpenShift Guide](deployment/openshift-deployment-guide.md) |
| **Worker Protocol** | ✅ Production | [Worker Protocol](worker/PROTOCOL_SPEC.md) |
| **REST API** | ✅ Production | [REST API](worker/REST_API.md) |

### 🏆 Key Capabilities

- ✅ **480+ VMCraft APIs** - Native Python VM manipulation engine
- ✅ **Multiple Input Formats** - VMDK, OVA, OVF, VHD, AMI, Azure VHD
- ✅ **Automated Fixes** - Bootloader (GRUB), fstab stabilization, initramfs regeneration
- ✅ **XFS UUID Regeneration** - Fix cloned VMware VMs with duplicate UUIDs (automatic fstab rebuild)
- ✅ **Multi-OS Support** - Windows (7-12, Server 2012-2025), Linux (RHEL, Ubuntu, SUSE, Photon), BSD
- ✅ **Remote Operations** - SSH-based fetch from ESXi, live-fix without downtime
- ✅ **Windows VirtIO** - Automatic driver injection and registry modification
- ✅ **Batch Processing** - Parallel multi-VM migrations with JSON manifests
- ✅ **Flexible Output** - qcow2, raw, VDI formats with compression levels
- ✅ **Cloud Integration** - Cloud-init injection, vSphere/Azure operations
- ✅ **Kubernetes Native** - Operator, CRDs, webhooks, metrics
- ✅ **Enterprise Features** - HA, monitoring, job scheduling, DAG dependencies

---

## Common Use Cases

### Scenario 1: Local VMDK Migration
**Goal**: Migrate a VMware VMDK to KVM qcow2

```yaml
# migration.yaml
command: local
vmdk: /vms/windows-server.vmdk
output_dir: /vms/converted
to_output: windows-server.qcow2
out_format: qcow2
fstab_mode: stabilize-all
regen_initramfs: true
compress: true
libvirt_test: true
```

```bash
# Install and run
pip install "hyper2kvm[full]"
hyper2kvm --config migration.yaml

# Import to libvirt
virsh define /vms/converted/windows-server.xml
virsh start windows-server
```

**Documentation**: [Beginner Tutorial](tutorials/01-beginner-migration.md) | [Windows Guide](os-support/windows/guide.md)

---

### Scenario 2: Remote ESXi Fetch
**Goal**: Fetch and migrate VM directly from ESXi host

```yaml
# fetch.yaml
command: fetch-and-fix
host: 192.168.1.100
user: root
identity: ~/.ssh/id_rsa
remote: /vmfs/volumes/datastore1/vm/vm.vmdk
output_dir: /vms/migrated
to_output: vm.qcow2
fstab_mode: stabilize-all
regen_initramfs: true
```

```bash
hyper2kvm --config fetch.yaml
```

**Documentation**: [Migration Playbooks](guides/migration/playbooks.md)

---

### Scenario 3: Batch Migration
**Goal**: Migrate multiple VMs in parallel

```yaml
# batch.yaml
command: local
batch_manifest: migrations.json
batch_parallel: 3
batch_continue_on_error: true
output_dir: /vms/batch
```

```json
// migrations.json
{
  "migrations": [
    {"vmdk": "/vms/vm1.vmdk", "to_output": "vm1.qcow2"},
    {"vmdk": "/vms/vm2.vmdk", "to_output": "vm2.qcow2"},
    {"vmdk": "/vms/vm3.vmdk", "to_output": "vm3.qcow2"}
  ]
}
```

```bash
hyper2kvm --config batch.yaml
```

**Documentation**: [Batch Migration Guide](guides/migration/batch-features.md)

---

### Scenario 4: Kubernetes/OpenShift Deployment
**Goal**: Deploy as a Kubernetes operator

```bash
# Install via Helm
helm install hyper2kvm-operator ./helm/hyper2kvm-operator \
  --namespace hyper2kvm-system \
  --create-namespace

# Create migration job
kubectl apply -f migration-job.yaml
```

**Documentation**: [OpenShift Quickstart](deployment/openshift/OPENSHIFT_QUICKSTART.md) | [Kubernetes Integration](deployment/KUBERNETES_INTEGRATION.md)

---

## Quick Reference Cards

### 📋 Reference Materials
- **[Quick Reference Card](QUICK_REFERENCE.md)** - One-page printable command reference
- **[Glossary](GLOSSARY.md)** - Complete terminology and acronyms
- **[FAQ](FAQ.md)** - Frequently asked questions with detailed answers

### Essential Commands

| Command | Description |
|---------|-------------|
| `hyper2kvm --config <yaml>` | Execute migration from YAML config (recommended) |
| `hyper2kvm --cmd local` | Local VMDK/disk migration (alias: `migrate`) |
| `hyper2kvm --cmd fetch-and-fix` | Remote ESXi fetch via SSH |
| `hyper2kvm --cmd ova` | OVA file extraction |
| `hyper2kvm --cmd ovf` | OVF file extraction |
| `hyper2kvm --cmd vhd` | VHD file import |
| `hyper2kvm --cmd ami` | AMI/cloud tarball extraction |
| `hyper2kvm --cmd raw` | Raw disk image/tarball import |
| `hyper2kvm --cmd live-fix` | SSH-based live fixing |
| `hyper2kvm --cmd libvirt-xml` | Parse libvirt XML to manifest |
| `h2kvmctl status` | Check worker job status |
| `h2kvmctl submit <config>` | Submit migration job to worker |
| `hyper2kvm --help` | Show full command reference |

### Common Workflows

**Standard Migration**:
```
1. Create YAML config file
2. Run: hyper2kvm --config migration.yaml
3. Automatic fstab/bootloader fixing
4. Optional: libvirt/QEMU testing
5. Import to libvirt with virsh
```

**Remote Fetch**:
```
1. Configure SSH access to ESXi
2. Create fetch-and-fix YAML config
3. Final switchover (<5s downtime)
4. Validate target
5. Cutover production traffic
```

**Kubernetes Deployment**:
```
1. Install Helm chart or OLM bundle
2. Create MigrationJob CRD
3. Monitor with kubectl/OpenShift console
4. Retrieve converted images
5. Deploy to KubeVirt or export
```

---

## Support and Resources

### Getting Help
- **Documentation**: You're here! Browse by topic above
- **Quick Reference**: [Quick Reference Card](QUICK_REFERENCE.md) - Printable one-page guide
- **Glossary**: [Complete Glossary](GLOSSARY.md) - All terms and acronyms explained
- **FAQ**: [Frequently Asked Questions](FAQ.md) - Common questions answered
- **Troubleshooting**: [Troubleshooting Guide](guides/troubleshooting.md)
- **Recipes**: [Migration Recipes](recipes/01-common-scenarios.md)
- **Issues**: [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)

### Learning Path

**Beginner** (0-2 hours):
1. [Installation](getting-started/01-Installation.md)
2. [Quick Start](getting-started/02-Quick-Start.md)
3. [Beginner Tutorial](tutorials/01-beginner-migration.md)

**Intermediate** (2-8 hours):
1. [Intermediate Workflows](tutorials/02-intermediate-workflows.md)
2. [Batch Migration](guides/migration/batch-features.md)
3. [OS-Specific Guides](os-support/windows/guide.md)

**Advanced** (8+ hours):
1. [Advanced Features](tutorials/03-advanced-features.md)
2. [VMCraft Complete Guide](features/vmcraft/complete-guide.md)
3. [API Reference](reference/api/vmcraft.md)

**Enterprise** (Full deployment):
1. [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
2. [OpenShift Deployment](deployment/openshift-deployment-guide.md)
3. [Security Best Practices](guides/security-best-practices.md)

---

## Version Compatibility

| Hyper2KVM Version | Python | Supported Hypervisors | Kubernetes | Status |
|-------------------|--------|----------------------|------------|--------|
| **2.1.0+** | 3.10+ | VMware, Hyper-V, KVM, AWS, Azure, GCP | 1.24-1.33 | ✅ Current |
| **2.0.0** | 3.10+ | VMware, Hyper-V, KVM, AWS, Azure | 1.24-1.30 | ✅ Stable |
| **1.x** | 3.10+ | VMware, Hyper-V, KVM | N/A | ✅ Supported |
| **0.9.x** | 3.9+ | VMware, Hyper-V, KVM | N/A | 🔄 Legacy |

---

## Documentation Structure

```
docs/
├── index.md (this file)          # Main documentation hub
├── QUICK_REFERENCE.md            # One-page command reference ⭐
├── GLOSSARY.md                   # Complete terminology guide ⭐
├── FAQ.md                        # Frequently asked questions ⭐
├── getting-started/              # Installation and first steps (README ⭐)
├── tutorials/                    # Step-by-step learning (README ⭐)
├── recipes/                      # Quick recipes (README ⭐)
├── guides/                       # Task-oriented guides (README ⭐)
│   ├── cli/                     # Command-line reference
│   ├── migration/               # Migration workflows
│   ├── tui/                     # Terminal UI
│   └── configuration/           # Configuration guides
├── features/                     # Feature documentation (README ⭐)
│   └── vmcraft/                 # VMCraft engine
├── os-support/                   # OS-specific guides (README ⭐)
│   └── windows/                 # Windows migration
├── deployment/                   # Deployment guides (README ⭐)
│   ├── openshift/               # OpenShift specific
│   └── releases/                # Release notes
├── worker/                       # Worker protocol (README ⭐)
├── test-results/                 # Test reports (README ⭐)
├── reference/                    # API and technical reference (README ⭐)
│   └── api/                     # API documentation
├── development/                  # Development guides
├── project/                      # Project information
├── presentation/                 # Presentation materials
├── api/                          # Legacy API docs
└── marketing/                    # Marketing content

⭐ = New or enhanced in v2.1.0
```

---

## Contributing

We welcome contributions! See:
- [Contributing Guide](development/contributing.md)
- [Development Setup](development/building.md)
- [Testing Guide](development/testing-guide.md)

---

## License

Hyper2KVM is licensed under LGPL-3.0-or-later. See LICENSE file for details.

---

**Last Updated**: February 2026
**Documentation Version**: 2.1.0
