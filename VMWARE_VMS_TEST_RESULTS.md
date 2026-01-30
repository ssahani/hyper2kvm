# VMware Production VMs Test Results

## Test Date: 2026-01-25

### VMware VMs Tested from /home/ssahani/vmware

All 3 production VMware VMs successfully converted! ✅

## Test Results

### 1. ✅ openSUSE Leap 15.4 (7.6G VMDK)
- **Source**: `/home/ssahani/vmware/Clone of openSUSE_Leap_15.4_VM_LinuxVMImages.COM/`
- **Detected**: openSUSE Leap 15.4 15.4 (distro=opensuse-leap)
- **Output**: `opensuse-leap-15.4.qcow2` (3.0G compressed)
- **Status**: ✅ PASSED
- **Filesystem**: Successfully mounted and fixed
- **Features**: Full VMware VM with complete configuration

### 2. ✅ Ubuntu 24.04.3 LTS (8.8G VMDK)
- **Source**: `/home/ssahani/vmware/Ubuntu-64-bit/`
- **Detected**: Ubuntu 24.04.3 LTS 24.4 (distro=ubuntu)
- **Output**: `ubuntu-vmware.qcow2` (4.8G compressed)
- **Status**: ✅ PASSED
- **Filesystem**: Successfully mounted and fixed
- **Features**: VMware installation with autoinst configuration

### 3. ✅ VMware Photon OS 5.0 (882M VMDK)
- **Source**: `/home/ssahani/vmware/VMware Photon OS 64-bit/`
- **Detected**: VMware Photon OS/Linux 5.0 (distro=photon)
- **Output**: `photon-vmware.qcow2` (373M compressed)
- **Status**: ✅ PASSED
- **Filesystem**: Successfully mounted and fixed
- **Note**: This is a real VMware installation, not the OVA version that had I/O errors

## Windows VMs (Not Yet Tested)

Two Windows VMs are available but not tested in this run:

### 4. ⊘ Windows 10 (11G split VMDK)
- **Source**: `/home/ssahani/vmware/win10/`
- **Format**: Split VMDK (win10-s001 through s004)
- **Status**: Not tested yet
- **Note**: Requires Windows driver injection testing

### 5. ⊘ Windows 11 (14G split VMDK)
- **Source**: `/home/ssahani/vmware/win11/`
- **Format**: Split VMDK (win11-s001 through s004)
- **Status**: Not tested yet
- **Note**: Requires Windows driver injection testing

## Statistics

### Linux VMs
- **Total tested**: 3 VMware production VMs
- **Passed**: 3/3 (100%)
- **Failed**: 0/3
- **Total source size**: 17.3G (7.6G + 8.8G + 882M)
- **Total output size**: 8.2G (3.0G + 4.8G + 373M)
- **Compression ratio**: 47% average (17.3G → 8.2G)

### All VMs (Including Previous Tests)
- **Total Linux distributions tested**: 10
  - Core suite: Fedora 42, CentOS 10, Arch, Ubuntu 25.04
  - Extended: Fedora Cloud 43, Arch 2024
  - VMware VMs: openSUSE Leap 15.4, Ubuntu 24.04, Photon OS 5.0, (Photon OVA failed)
- **Passed**: 9/10 (90%)
- **Failed due to code**: 0/10 (100% code success)
- **Failed due to image issues**: 1/10 (Photon OS OVA - qemu-nbd incompatibility)

## Distributions Validated

### Successfully Tested Linux Distributions
- ✅ Fedora 42 Server
- ✅ Fedora Cloud Base 43
- ✅ CentOS 10 Server
- ✅ **openSUSE Leap 15.4** (NEW)
- ✅ Ubuntu Server 25.04
- ✅ **Ubuntu 24.04.3 LTS** (VMware, NEW)
- ✅ Arch Linux (2 versions)
- ✅ **VMware Photon OS 5.0** (VMware installation, NEW)

### Filesystems Validated
- ✅ XFS on LVM (Fedora 42, CentOS 10)
- ✅ Btrfs with standard subvolumes (Arch Linux)
- ✅ Btrfs with custom subvolumes (Fedora Cloud, openSUSE)
- ✅ ext4 on partitions (Ubuntu 25.04, Ubuntu 24.04, Photon OS)

### Source Formats Validated
- ✅ VMDK (monolithic): Fedora, CentOS, Arch, openSUSE
- ✅ VMDK (VMware production VMs): openSUSE, Ubuntu, Photon OS
- ✅ VDI: Ubuntu 25.04
- ✅ QCOW2: Fedora Cloud Base 43

## Converted VM Images

All successful conversions are in `/home/ssahani/tt/hyper2kvm/out/`:

### Core Test Suite
- `fedora42-test/fedora42-server.qcow2` (1.6G)
- `centos10-test/centos10-server.qcow2` (1.4G)
- `arch-test/arch-64.qcow2` (618M)
- `ubuntu25-test/ubuntu25-server.qcow2` (2.8G)

### Extended Test Suite
- `fedora43-cloud-test/fedora43-cloud.qcow2` (563M)
- `arch2-test/arch-2024.qcow2` (564M)

### VMware Production VMs (NEW)
- `opensuse-leap-test/opensuse-leap-15.4.qcow2` (3.0G)
- `ubuntu-vmware-test/ubuntu-vmware.qcow2` (4.8G)
- `photon-vmware-test/photon-vmware.qcow2` (373M)

## Key Achievements

1. **100% success rate on real VMware VMs** - All 3 production VMware VMs converted successfully
2. **New distribution support**: openSUSE Leap 15.4, Ubuntu 24.04 VMware edition
3. **Photon OS success**: VMware installation works (OVA version had format issues)
4. **Large VM handling**: Successfully converted 8.8G Ubuntu VMware VM
5. **Production readiness**: Validated on actual VMware Workstation VMs with full configurations

## Test Configurations Created

- `test-confs/opensuse-leap-test.yaml`
- `test-confs/ubuntu-vmware-test.yaml`
- `test-confs/photon-vmware-test.yaml`
- `test-vmware-vms.sh` (automated test runner)

## Next Steps

- Test Windows 10 VM with driver injection
- Test Windows 11 VM with driver injection
- Validate split VMDK handling for Windows VMs
