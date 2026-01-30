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
command: local

# Daemon mode settings
daemon:
  enabled: true
  watch_dir: /var/lib/hyper2kvm/queue
  poll_interval: 60  # seconds
  max_concurrent: 2

# Default settings for migrations
output_dir: /var/lib/hyper2kvm/output
workdir: /var/lib/hyper2kvm/work
out_format: qcow2
compress: true
checksum: true

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
command: vsphere

vcenter: vcenter.example.com
vc_user: migration@vsphere.local
vc_password_env: VCENTER_PASSWORD
dc_name: Production-DC

daemon:
  enabled: true
  watch_dir: /var/lib/hyper2kvm/vsphere-queue
  poll_interval: 300

output_dir: /var/lib/hyper2kvm/vsphere-output
out_format: qcow2
compress: true

fstab_mode: stabilize-all
regen_initramfs: true
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
command: azure

azure:
  subscription: "Production"
  resource_group: legacy-vms

daemon:
  enabled: true
  watch_dir: /var/lib/hyper2kvm/azure-queue
  batch_size: 5

output_dir: /var/lib/hyper2kvm/azure-output
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
