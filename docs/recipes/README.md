# Migration Recipes

Practical, copy-paste-ready recipes for common VM migration scenarios. Each recipe includes prerequisites, step-by-step instructions, validation, and troubleshooting.

---

## Recipe Collections

### 📋 Common Scenarios
**[View Recipes](01-common-scenarios.md)**

10 frequently encountered migration scenarios with complete solutions.

**Recipes Included**:
1. **Single Windows Server Migration** - Hyper-V to KVM (Beginner, 15-30 min)
2. **Linux Web Server Migration** - VMware to KVM with LAMP stack (Beginner, 10-20 min)
3. **Database Server Migration** - PostgreSQL/MySQL with minimal downtime (Intermediate, 20-40 min)
4. **Batch Migration of 50+ VMs** - Datacenter migration (Intermediate, 4-8 hours)
5. **Live Migration** - Production app with <5s downtime (Advanced, 30-60 min)
6. **DR Testing from Veeam** - Restore and validate from backup (Intermediate, 20-40 min)
7. **VM to Kubernetes** - Extract containers and deploy to K8s (Advanced, 45-90 min)
8. **Domain Controller Migration** - Active Directory DC (Advanced, 30-60 min)
9. **Legacy Application Server** - Old CentOS 6 with legacy apps (Intermediate, 30-50 min)
10. **HA Cluster Migration** - 2-node Pacemaker/Corosync (Advanced, 2-4 hours)

---

### 🖥️ OS-Specific Recipes
**[View Recipes](02-os-specific.md)**

Operating system specific migration patterns and solutions.

**Categories**:
- **Windows** (Server 2012-2022, Desktop 7-11)
  - Domain-joined servers
  - SQL Server instances
  - IIS web servers
  - File servers
- **Linux** (RHEL, Ubuntu, SUSE, Debian)
  - systemd vs SysVinit
  - Network configuration differences
  - Package manager specifics
  - Bootloader configurations
- **BSD** (FreeBSD, OpenBSD)
  - Boot loader configuration
  - Network interface naming
  - Package management

---

### 🎯 Application-Specific Recipes
**[View Recipes](03-application-specific.md)**

Migrations for specific applications and workloads.

**Applications**:
- **Databases**
  - PostgreSQL clusters
  - MySQL/MariaDB replication
  - MongoDB replica sets
  - Redis clusters
- **Web Servers**
  - Apache with mod_php
  - Nginx reverse proxy
  - Tomcat application servers
  - Node.js applications
- **Enterprise Applications**
  - SAP systems
  - Oracle Database
  - Microsoft Exchange
  - SharePoint
- **Development Tools**
  - GitLab
  - Jenkins
  - Docker registries
  - Artifactory

---

### 🔧 Troubleshooting Recipes
**[View Recipes](04-troubleshooting.md)**

Common issues and step-by-step solutions.

**Issue Categories**:
- **Boot Failures**
  - "No boot device found"
  - GRUB rescue prompt
  - Windows "Inaccessible Boot Device"
  - Kernel panic
- **Network Issues**
  - No network connectivity
  - Interface naming changes
  - DHCP not working
  - Static IP lost
- **Storage Problems**
  - VirtIO driver missing
  - Disk not detected
  - fstab errors (emergency mode)
  - LVM not found
- **Performance Issues**
  - Slow disk I/O
  - High CPU usage
  - Memory pressure
  - Network throughput degradation

---

## Quick Recipe Finder

### By Hypervisor Source

| Source | Recipes |
|--------|---------|
| **VMware vSphere/ESXi** | Linux Web Server, Batch Migration, Live Migration |
| **Hyper-V** | Windows Server, Domain Controller, SQL Server |
| **KVM** | Database Server, HA Cluster |
| **AWS EC2** | Live Migration (EC2 to KVM) |
| **Proxmox** | Container Extraction, Backup Restore |

### By Operating System

| OS | Recipes |
|----|---------|
| **Windows Server** | Single Server, Domain Controller, SQL Server, IIS |
| **Ubuntu/Debian** | Web Server, Docker Host, Container Extraction |
| **RHEL/CentOS** | Database Server, HA Cluster, Legacy Apps |
| **SUSE/openSUSE** | Enterprise Apps, SAP Systems |

### By Complexity

| Level | Recipes |
|-------|---------|
| **Beginner** | Single Windows Server, Linux Web Server |
| **Intermediate** | Database Server, Batch Migration, DR Testing, Legacy Apps |
| **Advanced** | Live Migration, Container Extraction, Domain Controller, HA Cluster |

### By Duration

| Duration | Recipes |
|----------|---------|
| **<30 min** | Single Server, Linux Web Server |
| **30-60 min** | Database Server, DR Testing, Domain Controller, Legacy Apps |
| **1-2 hours** | Container Extraction |
| **2+ hours** | Batch Migration, HA Cluster |

---

## Recipe Format

Each recipe follows this structure:

### 1. **Scenario**
Clear description of what you're migrating

### 2. **Prerequisites**
- Required access and permissions
- Source VM requirements
- Storage requirements
- Tools needed

### 3. **Steps**
Step-by-step commands with explanations

### 4. **Validation**
How to verify successful migration

### 5. **Troubleshooting**
Common issues and solutions

---

## Using Recipes

### Copy-Paste Ready

All commands in recipes are designed to be copy-paste ready:

```bash
# Example: Single command to migrate Windows Server
hyper2kvm migrate /vms/source/windows-server.vhdx \
    --target /vms/migrated/windows-server.qcow2 \
    --format qcow2 \
    --fix-all \
    --verbose
```

### Customization

Replace placeholder values with your environment:

```bash
# Template
SOURCE=/path/to/source.vmdk
TARGET=/path/to/target.qcow2

# Your values
SOURCE=/vmware/prod/app-server.vmdk
TARGET=/kvm/migrated/app-server.qcow2
```

### Automation

Convert recipes to scripts:

```bash
#!/bin/bash
# migrate-web-server.sh

SOURCE=$1
TARGET=$2

if [ -z "$SOURCE" ] || [ -z "$TARGET" ]; then
    echo "Usage: $0 <source> <target>"
    exit 1
fi

# Recipe steps
hyper2kvm migrate $SOURCE \
    --target $TARGET \
    --fix-all \
    --validate

# Post-migration
virsh define ${TARGET%.qcow2}.xml
virsh start $(basename ${TARGET%.qcow2})
```

---

## Recipe Workflow

### Standard Migration Recipe

```
1. Prepare
   └─ Backup source VM
   └─ Create snapshot
   └─ Document current state

2. Migrate
   └─ Execute migration command
   └─ Apply automatic fixes
   └─ Convert disk format

3. Validate
   └─ Run validation checks
   └─ Verify boot configuration
   └─ Test network connectivity

4. Import
   └─ Define in libvirt
   └─ Start VM
   └─ Verify services

5. Verify
   └─ Application testing
   └─ Performance checks
   └─ User acceptance
```

### Rollback-Safe Recipe

```
1. Create Snapshot
   └─ Pre-migration snapshot
   └─ Compute checksum

2. Migrate with State Tracking
   └─ Track migration checkpoints
   └─ Mark reversible states

3. If Failure
   └─ Execute rollback
   └─ Verify rollback success
   └─ Review failure logs

4. If Success
   └─ Validate migration
   └─ Clean up snapshots
   └─ Update documentation
```

---

## Contributing Recipes

Help the community by sharing your migration experiences!

### How to Contribute

1. **Document Your Migration**
   - Clear scenario description
   - Complete command sequences
   - Validation steps
   - Troubleshooting tips

2. **Test Your Recipe**
   - Verify commands work
   - Test on clean environment
   - Validate all steps

3. **Submit PR**
   - Add to appropriate recipe collection
   - Follow existing format
   - Include expected output

**See**: [Contributing Guide](../development/contributing.md)

---

## Recipe Support

- **Questions?** [GitHub Discussions](https://github.com/ssahani/hyper2kvm/discussions)
- **Issues?** [GitHub Issues](https://github.com/ssahani/hyper2kvm/issues)
- **Suggestions?** [Feature Requests](https://github.com/ssahani/hyper2kvm/issues/new?labels=enhancement)

---

## Related Documentation

- **[Tutorials](../tutorials/)**: Learning path for beginners to experts
- **[API Reference](../api/)**: Programmatic migration workflows
- **[Guides](../guides/)**: In-depth feature documentation
- **[Troubleshooting](../guides/troubleshooting.md)**: Comprehensive issue resolution

---

**Start with**: [Common Scenarios →](01-common-scenarios.md)

**Last Updated**: January 2026
