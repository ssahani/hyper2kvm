# Hyper2KVM Tutorials

Step-by-step tutorials for mastering VM migration with Hyper2KVM, from beginner to enterprise deployment.

---

## Learning Path

### 🌱 Beginner (0-2 hours)
**Start here if you're new to Hyper2KVM**

- **[01. Your First VM Migration](01-beginner-migration.md)** (30-45 min)
  - Install Hyper2KVM and dependencies
  - Migrate a Windows Server from Hyper-V to KVM
  - Understand automatic fixes (bootloader, network, storage)
  - Validate the migrated VM
  - Import to libvirt and verify functionality

### 🌿 Intermediate (2-8 hours)
**Continue here after completing beginner tutorial**

- **[02. Batch Migration & Automation](02-intermediate-workflows.md)** (1-2 hours)
  - Execute batch migrations of 10+ VMs
  - Create reusable YAML configurations
  - Automate workflows with cron/CI/CD
  - Monitor migration progress in real-time
  - Generate compliance reports

### 🌳 Advanced (8+ hours)
**Master advanced features and complex scenarios**

- **[03. Advanced Features](03-advanced-features.md)** (2-3 hours)
  - Live migration with <5s downtime using HyperSDK
  - Database-aware migrations (PostgreSQL, MySQL)
  - Container extraction (VM → Kubernetes)
  - Backup integration and DR testing
  - Rollback framework for failure recovery

### 🏢 Enterprise (Full deployment knowledge)
**Production deployment and best practices**

- **[04. Enterprise Deployment](04-enterprise-deployment.md)** (4+ hours)
  - Production architecture design
  - Security best practices
  - Compliance and audit requirements
  - High-availability considerations
  - Monitoring and alerting setup
  - Disaster recovery planning

---

## Quick Reference

### Tutorial Comparison

| Tutorial | Duration | Difficulty | VMs Migrated | Features Covered |
|----------|----------|------------|--------------|------------------|
| **Beginner** | 30-45 min | ⭐ Easy | 1 | Basic migration, validation, import |
| **Intermediate** | 1-2 hours | ⭐⭐ Moderate | 10+ | Batch, automation, monitoring |
| **Advanced** | 2-3 hours | ⭐⭐⭐ Hard | Varies | Live, database, containers, DR |
| **Enterprise** | 4+ hours | ⭐⭐⭐⭐ Expert | Production | Architecture, security, compliance |

---

## Prerequisites by Level

### Beginner
- ✅ Basic command-line knowledge
- ✅ Access to a VM disk file (.vhdx, .vmdk, .qcow2)
- ✅ Linux system with sudo access
- ✅ 10GB free disk space

### Intermediate
- ✅ Completed beginner tutorial
- ✅ Familiarity with YAML
- ✅ Access to multiple VMs
- ✅ 100GB+ free disk space

### Advanced
- ✅ Completed intermediate tutorial
- ✅ Understanding of virtualization concepts
- ✅ Network configuration knowledge
- ✅ HyperSDK installed (for live migration)

### Enterprise
- ✅ All advanced prerequisites
- ✅ Production environment access
- ✅ Security policy knowledge
- ✅ Team coordination capabilities

---

## What You'll Build

### By End of Beginner Tutorial
- Migrate 1 VM from Hyper-V/VMware to KVM
- Validate migration success
- Boot VM in KVM environment
- Understand automatic fixes

### By End of Intermediate Tutorial
- Batch migrate 10+ VMs efficiently
- Automate migrations with scheduling
- Monitor progress in real-time
- Generate compliance reports
- Handle failures gracefully

### By End of Advanced Tutorial
- Live migrate production VMs (<5s downtime)
- Migrate database servers safely
- Extract containers from VMs
- Test DR scenarios from backups
- Rollback failed migrations

### By End of Enterprise Tutorial
- Design production migration architecture
- Implement security controls
- Set up monitoring and alerting
- Plan disaster recovery
- Meet compliance requirements

---

## Additional Resources

### Hands-On Practice
- **[Migration Recipes](../recipes/01-common-scenarios.md)**: 10+ real-world scenarios
- **[OS-Specific Guides](../os-support/windows/guide.md)**: Windows, Linux, BSD
- **[Troubleshooting Guide](../guides/troubleshooting.md)**: Common issues and solutions

### API Documentation
- **[VMCraft API](../api/vmcraft-api.md)**: Guest filesystem manipulation
- **[Validation API](../api/validation-api.md)**: Post-migration validation
- **[Rollback API](../api/rollback-api.md)**: Rollback and recovery

### Feature Guides
- **[Live Migration](../features/live-migration.md)**: Minimal-downtime migration
- **[Compliance & Audit](../features/compliance-audit.md)**: Reporting and audit trails
- **[Batch Migration](../guides/migration/batch-features.md)**: Multi-VM migration

---

## Support

- **Questions?** Check the [Troubleshooting Guide](../guides/troubleshooting.md)
- **Issues?** See [Migration Recipes](../recipes/01-common-scenarios.md)
- **Bugs?** Report on [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)

---

**Start Learning**: [Beginner Tutorial →](01-beginner-migration.md)
