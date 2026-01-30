# hyper2kvm Documentation

Complete documentation for hyper2kvm - VMware to KVM migration toolkit.

## Documentation Structure

### 📚 [Getting Started](getting-started/)
New to hyper2kvm? Start here!
- Installation guide
- Quick start tutorial
- Basic concepts

### 📖 [Guides](guides/)
Step-by-step guides and tutorials
- **[Migration](guides/migration/)** - Migration guides and playbooks
- **[CLI](guides/cli/)** - Command-line interface
- **[TUI](guides/tui/)** - Terminal user interface
- [Cookbook](guides/cookbook.md) - Common recipes
- [Troubleshooting](guides/troubleshooting.md)
- [Security Best Practices](guides/security-best-practices.md)

### 📋 [Reference](reference/)
Technical reference documentation
- **[API](reference/api/)** - API documentation
- [Architecture](reference/architecture.md)
- [Dependencies](reference/dependencies.md)
- [Manifest Workflow](reference/manifest-workflow.md)
- [Failure Modes](reference/failure-modes.md)

### 💻 [OS Support](os-support/)
Operating system-specific documentation
- **Linux**: RHEL, Ubuntu, SUSE, Photon OS
- **Windows**: Complete Windows migration guide

### ⚡ [Features](features/)
Feature-specific documentation
- **[VMCraft](features/vmcraft/)** - VM manipulation library
- Daemon Mode
- Systemd Integration
- vSphere Export
- Enhanced Chroot

### 🔧 [Development](development/)
Developer documentation
- [Contributing Guide](development/contributing.md)
- [Architecture](development/architecture.md)
- [Building](development/building.md)
- [Testing Guide](development/testing-guide.md)

### 📊 [Project](project/)
Project status and planning
- [Ecosystem](project/ECOSYSTEM.md)
- [Project Status](project/PROJECT_STATUS.md)
- [Priority Features](project/Priority-1-Features.md)

## Quick Links

| Task | Documentation |
|------|---------------|
| Install hyper2kvm | [Installation Guide](getting-started/01-Installation.md) |
| First migration | [Quick Start](getting-started/02-Quick-Start.md) |
| CLI usage | [CLI Reference](guides/cli/reference.md) |
| Migration recipes | [Cookbook](guides/cookbook.md) |
| API reference | [Library API](reference/api/library-api.md) |
| Troubleshooting | [Troubleshooting Guide](guides/troubleshooting.md) |

## Documentation by Use Case

### First-Time Users
1. [Installation](getting-started/01-Installation.md)
2. [Quick Start](getting-started/02-Quick-Start.md)
3. [Migration Quick Reference](guides/migration/quick-reference.md)

### Advanced Users
1. [Migration Playbooks](guides/migration/playbooks.md)
2. [Batch Migration](guides/migration/batch-features.md)
3. [Advanced Features](guides/enhanced-features.md)

### Developers
1. [Contributing Guide](development/contributing.md)
2. [Architecture](development/architecture.md)
3. [Testing Guide](development/testing-guide.md)
4. [API Reference](reference/api/)

### System Administrators
1. [Daemon Mode](features/daemon-mode.md)
2. [Security Best Practices](guides/security-best-practices.md)
3. [Production Deployment](guides/migration/playbooks.md)

## Contributing to Documentation

Documentation contributions are welcome! Please see:
- [Contributing Guide](development/contributing.md)
- [Documentation Style Guide](development/summaries/README.md)

## Archive

Historical implementation documents and old versions are in [archive/](archive/).
