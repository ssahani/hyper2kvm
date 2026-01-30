# SPDX-License-Identifier: LGPL-3.0-or-later
# tests/unit/test_cli.py
"""
Unit tests for CLI framework.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hyper2kvm.cli import (
    MigrationWizard,
    WizardResult,
    ProgressBar,
    Spinner,
    ProgressTracker,
    OutputFormatter,
    OutputStyle,
    Table,
    ConfigManager,
    MigrationConfig,
)


@pytest.fixture
def logger():
    """Create test logger."""
    return logging.getLogger("test")


# MigrationWizard Tests

def test_wizard_initialization(logger):
    """Test wizard initialization."""
    wizard = MigrationWizard(logger)

    assert wizard.logger == logger
    assert wizard._current_step == 0


def test_wizard_non_interactive_run(logger):
    """Test wizard in non-interactive mode."""
    wizard = MigrationWizard(logger)

    # Pre-configure wizard
    wizard._config = {
        "source_path": "/test/source.qcow2",
        "target_path": "/test/target.qcow2",
        "target_format": "qcow2",
        "readonly": True,
        "create_snapshot": True,
        "fix_bootloader": True,
        "fix_network": True,
        "stabilize_fstab": True,
        "run_validation": True,
        "validate_services": True,
        "validate_network": True,
        "validate_databases": True,
    }

    result = wizard.run(interactive=False)

    assert result.completed is True
    assert result.cancelled is False
    assert result.steps_completed == 5
    assert "source_path" in result.config


def test_wizard_get_config(logger):
    """Test getting wizard configuration."""
    wizard = MigrationWizard(logger)
    wizard._config = {"test_key": "test_value"}

    config = wizard.get_config()

    assert config["test_key"] == "test_value"
    # Verify it's a copy
    assert config is not wizard._config


# ProgressBar Tests

def test_progress_bar_initialization():
    """Test progress bar initialization."""
    bar = ProgressBar(total=100)

    assert bar.total == 100
    assert bar.current == 0
    assert bar.width == 40


def test_progress_bar_update():
    """Test progress bar update."""
    bar = ProgressBar(total=100)

    bar.update(current=50)
    assert bar.current == 50

    bar.update(increment=10)
    assert bar.current == 60


def test_progress_bar_completion():
    """Test progress bar completion."""
    bar = ProgressBar(total=10)

    for i in range(10):
        bar.update(increment=1)

    assert bar.current == 10


# Spinner Tests

def test_spinner_initialization():
    """Test spinner initialization."""
    spinner = Spinner("Loading")

    assert spinner.message == "Loading"
    assert spinner.is_running is False


def test_spinner_start_stop():
    """Test spinner start and stop."""
    spinner = Spinner("Test")

    spinner.start()
    assert spinner.is_running is True

    spinner.stop()
    assert spinner.is_running is False


def test_spinner_update():
    """Test spinner update."""
    spinner = Spinner("Test")
    spinner.start()

    initial_frame = spinner.current_frame
    spinner.update()

    # Frame should have advanced
    assert spinner.current_frame != initial_frame or len(spinner.frames) == 1

    spinner.stop()


# ProgressTracker Tests

def test_progress_tracker_initialization():
    """Test progress tracker initialization."""
    stages = ["Stage 1", "Stage 2", "Stage 3"]
    tracker = ProgressTracker(stages)

    assert tracker.stages == stages
    assert tracker.current_stage_idx == 0
    assert all(tracker.stage_progress[s] == 0.0 for s in stages)


def test_progress_tracker_start_stage():
    """Test starting a stage."""
    tracker = ProgressTracker(["Stage 1", "Stage 2"])

    tracker.start_stage("Stage 2")

    assert tracker.current_stage_idx == 1


def test_progress_tracker_update_stage():
    """Test updating stage progress."""
    tracker = ProgressTracker(["Stage 1"])

    tracker.update_stage("Stage 1", 50.0)

    assert tracker.stage_progress["Stage 1"] == 50.0


def test_progress_tracker_complete_stage():
    """Test completing a stage."""
    tracker = ProgressTracker(["Stage 1"])

    tracker.complete_stage("Stage 1")

    assert tracker.stage_progress["Stage 1"] == 100.0


def test_progress_tracker_overall_progress():
    """Test overall progress calculation."""
    tracker = ProgressTracker(["Stage 1", "Stage 2"])

    tracker.update_stage("Stage 1", 100.0)
    tracker.update_stage("Stage 2", 50.0)

    overall = tracker.get_overall_progress()

    assert overall == 75.0


def test_progress_tracker_eta():
    """Test ETA calculation."""
    tracker = ProgressTracker(["Stage 1"])

    # With 0% progress, ETA should be "Unknown"
    eta = tracker.get_eta()
    assert eta == "Unknown"


# OutputFormatter Tests

def test_formatter_initialization():
    """Test formatter initialization."""
    formatter = OutputFormatter(enable_colors=False)

    assert formatter.enable_colors is False


def test_formatter_format_message():
    """Test message formatting."""
    formatter = OutputFormatter(enable_colors=False)

    msg = formatter.format("Test message", OutputStyle.SUCCESS)

    # Without colors, should return unchanged
    assert msg == "Test message"


def test_formatter_print_success():
    """Test success message formatting."""
    formatter = OutputFormatter(enable_colors=False)

    # Should not raise exception
    formatter.print_success("Success message")


def test_formatter_print_error():
    """Test error message formatting."""
    formatter = OutputFormatter(enable_colors=False)

    formatter.print_error("Error message")


def test_formatter_print_warning():
    """Test warning message formatting."""
    formatter = OutputFormatter(enable_colors=False)

    formatter.print_warning("Warning message")


def test_formatter_print_info():
    """Test info message formatting."""
    formatter = OutputFormatter(enable_colors=False)

    formatter.print_info("Info message")


# Table Tests

def test_table_initialization():
    """Test table initialization."""
    table = Table(headers=["Col1", "Col2"])

    assert table.headers == ["Col1", "Col2"]
    assert len(table.rows) == 0


def test_table_add_row():
    """Test adding row to table."""
    table = Table(headers=["Col1", "Col2"])

    table.add_row(["Value1", "Value2"])

    assert len(table.rows) == 1
    assert table.rows[0] == ["Value1", "Value2"]


def test_table_render():
    """Test table rendering."""
    table = Table(headers=["Name", "Value"], title="Test Table")
    table.add_row(["Item1", "100"])
    table.add_row(["Item2", "200"])

    rendered = table.render()

    assert "Test Table" in rendered
    assert "Name" in rendered
    assert "Value" in rendered
    assert "Item1" in rendered
    assert "100" in rendered


# ConfigManager Tests

def test_config_manager_initialization(logger):
    """Test config manager initialization."""
    manager = ConfigManager(logger)

    assert manager.logger == logger


def test_config_manager_save_load_json(logger, tmp_path):
    """Test saving and loading JSON config."""
    manager = ConfigManager(logger)

    config = MigrationConfig(source_path="/test/source.qcow2")
    config_file = tmp_path / "config.json"

    manager.save_config(config, config_file, format="json")

    assert config_file.exists()

    loaded_config = manager.load_config(config_file)

    assert loaded_config.source_path == config.source_path
    assert loaded_config.readonly == config.readonly


def test_config_manager_create_default(logger):
    """Test creating default configuration."""
    manager = ConfigManager(logger)

    config = manager.create_default_config("/test/source.qcow2")

    assert config.source_path == "/test/source.qcow2"
    assert config.readonly is True
    assert config.fix_bootloader is True


def test_config_manager_validate_config(logger, tmp_path):
    """Test configuration validation."""
    manager = ConfigManager(logger)

    # Create test source file
    source_file = tmp_path / "source.qcow2"
    source_file.write_text("test")

    # Valid configuration
    valid_config = MigrationConfig(source_path=str(source_file))
    errors = manager.validate_config(valid_config)
    assert len(errors) == 0

    # Invalid configuration (missing source)
    invalid_config = MigrationConfig(source_path="")
    errors = manager.validate_config(invalid_config)
    assert len(errors) > 0


def test_config_manager_load_nonexistent(logger):
    """Test loading nonexistent configuration."""
    manager = ConfigManager(logger)

    with pytest.raises(FileNotFoundError):
        manager.load_config("/nonexistent/config.json")


# MigrationConfig Tests

def test_migration_config_to_dict():
    """Test config to dict conversion."""
    config = MigrationConfig(source_path="/test/source.qcow2")

    config_dict = config.to_dict()

    assert config_dict["source_path"] == "/test/source.qcow2"
    assert "readonly" in config_dict
    assert "fix_bootloader" in config_dict


def test_migration_config_from_dict():
    """Test config from dict creation."""
    data = {
        "source_path": "/test/source.qcow2",
        "target_path": "/test/target.qcow2",
        "readonly": False,
        "unknown_field": "ignored",  # Should be filtered out
    }

    config = MigrationConfig.from_dict(data)

    assert config.source_path == "/test/source.qcow2"
    assert config.target_path == "/test/target.qcow2"
    assert config.readonly is False
