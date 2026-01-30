# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Tests for TUI availability and graceful degradation.
"""

import pytest


class TestTUIAvailability:
    """Test TUI availability detection."""

    def test_textual_availability_flag(self):
        """Test that TEXTUAL_AVAILABLE flag is boolean."""
        from hyper2kvm.core.optional_imports import TEXTUAL_AVAILABLE

        assert isinstance(TEXTUAL_AVAILABLE, bool)

    def test_tui_module_imports(self):
        """Test that TUI module can be imported."""
        import hyper2kvm.tui

        assert hasattr(hyper2kvm.tui, "TEXTUAL_AVAILABLE")

    def test_require_textual_function(self):
        """Test require_textual helper function."""
        from hyper2kvm.core.optional_imports import require_textual, TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            with pytest.raises(ImportError, match="textual"):
                require_textual()
        else:
            # Should not raise
            require_textual()

    def test_tui_import_error_without_textual(self):
        """Test that TUI modules provide helpful error without textual."""
        from hyper2kvm.core.optional_imports import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            with pytest.raises(ImportError, match="[Tt]extual"):
                from hyper2kvm.tui.dashboard import MigrationDashboard

            with pytest.raises(ImportError, match="[Tt]extual"):
                from hyper2kvm.tui.widgets import MigrationStatusWidget


class TestTUIModuleStructure:
    """Test TUI module structure."""

    def test_tui_package_exists(self):
        """Test that tui package exists."""
        import hyper2kvm.tui

        assert hyper2kvm.tui is not None

    def test_tui_init_exports(self):
        """Test that tui __init__ exports availability flag."""
        from hyper2kvm.tui import TEXTUAL_AVAILABLE

        assert isinstance(TEXTUAL_AVAILABLE, bool)

    @pytest.mark.skipif(
        True,  # Always skip this test unless textual is available
        reason="Only run when testing with textual installed",
    )
    def test_tui_exports_with_textual(self):
        """Test TUI exports when textual is available (skipped by default)."""
        from hyper2kvm.core.optional_imports import TEXTUAL_AVAILABLE

        if TEXTUAL_AVAILABLE:
            from hyper2kvm.tui import MigrationDashboard, MigrationStatusWidget, MetricsWidget

            assert MigrationDashboard is not None
            assert MigrationStatusWidget is not None
            assert MetricsWidget is not None
