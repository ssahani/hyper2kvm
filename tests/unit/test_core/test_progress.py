# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for progress bar functionality.
"""

import pytest
import io
from hyper2kvm.core.progress import (
    SimpleProgressBar,
    ProgressBarConfig,
    ProgressManager,
    Colors,
    create_progress_bar,
)
from hyper2kvm.core.optional_imports import RICH_AVAILABLE


class TestColors:
    """Test color support detection."""

    def test_color_constants_exist(self):
        """Test that color constants are defined."""
        assert hasattr(Colors, "BRIGHT_ORANGE")
        assert hasattr(Colors, "GOLD_ORANGE")
        assert hasattr(Colors, "LIGHT_ORANGE")
        assert hasattr(Colors, "SUCCESS_GREEN")
        assert hasattr(Colors, "ERROR_RED")

    def test_supports_color(self):
        """Test color support detection."""
        # This will depend on the environment
        result = Colors.supports_color()
        assert isinstance(result, bool)


class TestProgressBarConfig:
    """Test progress bar configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = ProgressBarConfig()
        assert config.width == 40
        assert config.filled_char == "█"
        assert config.empty_char == "░"
        assert config.left_bracket == "["
        assert config.right_bracket == "]"
        assert config.show_percentage is True
        assert config.show_spinner is False
        assert config.show_eta is False
        assert config.color_enabled is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ProgressBarConfig(
            width=50,
            filled_char="=",
            empty_char=" ",
            show_spinner=True,
            show_eta=True,
        )
        assert config.width == 50
        assert config.filled_char == "="
        assert config.empty_char == " "
        assert config.show_spinner is True
        assert config.show_eta is True


class TestSimpleProgressBar:
    """Test simple progress bar."""

    def test_creation(self):
        """Test progress bar creation."""
        output = io.StringIO()
        progress = SimpleProgressBar(
            total=100,
            description="Test",
            file=output,
        )
        assert progress.total == 100
        assert progress.current == 0.0
        assert progress.description == "Test"

    def test_update(self):
        """Test progress update."""
        output = io.StringIO()
        config = ProgressBarConfig(color_enabled=False)
        progress = SimpleProgressBar(
            total=100,
            description="Test",
            config=config,
            file=output,
        )

        progress.update(50)
        assert progress.current == 50

        result = output.getvalue()
        assert "50%" in result or "50" in result

    def test_advance(self):
        """Test progress advance."""
        output = io.StringIO()
        progress = SimpleProgressBar(total=100, file=output)

        progress.advance(10)
        assert progress.current == 10

        progress.advance(5)
        assert progress.current == 15

    def test_finish(self):
        """Test progress finish."""
        output = io.StringIO()
        config = ProgressBarConfig(color_enabled=False)
        progress = SimpleProgressBar(
            total=100,
            description="Test",
            config=config,
            file=output,
        )

        progress.finish("Done!")

        result = output.getvalue()
        assert "100%" in result or "Done!" in result

    def test_progress_clamping(self):
        """Test that progress is clamped to [0, total]."""
        output = io.StringIO()
        progress = SimpleProgressBar(total=100, file=output)

        # Test over-limit
        progress.update(150)
        assert progress.current == 100

        # Test under-limit (now properly clamped to 0)
        progress.update(-10)
        assert progress.current == 0.0  # Should be clamped to 0

    def test_spinner_frames(self):
        """Test spinner animation frames."""
        output = io.StringIO()
        config = ProgressBarConfig(show_spinner=True, color_enabled=False)
        progress = SimpleProgressBar(
            total=100,
            config=config,
            file=output,
        )

        # Update multiple times to cycle through spinner frames
        for i in range(len(SimpleProgressBar.SPINNER_FRAMES) + 1):
            progress.update(i)

        # Just verify spinner index changes
        assert progress.spinner_index > 0

    def test_custom_characters(self):
        """Test custom progress bar characters."""
        output = io.StringIO()
        config = ProgressBarConfig(
            filled_char="=",
            empty_char="-",
            left_bracket="(",
            right_bracket=")",
            color_enabled=False,
        )
        progress = SimpleProgressBar(
            total=100,
            description="Custom",
            config=config,
            file=output,
        )

        progress.update(50)
        result = output.getvalue()

        # Should contain custom characters
        assert "=" in result or "(" in result or ")" in result

    def test_no_color_mode(self):
        """Test progress bar without colors."""
        output = io.StringIO()
        config = ProgressBarConfig(color_enabled=False)
        progress = SimpleProgressBar(
            total=100,
            description="No Color",
            config=config,
            file=output,
        )

        progress.update(50)
        result = output.getvalue()

        # Should not contain ANSI codes
        assert "\033[" not in result


class TestProgressManager:
    """Test progress manager."""

    def test_creation(self):
        """Test progress manager creation."""
        manager = ProgressManager(description="Test", total=100)
        assert manager.description == "Test"
        assert manager.total == 100

    def test_context_manager(self):
        """Test progress manager as context manager."""
        with ProgressManager(description="Test", total=100) as manager:
            assert manager is not None
            manager.update(50)

    def test_update(self):
        """Test progress update."""
        with ProgressManager(description="Test", total=100) as manager:
            manager.update(50)
            # If Rich is available, it uses Rich, otherwise SimpleProgressBar
            # Just verify it doesn't crash

    def test_advance(self):
        """Test progress advance."""
        with ProgressManager(description="Test", total=100) as manager:
            manager.advance(10)
            manager.advance(5)
            # Verify it doesn't crash

    @pytest.mark.skipif(RICH_AVAILABLE, reason="Testing fallback mode")
    def test_fallback_to_simple(self):
        """Test that manager falls back to SimpleProgressBar when Rich unavailable."""
        manager = ProgressManager(description="Test", total=100)
        assert hasattr(manager, "_simple_progress")

    @pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
    def test_uses_rich_when_available(self):
        """Test that manager uses Rich when available."""
        manager = ProgressManager(description="Test", total=100)
        assert hasattr(manager, "_rich_progress")


class TestCreateProgressBar:
    """Test create_progress_bar convenience function."""

    def test_create_default(self):
        """Test creating progress bar with defaults."""
        progress = create_progress_bar()
        assert progress.description == ""
        assert progress.total == 100.0

    def test_create_custom(self):
        """Test creating progress bar with custom parameters."""
        progress = create_progress_bar(description="Custom", total=200)
        assert progress.description == "Custom"
        assert progress.total == 200

    def test_create_and_use(self):
        """Test creating and using progress bar."""
        with create_progress_bar("Test", 100) as progress:
            progress.update(50)
            progress.advance(25)
            # Verify it works without crashing
