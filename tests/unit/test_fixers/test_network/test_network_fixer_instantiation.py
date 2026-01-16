# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Test NetworkFixer instantiation to prevent regression.

This test was added after a critical bug where NetworkFixersBackend
was instantiated without required arguments, causing runtime failures.
"""
from __future__ import annotations

import logging
import pytest

from hyper2kvm.fixers.network.core import NetworkFixer
from hyper2kvm.fixers.network.model import FixLevel


class TestNetworkFixerInstantiation:
    """Test NetworkFixer can be instantiated correctly."""

    def test_instantiate_with_defaults(self):
        """Test NetworkFixer instantiates with default arguments."""
        logger = logging.getLogger(__name__)
        fixer = NetworkFixer(logger=logger)

        # Verify components created
        assert fixer.discovery is not None
        assert fixer.topology is not None
        assert fixer.validation is not None
        assert fixer.backend is not None

        # Verify backend has required attributes
        assert hasattr(fixer.backend, 'vmware_drivers')
        assert hasattr(fixer.backend, 'mac_pinning_patterns')
        assert hasattr(fixer.backend, 'logger')
        assert hasattr(fixer.backend, 'fix_level')

    def test_instantiate_with_all_fix_levels(self):
        """Test NetworkFixer instantiates with all fix levels."""
        logger = logging.getLogger(__name__)

        for level in [FixLevel.CONSERVATIVE, FixLevel.MODERATE, FixLevel.AGGRESSIVE]:
            fixer = NetworkFixer(logger=logger, fix_level=level)
            assert fixer.fix_level == level
            assert fixer.backend.fix_level == level

    def test_instantiate_with_dry_run(self):
        """Test NetworkFixer instantiates with dry_run enabled."""
        logger = logging.getLogger(__name__)
        fixer = NetworkFixer(logger=logger, dry_run=True)
        assert fixer.dry_run is True

    def test_backend_has_vmware_drivers(self):
        """Test backend has VMware drivers configured."""
        logger = logging.getLogger(__name__)
        fixer = NetworkFixer(logger=logger)

        # Should have common VMware drivers
        assert len(fixer.backend.vmware_drivers) > 0
        assert 'vmxnet3' in fixer.backend.vmware_drivers
        assert 'e1000' in fixer.backend.vmware_drivers

    def test_backend_has_mac_pinning_patterns(self):
        """Test backend has MAC pinning patterns configured."""
        logger = logging.getLogger(__name__)
        fixer = NetworkFixer(logger=logger)

        # Should have MAC pinning patterns
        assert len(fixer.backend.mac_pinning_patterns) > 0
        # Patterns are tuples of (regex, description)
        assert all(isinstance(p, tuple) and len(p) == 2
                  for p in fixer.backend.mac_pinning_patterns)

    def test_backward_compatible_import(self):
        """Test backward compatible import from network_fixer module."""
        from hyper2kvm.fixers.network_fixer import NetworkFixer as NetworkFixerCompat

        logger = logging.getLogger(__name__)
        fixer = NetworkFixerCompat(logger=logger)

        # Should be the same class
        assert type(fixer).__name__ == 'NetworkFixer'
        assert fixer.backend is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
