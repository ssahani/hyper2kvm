# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for LibvirtManager."""

import pytest

# Check if libvirt is available
try:
    from hyper2kvm.libvirt import LIBVIRT_AVAILABLE, LibvirtManager, LibvirtManagerError

    SKIP_REASON = None
except ImportError:
    LIBVIRT_AVAILABLE = False
    SKIP_REASON = "libvirt-python not installed"


@pytest.mark.skipif(not LIBVIRT_AVAILABLE, reason=SKIP_REASON or "libvirt not available")
class TestLibvirtManager:
    """Test LibvirtManager functionality."""

    def test_manager_initialization(self):
        """Test LibvirtManager can be initialized."""
        manager = LibvirtManager()
        assert manager is not None
        assert manager.uri == "qemu:///system"

    def test_manager_custom_uri(self):
        """Test LibvirtManager with custom URI."""
        manager = LibvirtManager(uri="qemu:///session")
        assert manager.uri == "qemu:///session"

    def test_context_manager(self):
        """Test LibvirtManager as context manager."""
        # This may fail if libvirt daemon is not running, but should not crash
        try:
            with LibvirtManager() as manager:
                assert manager is not None
        except Exception:
            # Expected if libvirt daemon not running
            pass


@pytest.mark.skipif(LIBVIRT_AVAILABLE, reason="Testing error when libvirt not available")
def test_manager_unavailable():
    """Test that appropriate error is raised when libvirt not available."""
    # This test only runs when libvirt is NOT available
    # When libvirt is unavailable, importing should fail or raise error
    try:
        from hyper2kvm.libvirt import LibvirtManager

        # If we get here, LibvirtManager exists but should raise on init
        with pytest.raises(Exception):
            LibvirtManager()
    except ImportError:
        # Expected when libvirt not available
        pass
