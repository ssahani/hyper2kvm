# Security Policy

## Overview

hyper2kvm handles sensitive credentials and requires elevated privileges for VM disk operations. This document outlines security best practices for deployment and operation.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

## Reporting Vulnerabilities

If you discover a security vulnerability, please:

1. **DO NOT** open a public GitHub issue
2. Email the maintainers with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if available)
3. Allow 90 days for coordinated disclosure

## Security Considerations

### 1. Password and Credential Handling

#### vSphere/VMware Credentials

**Best Practices:**
- Use environment variables (`VS_PASSWORD_ENV`, `VC_PASSWORD_ENV`) instead of command-line arguments or YAML files
- Set restrictive permissions on YAML config files containing credentials: `chmod 600 config.yaml`
- Never commit credentials to version control
- Use vSphere service accounts with minimal required permissions
- Rotate credentials regularly

**Internal Security:**
- Password files are created with `0o600` permissions atomically (fixed in recent versions)
- Passwords are cleared from memory after use where possible
- Temporary password files are deleted in `finally` blocks

**Example Secure Configuration:**
```yaml
# config.yaml (chmod 600)
cmd: vsphere
vs_user: migration-service-account@vsphere.local
vs_password_env: VSPHERE_PASSWORD  # Read from environment
vs_host: vcenter.example.com
```

```bash
# Set password securely
export VSPHERE_PASSWORD='your-password-here'
chmod 600 config.yaml
hyper2kvm -c config.yaml
```

#### Azure Credentials

**Best Practices:**
- Use `az login` with managed identity or service principal
- Avoid storing subscription/tenant IDs in YAML if possible
- Use Azure Key Vault for production deployments
- Grant minimum required RBAC permissions (Reader + Disk Export Operator)

**Required Azure Permissions:**
- `Microsoft.Compute/disks/read`
- `Microsoft.Compute/snapshots/read`
- `Microsoft.Compute/snapshots/write`
- `Microsoft.Compute/snapshots/delete`
- `Microsoft.Compute/disks/beginGetAccess/action` (SAS token generation)
- `Microsoft.Compute/virtualMachines/read`

#### LUKS/Encrypted Disk Passphrases

**Best Practices:**
- Use `luks_passphrase_env` instead of `luks_passphrase` in YAML
- Store passphrases in secrets management systems (Vault, AWS Secrets Manager, etc.)
- Use keyfiles with `0o400` permissions when possible
- Avoid passphrase reuse across VMs

### 2. Root/Sudo Requirements

hyper2kvm uses `libguestfs` which requires root/sudo for:
- Mounting disk images via loopback devices
- Modifying filesystem contents
- Injecting kernel modules and drivers

**Deployment Options:**

#### Option A: Run as Root (Simplest)
```bash
sudo hyper2kvm -c config.yaml
```
**Risk:** Full root access to the system.

#### Option B: Sudo Wrapper (Recommended)
Create `/etc/sudoers.d/hyper2kvm`:
```
migration-user ALL=(root) NOPASSWD: /usr/bin/guestfish
migration-user ALL=(root) NOPASSWD: /usr/bin/guestmount
migration-user ALL=(root) NOPASSWD: /usr/bin/virt-v2v
migration-user ALL=(root) NOPASSWD: /usr/bin/qemu-img
```
**Risk:** Limited to specific binaries, but those binaries can modify arbitrary files.

#### Option C: Dedicated VM/Container (Most Secure)
- Run hyper2kvm in an isolated VM or container
- Use volume mounts for input/output directories only
- Limit network access (only to source hypervisor APIs)
- Discard VM/container after migration

### 3. Multi-User System Considerations

**Risks:**
- Temporary files in `/tmp` or output directories may be readable by other users
- Downloaded VHDs contain sensitive data
- Process arguments may expose credentials in `ps` output
- Checkpoint files contain VM metadata

**Mitigations:**
```bash
# Set restrictive umask
umask 077

# Use private output directory
mkdir -p ~/hyper2kvm-output
chmod 700 ~/hyper2kvm-output

# Check for leaked credentials in process list
ps aux | grep hyper2kvm  # Should not show passwords

# Encrypt output directory (optional)
# Use LUKS, eCryptfs, or filesystem-level encryption
```

### 4. Environment Variable Security

**Risks:**
- Environment variables are inherited by child processes
- May be logged in debug output
- Visible in `/proc/$PID/environ` to users with access

**Mitigations:**
- Unset sensitive env vars immediately after reading:
  ```bash
  export VSPHERE_PASSWORD='...'
  hyper2kvm -c config.yaml
  unset VSPHERE_PASSWORD
  ```
- Use process-specific environment (not system-wide)
- Review logs for accidental credential leakage

### 5. Archive Extraction Safety

**Protections Implemented:**
- Symlink attack prevention (checks for symlinks before writing)
- Path traversal defense (validates extraction paths)
- Permission masking (removes world-writable bits from archives)
- Uses `O_NOFOLLOW` where supported

**Recommendations:**
- Only extract archives from trusted sources
- Review extracted contents before processing
- Use checksum verification when available

### 6. Network Security

#### vSphere Connections
- Always use TLS (HTTPS) for vCenter connections
- Verify TLS certificates (`vs_no_verify: false` in production)
- Use VDDK thumbprint verification when available
- Isolate migration traffic on dedicated VLANs

#### Azure Connections
- SAS tokens are time-limited (default 1 hour)
- Use private endpoints for Azure Storage when possible
- Enable Azure Storage firewall rules
- Audit SAS token usage via Azure Monitor

### 7. Output Data Protection

**VM Disks Contain:**
- Operating system files
- Application data and databases
- Cached credentials and SSH keys
- Browser history and cookies
- Log files with sensitive information

**Recommendations:**
- Encrypt output directories
- Use dedicated storage with access controls
- Securely wipe disks after successful import to target
- Consider data residency and compliance requirements
- Review contents before sharing or moving to less secure storage

### 8. Logging and Audit

**What is Logged:**
- Source VM metadata (names, sizes, UUIDs)
- Connection endpoints (vCenter URLs, Azure subscriptions)
- Operation progress and errors
- File paths and sizes
- SAS token hashes (first 10 chars only, for audit trail)

**What is NOT Logged:**
- Passwords or passphrases
- Full SAS tokens
- VM disk contents
- LUKS keyfile contents

**Recommendations:**
- Review logs before sharing for support
- Rotate logs regularly
- Restrict log file access: `chmod 640 /var/log/hyper2kvm.log`
- Redact sensitive paths/names before sharing

### 9. Dependency Security

**Critical Dependencies:**
- `libguestfs` - runs with root privileges
- `qemu-img` - parses untrusted disk images
- `virt-v2v` - connects to remote hypervisors
- `requests` - makes HTTP requests
- `pyVmomi` - parses vSphere API responses

**Recommendations:**
- Keep dependencies updated (security patches)
- Use distribution packages when available (signed, reviewed)
- Monitor CVE databases for libguestfs/QEMU vulnerabilities
- Consider running in AppArmor/SELinux confined mode

### 10. Deployment Security Checklist

Before production deployment:

- [ ] Credentials stored in environment variables or secrets manager
- [ ] YAML config files have `chmod 600` permissions
- [ ] Output directory has `chmod 700` permissions
- [ ] Running in dedicated VM/container (recommended)
- [ ] TLS certificate verification enabled (`vs_no_verify: false`)
- [ ] Logs are rotated and access-controlled
- [ ] Recovery checkpoints directory is private (`chmod 700`)
- [ ] Service account permissions are minimal (least privilege)
- [ ] Network access limited to required endpoints only
- [ ] Monitoring and alerting configured for failures
- [ ] Tested credential rotation procedures
- [ ] Documented incident response plan
- [ ] Reviewed audit logs for credential leakage
- [ ] Planned secure disposal of output disks
- [ ] Verified compliance with data residency requirements

## Known Security Issues (Fixed)

### CVE-Candidate: Password File Race Condition (Fixed 2026-01-15)
- **Severity:** High
- **Component:** `vmware/clients/client.py`, `vmware/utils/v2v.py`
- **Issue:** Password files created with default umask, then chmod'd (race condition window)
- **Fix:** Use `os.open(O_CREAT|O_EXCL|O_WRONLY, 0o600)` for atomic creation
- **Status:** ✅ Fixed in commit XXX

### Archive Permission Extraction (Fixed 2026-01-15)
- **Severity:** Medium
- **Component:** `converters/extractors/ami.py`
- **Issue:** Extracted files could be world-writable if archive contained malicious permissions
- **Fix:** Mask permissions with `& 0o755` to remove world-writable bit
- **Status:** ✅ Fixed in commit XXX

## Security Hardening Guide

### AppArmor Profile (Example)

```apparmor
# /etc/apparmor.d/usr.local.bin.hyper2kvm
#include <tunables/global>

/usr/local/bin/hyper2kvm {
  #include <abstractions/base>
  #include <abstractions/python>

  # Allow reading config
  /etc/hyper2kvm/** r,
  owner @{HOME}/.hyper2kvm/** r,

  # Allow writing output
  owner /var/lib/hyper2kvm/** rw,

  # Allow libguestfs operations
  /usr/bin/guestfish Px,
  /usr/bin/qemu-img Px,

  # Network (vSphere/Azure)
  network inet stream,
  network inet6 stream,

  # Deny everything else
  deny /home/** w,
  deny /root/** rw,
}
```

### SELinux Policy (Example)

```bash
# Create custom policy for hyper2kvm
semanage fcontext -a -t hyper2kvm_exec_t /usr/local/bin/hyper2kvm
semanage fcontext -a -t hyper2kvm_data_t '/var/lib/hyper2kvm(/.*)?'
restorecon -Rv /usr/local/bin/hyper2kvm /var/lib/hyper2kvm
```

### Container Hardening (Example)

```dockerfile
# Dockerfile
FROM fedora:39
RUN dnf install -y libguestfs-tools qemu-img python3-pip
RUN useradd -m -u 1000 migration
USER migration
WORKDIR /home/migration
COPY --chown=migration:migration hyper2kvm /usr/local/bin/
RUN pip install --user hyper2kvm
ENTRYPOINT ["/usr/local/bin/hyper2kvm"]
```

```bash
# Run with minimal privileges
docker run --rm \
  --cap-drop=ALL \
  --cap-add=SYS_ADMIN \
  --security-opt apparmor=docker-default \
  --read-only \
  -v /path/to/output:/output:rw \
  hyper2kvm:latest -c /config/migration.yaml
```

## Security Contact

For security-related questions or to report vulnerabilities:
- **Email:** [security contact - to be filled]
- **Response Time:** 48 hours for acknowledgment, 90 days for patch
- **Encryption:** [PGP key - to be provided]

## Further Reading

- [libguestfs Security](http://libguestfs.org/guestfs-security.1.html)
- [QEMU Security](https://www.qemu.org/docs/master/system/security.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [CIS Benchmark for Container Security](https://www.cisecurity.org/benchmark/docker)
