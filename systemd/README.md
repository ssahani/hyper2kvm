# hyper2kvm Systemd Service Units

This directory contains systemd service unit files for running hyper2kvm as a daemon.

## Available Units

### hyper2kvm.service
Single instance service for the main hyper2kvm daemon.

**Configuration:**
- Config file: `/etc/hyper2kvm/hyper2kvm.conf`
- Working directory: `/var/lib/hyper2kvm`
- Log directory: `/var/log/hyper2kvm`

**Usage:**
```bash
# Enable and start the service
sudo systemctl enable --now hyper2kvm.service

# Check status
sudo systemctl status hyper2kvm.service

# View logs
sudo journalctl -u hyper2kvm.service -f
```

### hyper2kvm@.service
Template service for running multiple instances with different configurations.

**Configuration:**
- Config file: `/etc/hyper2kvm/{instance}.yaml`
- Instance name replaces `%i` in the template

**Usage:**
```bash
# Create configuration
sudo mkdir -p /etc/hyper2kvm
sudo cp my-config.yaml /etc/hyper2kvm/production.yaml

# Start instance
sudo systemctl enable --now hyper2kvm@production.service

# Multiple instances
sudo systemctl enable --now hyper2kvm@vsphere-prod.service
sudo systemctl enable --now hyper2kvm@azure-dev.service

# Check status
sudo systemctl status hyper2kvm@production.service

# View logs
sudo journalctl -u hyper2kvm@production.service -f
```

## Prerequisites

### Install the Python Package

**IMPORTANT:** Before setting up the systemd service, you must install the hyper2kvm Python package properly.

```bash
# Install from the repository (development mode)
cd /path/to/hyper2kvm
sudo /usr/bin/python3 -m pip install -e .

# Or install from PyPI (when available)
sudo /usr/bin/python3 -m pip install hyper2kvm
```

**Critical Notes:**
- Always use `/usr/bin/python3` (not `/usr/sbin/python3` or other interpreters)
- This ensures the wrapper script at `/usr/local/bin/hyper2kvm` is created with the correct shebang
- The package must be installed system-wide (with sudo) for the systemd service to access it

**Verify Installation:**
```bash
# Check that hyper2kvm is installed
which hyper2kvm
# Should show: /usr/local/bin/hyper2kvm

# Verify the shebang is correct
head -1 /usr/local/bin/hyper2kvm
# Should show: #!/usr/bin/python3 (NOT /usr/sbin/python3)

# Test the command
hyper2kvm --help

# Verify Python can import the module
/usr/bin/python3 -c "import hyper2kvm; print(hyper2kvm.__file__)"
```

### System Dependencies

Install required system packages:

```bash
# Fedora/RHEL/CentOS
sudo dnf install -y qemu-img libguestfs libguestfs-tools python3-pip

# Ubuntu/Debian
sudo apt-get install -y qemu-utils libguestfs-tools python3-pip

# Arch Linux
sudo pacman -S qemu-img libguestfs python-pip
```

## Setup

### 1. Create System User and Directories

**Note:** When installing via RPM, this is done automatically. Manual setup is only needed for non-RPM installations.

```bash
# Create hyper2kvm system user
sudo useradd -r -s /sbin/nologin -d /var/lib/hyper2kvm -c "hyper2kvm daemon" hyper2kvm

# Add user to necessary groups for libguestfs, QEMU, and libvirt access
# (RPM installation does this automatically)
for group in qemu kvm libvirt disk; do
    if getent group "$group" >/dev/null 2>&1; then
        sudo usermod -a -G "$group" hyper2kvm
    fi
done

# Verify group membership
sudo id hyper2kvm
# Expected output: uid=XXX(hyper2kvm) gid=XXX(hyper2kvm) groups=XXX(hyper2kvm),XXX(qemu),XXX(kvm),XXX(libvirt),XXX(disk)

# Create directories
sudo mkdir -p /var/lib/hyper2kvm
sudo mkdir -p /var/log/hyper2kvm
sudo mkdir -p /etc/hyper2kvm

# Set permissions
sudo chown -R hyper2kvm:hyper2kvm /var/lib/hyper2kvm
sudo chown -R hyper2kvm:hyper2kvm /var/log/hyper2kvm
sudo chown -R root:hyper2kvm /etc/hyper2kvm
sudo chmod 750 /etc/hyper2kvm
```

**Group Memberships Explained:**
- `qemu` - Required for QEMU operations and disk image access
- `kvm` - Required for KVM acceleration access (/dev/kvm)
- `libvirt` - Required for libvirt domain management and socket access
- `disk` - Optional, for direct disk device access in some scenarios

### 2. Create Configuration

```bash
# Example configuration for daemon mode
cat > /tmp/hyper2kvm-daemon.yaml <<'EOF'
# Daemon mode - watches directory for new disk files
command: daemon
daemon: true

# Directory to watch for incoming disk files
# Supports: .vmdk, .ova, .ovf, .vhd, .vhdx, .raw, .img, .ami
watch_dir: /var/lib/hyper2kvm/queue

# Output directory for converted VMs
output_dir: /var/lib/hyper2kvm/output

# Working directory for temporary files
workdir: /var/lib/hyper2kvm/work

# Output format and compression
out_format: qcow2
compress: true
flatten: true

# Enable recovery mode for resumable conversions
enable_recovery: true

# Logging
log_file: /var/log/hyper2kvm/hyper2kvm.log
verbose: 1

# Guest OS fixes
fstab_mode: stabilize-all
regen_initramfs: true
EOF

sudo cp /tmp/hyper2kvm-daemon.yaml /etc/hyper2kvm/hyper2kvm.conf
sudo chown root:hyper2kvm /etc/hyper2kvm/hyper2kvm.conf
sudo chmod 640 /etc/hyper2kvm/hyper2kvm.conf
```

### 3. Customize Service (Optional)

Edit the service file if you need different settings:

```bash
# Override the service
sudo systemctl edit hyper2kvm.service

# Add custom settings
[Service]
# Increase memory limit for large VMs
MemoryMax=16G

# Run as root if libguestfs requires it
User=root
Group=root

# Custom environment
Environment="LIBGUESTFS_BACKEND=direct"
```

## Security Considerations

The service units include security hardening:

- **NoNewPrivileges**: Prevents privilege escalation
- **PrivateTmp**: Isolated /tmp directory
- **ProtectSystem=strict**: Read-only /usr, /boot, /efi
- **ProtectHome**: No access to user home directories
- **ReadWritePaths**: Limited write access to work directories
- **MemoryMax**: Memory limit to prevent OOM
- **TasksMax**: Process limit

### Running as Root

If you need root access for libguestfs operations:

```bash
# Edit the service
sudo systemctl edit hyper2kvm.service

# Add:
[Service]
User=root
Group=root
ReadWritePaths=/var/lib/hyper2kvm /var/log/hyper2kvm /tmp
```

## Example Workflows

### vSphere Automated Migration

```yaml
# /etc/hyper2kvm/vsphere-prod.yaml
# Daemon mode for watching directory and processing vSphere exports
command: daemon
daemon: true

# Watch directory for vSphere-exported disk files
watch_dir: /var/lib/hyper2kvm/vsphere-queue

# Output settings
output_dir: /var/lib/hyper2kvm/vsphere-output
workdir: /var/lib/hyper2kvm/vsphere-work
out_format: qcow2
compress: true
flatten: true
enable_recovery: true

# Guest OS fixes
fstab_mode: stabilize-all
regen_initramfs: true

# Logging
log_file: /var/log/hyper2kvm/vsphere.log
verbose: 1
```

```bash
# Set environment variable
sudo systemctl edit hyper2kvm@vsphere-prod.service

# Add:
[Service]
Environment="VCENTER_PASSWORD=secret"

# Or use a drop-in file
sudo mkdir -p /etc/systemd/system/hyper2kvm@vsphere-prod.service.d
cat > /etc/systemd/system/hyper2kvm@vsphere-prod.service.d/credentials.conf <<EOF
[Service]
Environment="VCENTER_PASSWORD=secret"
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hyper2kvm@vsphere-prod.service
```

### Azure Batch Migration

```yaml
# /etc/hyper2kvm/azure-batch.yaml
# Daemon mode for watching directory and processing Azure exports
command: daemon
daemon: true

# Watch directory for Azure-exported disk files
watch_dir: /var/lib/hyper2kvm/azure-queue

# Output settings
output_dir: /var/lib/hyper2kvm/azure-output
workdir: /var/lib/hyper2kvm/azure-work
out_format: qcow2
compress: true
flatten: true
enable_recovery: true

# Logging
log_file: /var/log/hyper2kvm/azure.log
verbose: 1
```

## Monitoring

### Check Service Status

```bash
# Status
systemctl status hyper2kvm.service

# Logs
journalctl -u hyper2kvm.service -f

# Resource usage
systemd-cgtop
```

### Common Issues

**Permission denied:**
```bash
# Check user and permissions
sudo -u hyper2kvm ls /var/lib/hyper2kvm
sudo namei -l /var/lib/hyper2kvm
```

**Service fails to start:**
```bash
# Check logs
sudo journalctl -u hyper2kvm.service -n 50 --no-pager

# Validate config
hyper2kvm --config /etc/hyper2kvm/hyper2kvm.conf --dry-run
```

**Memory limits:**
```bash
# Check current limit
systemctl show hyper2kvm.service -p MemoryMax

# Adjust if needed
sudo systemctl edit hyper2kvm.service
# Add: MemoryMax=16G
```

**Module not found (incorrect Python shebang):**

If you see "ModuleNotFoundError: No module named 'hyper2kvm'" even though the package is installed:

```bash
# 1. Check the shebang
head -1 /usr/local/bin/hyper2kvm
# Should be: #!/usr/bin/python3
# If it shows #!/usr/sbin/python3 or another interpreter, it needs to be fixed

# 2. Fix the issue by reinstalling
sudo rm /usr/local/bin/hyper2kvm
sudo pip3 uninstall -y hyper2kvm
sudo /usr/bin/python3 -m pip install -e /path/to/hyper2kvm

# 3. Verify the fix
head -1 /usr/local/bin/hyper2kvm
/usr/local/bin/hyper2kvm --help

# 4. Restart the service
sudo systemctl restart hyper2kvm.service
```

## Uninstall

```bash
# Stop and disable services
sudo systemctl stop hyper2kvm.service
sudo systemctl disable hyper2kvm.service

# Remove user and directories
sudo userdel hyper2kvm
sudo rm -rf /var/lib/hyper2kvm
sudo rm -rf /var/log/hyper2kvm
sudo rm -rf /etc/hyper2kvm

# Remove systemd files
sudo rm /etc/systemd/system/hyper2kvm*.service
sudo systemctl daemon-reload
```
