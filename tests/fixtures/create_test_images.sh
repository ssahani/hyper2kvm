#!/bin/bash
# ============================================
# Create Test VM Disk Images
# ============================================
# Description: Generate fake VM disk images for testing
# Creates: VMDK, QCOW2, RAW images with filesystems
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_IMAGES_DIR="${SCRIPT_DIR}/images"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Creating Test VM Disk Images${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Create images directory
mkdir -p "${TEST_IMAGES_DIR}"

# Function to create a basic disk image with filesystem
create_linux_image() {
    local name="$1"
    local format="$2"
    local size="$3"

    echo -e "${GREEN}Creating ${name}.${format} (${size})...${NC}"

    local image_path="${TEST_IMAGES_DIR}/${name}.${format}"

    # Create empty image
    qemu-img create -f "${format}" "${image_path}" "${size}"

    # Create MBR partition table and filesystem
    # This requires root/sudo to create loop devices
    if [ "${EUID}" -eq 0 ]; then
        echo "  Creating partition table and filesystem..."

        # Setup loop device
        local loop_dev=$(losetup -f)
        losetup "${loop_dev}" "${image_path}"

        # Create partition
        parted -s "${loop_dev}" mklabel msdos
        parted -s "${loop_dev}" mkpart primary ext4 1MiB 100%
        parted -s "${loop_dev}" set 1 boot on

        # Inform kernel of partition changes
        partprobe "${loop_dev}"
        sleep 1

        # Format partition
        mkfs.ext4 -F "${loop_dev}p1"

        # Mount and add test files
        local mount_point="/tmp/test-mount-$$"
        mkdir -p "${mount_point}"
        mount "${loop_dev}p1" "${mount_point}"

        # Create test directory structure
        mkdir -p "${mount_point}"/{boot,etc,var,usr,home}

        # Create fake /etc/fstab
        cat > "${mount_point}/etc/fstab" <<EOF
# Test fstab for hyper2kvm testing
UUID=test-uuid-1234 / ext4 defaults 0 1
/dev/sda1 /boot ext4 defaults 0 2
EOF

        # Create fake grub config
        mkdir -p "${mount_point}/boot/grub2"
        cat > "${mount_point}/boot/grub2/grub.cfg" <<EOF
# Test GRUB2 configuration
set timeout=5
set default=0

menuentry 'Test Linux' {
    linux /vmlinuz root=/dev/sda1 ro quiet
    initrd /initrd.img
}
EOF

        # Create fake network config
        mkdir -p "${mount_point}/etc/sysconfig/network-scripts"
        cat > "${mount_point}/etc/sysconfig/network-scripts/ifcfg-eth0" <<EOF
# Test network config
DEVICE=eth0
BOOTPROTO=dhcp
ONBOOT=yes
TYPE=Ethernet
HWADDR=00:50:56:12:34:56
EOF

        # Unmount and cleanup
        umount "${mount_point}"
        rmdir "${mount_point}"
        losetup -d "${loop_dev}"

        echo -e "  ${GREEN}✓${NC} Created with filesystem and test data"
    else
        echo -e "  ${YELLOW}⚠${NC} Created empty (run with sudo to add filesystem)"
    fi
}

# Function to create Windows test image
create_windows_image() {
    local name="$1"
    local format="$2"
    local size="$3"

    echo -e "${GREEN}Creating ${name}.${format} (${size})...${NC}"

    local image_path="${TEST_IMAGES_DIR}/${name}.${format}"

    # Create empty image (Windows FS requires more complex setup)
    qemu-img create -f "${format}" "${image_path}" "${size}"

    echo -e "  ${YELLOW}⚠${NC} Created empty (Windows FS simulation requires guestfs)"
}

# Create test images

echo "Creating Linux test images..."
create_linux_image "test-linux-raw" "raw" "1G"
create_linux_image "test-linux-qcow2" "qcow2" "1G"

echo ""
echo "Creating VMDK test images..."
create_linux_image "test-linux-vmdk" "vmdk" "1G"

echo ""
echo "Creating Windows test images..."
create_windows_image "test-windows-qcow2" "qcow2" "2G"
create_windows_image "test-windows-vmdk" "vmdk" "2G"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Test Image Creation Complete${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Images created in: ${TEST_IMAGES_DIR}"
ls -lh "${TEST_IMAGES_DIR}/"
echo ""
echo "Note: Images with filesystems require sudo/root access"
echo "Run with: sudo $0"
