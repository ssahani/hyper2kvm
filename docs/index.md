# Hyper2KVM Documentation Hub

**Enterprise-Grade VM Migration from Hyper-V, VMware, and Other Hypervisors to KVM/Libvirt**

Welcome to the comprehensive documentation for Hyper2KVM, a production-ready VM migration toolkit designed for seamless hypervisor transitions.

---

## Quick Navigation

### 🚀 Getting Started
- **[Installation Guide](getting-started/01-Installation.md)** - Install Hyper2KVM in 5 minutes
- **[Quick Start Tutorial](getting-started/00-Quickstart.md)** - Your first migration in 10 minutes
- **[Architecture Overview](reference/architecture.md)** - Understand how Hyper2KVM works

### 📚 Tutorials
- **[Beginner Tutorial](tutorials/01-beginner-migration.md)** - Step-by-step first migration
- **[Intermediate Tutorial](tutorials/02-intermediate-workflows.md)** - Batch migrations and automation
- **[Advanced Tutorial](tutorials/03-advanced-features.md)** - Live migration, DR testing, database-aware migrations
- **[Enterprise Tutorial](tutorials/04-enterprise-deployment.md)** - Production deployment strategies

### 🍳 Migration Recipes
- **[Common Scenarios](recipes/01-common-scenarios.md)** - Frequently encountered migration patterns
- **[OS-Specific Recipes](recipes/02-os-specific.md)** - Windows, Linux, BSD migration examples
- **[Application Recipes](recipes/03-application-specific.md)** - Database servers, web servers, domain controllers
- **[Troubleshooting Recipes](recipes/04-troubleshooting.md)** - Common issues and solutions

### 📖 API Reference
- **[VMCraft API](api/vmcraft-api.md)** - Complete guest filesystem manipulation API
- **[Validation API](api/validation-api.md)** - Post-migration validation framework
- **[Rollback API](api/rollback-api.md)** - Migration rollback and recovery
- **[CLI API](api/cli-api.md)** - Command-line interface and configuration
- **[Backup Integration API](api/backup-api.md)** - Backup restore and DR testing
- **[Live Migration API](api/live-migration-api.md)** - Live migration with minimal downtime

### 🛠️ User Guides
- **[CLI Reference](guides/cli/reference.md)** - Complete command-line reference
- **[Batch Migration Guide](guides/migration/batch-features.md)** - Migrating multiple VMs
- **[Security Best Practices](guides/security-best-practices.md)** - Secure migration workflows
- **[Troubleshooting Guide](guides/troubleshooting.md)** - Diagnose and fix issues
- **[TUI Dashboard](guides/tui/dashboard.md)** - Terminal user interface guide

### 🔧 Feature Documentation
- **[Live Migration](features/live-migration.md)** - Minimal-downtime migration
- **[Database-Aware Migration](features/database-aware.md)** - Automated database preparation
- **[Compliance & Audit](features/compliance-audit.md)** - Compliance reporting and audit trails
- **[Container Extraction](features/container-extraction.md)** - VM-to-Kubernetes migration
- **[Backup Integration](features/backup-integration.md)** - DR testing and backup restore
- **[Migration Validation](features/migration-validation.md)** - Automated validation framework
- **[Rollback Framework](features/rollback-framework.md)** - Recovery from failed migrations

### 🖥️ OS-Specific Documentation
- **[Windows Migration](os-support/windows/guide.md)** - Windows VM migration guide
- **[RHEL/CentOS Migration](os-support/rhel-10.md)** - Red Hat Enterprise Linux
- **[Ubuntu Migration](os-support/ubuntu-2404.md)** - Ubuntu and Debian-based systems
- **[SUSE Migration](os-support/suse.md)** - openSUSE and SLES
- **[Photon OS Migration](os-support/photon-os.md)** - VMware Photon OS

### 👥 Development
- **[Contributing Guide](development/contributing.md)** - Contribute to Hyper2KVM
- **[Architecture Documentation](development/architecture.md)** - Internal architecture
- **[Testing Guide](development/testing-guide.md)** - Running and writing tests
- **[Building from Source](development/building.md)** - Build Hyper2KVM locally

### 📊 Project Information
- **[Project Status](project/PROJECT_STATUS.md)** - Current development status
- **[Priority Features](project/Priority-1-Features.md)** - Roadmap and priorities
- **[Ecosystem](project/ECOSYSTEM.md)** - Related tools and integrations

---

## Feature Highlights

### 🎯 Production-Ready Features

| Feature | Status | Documentation |
|---------|--------|---------------|
| **VMCraft (Guest OS Manipulation)** | ✅ Production | [Complete Guide](features/vmcraft/complete-guide.md) |
| **Live Migration** | ✅ Production | [Live Migration Guide](features/live-migration.md) |
| **Batch Migration** | ✅ Production | [Batch Guide](guides/migration/batch-features.md) |
| **Database-Aware Migration** | ✅ Production | [Database Guide](features/database-aware.md) |
| **Compliance & Audit** | ✅ Production | [Compliance Guide](features/compliance-audit.md) |
| **Container Extraction** | ✅ Production | [Container Guide](features/container-extraction.md) |
| **Backup Integration** | ✅ Production | [Backup Guide](features/backup-integration.md) |
| **Migration Validation** | ✅ Production | [Validation Guide](features/migration-validation.md) |
| **Rollback Framework** | ✅ Production | [Rollback Guide](features/rollback-framework.md) |
| **CLI Enhancement** | ✅ Production | [CLI Guide](api/cli-api.md) |

### 🏆 Key Capabilities

- ✅ **480+ VMCraft APIs** - Comprehensive VM manipulation capabilities
- ✅ **Live Migration** - <5s downtime for suitable workloads with HyperSDK
- ✅ **Automated Fixes** - Bootloader, network, fstab, drivers automatically configured
- ✅ **Multi-OS Support** - Windows, Linux (RHEL, Ubuntu, SUSE, Photon), BSD
- ✅ **Enterprise Features** - Batch migration, compliance reporting, audit trails
- ✅ **Database Support** - PostgreSQL, MySQL/MariaDB, MongoDB, Redis automatic preparation
- ✅ **Container Extraction** - VM → Kubernetes migration with auto-generated manifests
- ✅ **Backup Restore** - Veeam, Proxmox PBS, generic backup integration
- ✅ **Validation Framework** - Automated health checks, service/network/database validation
- ✅ **Rollback Capability** - Full and partial rollback with snapshot management

---

## Common Use Cases

### Scenario 1: Basic VM Migration
**Goal**: Migrate a single Windows Server from Hyper-V to KVM

```bash
# Install Hyper2KVM
pip install hyper2kvm

# Migrate VM
hyper2kvm migrate /vms/windows-server.vhdx \
    --target /vms/converted/windows-server.qcow2 \
    --fix-all \
    --validate

# Import to libvirt
virsh define windows-server.xml
virsh start windows-server
```

**Documentation**: [Beginner Tutorial](tutorials/01-beginner-migration.md) | [Windows Guide](os-support/windows/guide.md)

---

### Scenario 2: Batch Migration with Validation
**Goal**: Migrate 50 Linux VMs with automated validation

```bash
# Create batch config
hyper2kvm batch create --config batch-config.yaml

# Execute batch migration
hyper2kvm batch execute batch-config.yaml \
    --parallel 5 \
    --validate-all \
    --compliance-report

# Generate summary report
hyper2kvm batch report --format markdown
```

**Documentation**: [Batch Migration Guide](guides/migration/batch-features.md) | [Validation Guide](features/migration-validation.md)

---

### Scenario 3: Live Migration with Minimal Downtime
**Goal**: Migrate production database server with <5s downtime

```bash
# Analyze migration feasibility
hyper2kvm live analyze /vms/prod-db.vmdk

# Execute live migration
hyper2kvm live migrate /vms/prod-db.vmdk \
    --target /vms/prod-db.qcow2 \
    --provider vmware \
    --max-downtime 5

# Validate migration
hyper2kvm validate /vms/prod-db.qcow2 \
    --check-databases \
    --check-services \
    --check-network
```

**Documentation**: [Live Migration Tutorial](tutorials/03-advanced-features.md#live-migration) | [Live Migration API](api/live-migration-api.md)

---

### Scenario 4: DR Testing from Backups
**Goal**: Test disaster recovery by restoring from Veeam backups

```bash
# Restore from Veeam backup
hyper2kvm backup restore \
    --source veeam:///backups/veeam-repo \
    --vm prod-app-01 \
    --target /vms/dr-test/prod-app-01.qcow2

# Run DR validation
hyper2kvm validate /vms/dr-test/prod-app-01.qcow2 \
    --full-check \
    --report /reports/dr-test.json

# Cleanup test environment
virsh destroy prod-app-01-test
```

**Documentation**: [Backup Integration Guide](features/backup-integration.md) | [Validation Guide](features/migration-validation.md)

---

### Scenario 5: VM to Kubernetes Migration
**Goal**: Extract containers from VM and deploy to Kubernetes

```bash
# Extract containers from VM
hyper2kvm container extract /vms/docker-host.qcow2 \
    --output-dir /k8s/manifests \
    --generate-manifests

# Review generated manifests
ls /k8s/manifests/
# deployments/
# services/
# configmaps/
# secrets/

# Deploy to Kubernetes
kubectl apply -f /k8s/manifests/
```

**Documentation**: [Container Extraction Guide](features/container-extraction.md) | [Container Recipes](recipes/03-application-specific.md#containerized-workloads)

---

## Quick Reference Cards

### Essential Commands

| Command | Description |
|---------|-------------|
| `hyper2kvm migrate <source>` | Basic VM migration |
| `hyper2kvm batch execute <config>` | Batch migration |
| `hyper2kvm live migrate <source>` | Live migration with minimal downtime |
| `hyper2kvm validate <disk>` | Post-migration validation |
| `hyper2kvm backup restore` | Restore from backup |
| `hyper2kvm container extract` | Extract containers from VM |
| `hyper2kvm rollback <snapshot-id>` | Rollback failed migration |

### Common Workflows

**Standard Migration**:
```
1. Analyze source VM
2. Create pre-migration snapshot
3. Execute migration with fixes
4. Run validation checks
5. Import to libvirt
```

**Live Migration**:
```
1. Analyze feasibility
2. Pre-copy memory/disk
3. Final switchover (<5s downtime)
4. Validate target
5. Cutover production traffic
```

**DR Testing**:
```
1. Restore from backup
2. Convert to KVM format
3. Apply migration fixes
4. Run DR validation
5. Generate test report
```

---

## Support and Resources

### Getting Help
- **Documentation**: You're here! Browse by topic above
- **Troubleshooting**: [Troubleshooting Guide](guides/troubleshooting.md)
- **Recipes**: [Migration Recipes](recipes/01-common-scenarios.md)
- **Issues**: [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)

### Learning Path

**Beginner** (0-2 hours):
1. [Installation](getting-started/01-Installation.md)
2. [Quick Start](getting-started/00-Quickstart.md)
3. [Beginner Tutorial](tutorials/01-beginner-migration.md)

**Intermediate** (2-8 hours):
1. [Intermediate Workflows](tutorials/02-intermediate-workflows.md)
2. [Batch Migration](guides/migration/batch-features.md)
3. [OS-Specific Guides](os-support/windows/guide.md)

**Advanced** (8+ hours):
1. [Advanced Features](tutorials/03-advanced-features.md)
2. [Live Migration](features/live-migration.md)
3. [API Reference](api/vmcraft-api.md)

**Enterprise** (Full deployment):
1. [Enterprise Tutorial](tutorials/04-enterprise-deployment.md)
2. [Security Best Practices](guides/security-best-practices.md)
3. [Compliance & Audit](features/compliance-audit.md)

---

## Version Compatibility

| Hyper2KVM Version | Python | Supported Hypervisors | Status |
|-------------------|--------|----------------------|--------|
| **1.0.0+** | 3.10+ | Hyper-V, VMware, KVM, AWS, Azure, GCP | ✅ Current |
| **0.9.x** | 3.9+ | Hyper-V, VMware, KVM | 🔄 Legacy |
| **0.8.x** | 3.8+ | Hyper-V, VMware | ⚠️ Deprecated |

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

**Last Updated**: January 2026
**Documentation Version**: 1.0.0
