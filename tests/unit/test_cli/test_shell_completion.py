# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit tests for shell completion functionality.

Tests the integration of argcomplete with the hyper2kvm CLI parser.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestShellCompletion:
    """Test shell completion integration."""

    def test_argcomplete_integration(self):
        """Test that argcomplete integrates correctly with the parser."""
        try:
            import argcomplete
        except ImportError:
            pytest.skip("argcomplete not installed")

        from hyper2kvm.cli.args.parser import build_parser

        parser = build_parser()

        # This should not raise an exception
        # Use exit_method to prevent actual exit during testing
        argcomplete.autocomplete(parser, exit_method=lambda x: None)

    def test_parser_without_argcomplete(self, monkeypatch):
        """Test that parser works gracefully without argcomplete."""
        # Simulate argcomplete not being installed
        import sys

        # Remove argcomplete from sys.modules if it exists
        if "argcomplete" in sys.modules:
            monkeypatch.delitem(sys.modules, "argcomplete")

        # Make import fail
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "argcomplete":
                raise ImportError("argcomplete not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        # Parser should still build successfully
        from hyper2kvm.cli.args.parser import build_parser

        parser = build_parser()
        assert parser is not None

    def test_completion_files_exist(self):
        """Test that all completion files exist."""
        repo_root = Path(__file__).parent.parent.parent.parent
        completions_dir = repo_root / "completions"

        assert completions_dir.exists(), "completions directory should exist"
        assert (completions_dir / "hyper2kvm.bash").exists(), "bash completion should exist"
        assert (completions_dir / "hyper2kvm.zsh").exists(), "zsh completion should exist"
        assert (completions_dir / "hyper2kvm.fish").exists(), "fish completion should exist"
        assert (
            completions_dir / "install-completions.sh"
        ).exists(), "installation script should exist"
        assert (completions_dir / "README.md").exists(), "completion README should exist"

    def test_installation_script_executable(self):
        """Test that the installation script is executable."""
        repo_root = Path(__file__).parent.parent.parent.parent
        install_script = repo_root / "completions" / "install-completions.sh"

        assert install_script.exists(), "installation script should exist"
        assert install_script.stat().st_mode & 0o111, "installation script should be executable"

    def test_bash_completion_syntax(self):
        """Test that bash completion script has valid syntax."""
        repo_root = Path(__file__).parent.parent.parent.parent
        bash_completion = repo_root / "completions" / "hyper2kvm.bash"

        assert bash_completion.exists(), "bash completion should exist"

        # Test syntax using bash -n
        result = subprocess.run(
            ["bash", "-n", str(bash_completion)], capture_output=True, text=True, timeout=5
        )

        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_fish_completion_syntax(self):
        """Test that fish completion script has valid syntax."""
        repo_root = Path(__file__).parent.parent.parent.parent
        fish_completion = repo_root / "completions" / "hyper2kvm.fish"

        assert fish_completion.exists(), "fish completion should exist"

        # Test syntax using fish -n (if fish is installed)
        try:
            result = subprocess.run(
                ["fish", "-n", str(fish_completion)], capture_output=True, text=True, timeout=5
            )
            assert result.returncode == 0, f"Fish syntax error: {result.stderr}"
        except FileNotFoundError:
            pytest.skip("fish shell not installed")

    def test_installation_script_syntax(self):
        """Test that the installation script has valid bash syntax."""
        repo_root = Path(__file__).parent.parent.parent.parent
        install_script = repo_root / "completions" / "install-completions.sh"

        assert install_script.exists(), "installation script should exist"

        # Test syntax using bash -n
        result = subprocess.run(
            ["bash", "-n", str(install_script)], capture_output=True, text=True, timeout=5
        )

        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_completion_files_content(self):
        """Test that completion files contain expected content."""
        repo_root = Path(__file__).parent.parent.parent.parent
        completions_dir = repo_root / "completions"

        # Test bash completion
        bash_content = (completions_dir / "hyper2kvm.bash").read_text()
        assert "register-python-argcomplete" in bash_content
        assert "hyper2kvm" in bash_content

        # Test zsh completion
        zsh_content = (completions_dir / "hyper2kvm.zsh").read_text()
        assert "register-python-argcomplete" in zsh_content
        assert "hyper2kvm" in zsh_content
        assert "bashcompinit" in zsh_content

        # Test fish completion
        fish_content = (completions_dir / "hyper2kvm.fish").read_text()
        assert "register-python-argcomplete" in fish_content
        assert "hyper2kvm" in fish_content
        assert "fish" in fish_content

    def test_readme_exists_and_contains_info(self):
        """Test that completion README exists and contains useful information."""
        repo_root = Path(__file__).parent.parent.parent.parent
        readme = repo_root / "completions" / "README.md"

        assert readme.exists(), "completion README should exist"

        content = readme.read_text()
        assert "Shell Completion" in content
        assert "bash" in content.lower()
        assert "zsh" in content.lower()
        assert "fish" in content.lower()
        assert "argcomplete" in content.lower()
        assert "installation" in content.lower()

    def test_manifest_includes_completion_files(self):
        """Test that MANIFEST.in includes completion files."""
        repo_root = Path(__file__).parent.parent.parent.parent
        manifest = repo_root / "MANIFEST.in"

        assert manifest.exists(), "MANIFEST.in should exist"

        content = manifest.read_text()
        assert "completions" in content.lower()
        assert any(ext in content for ext in [".bash", ".zsh", ".fish", ".sh"])

    def test_pyproject_includes_argcomplete(self):
        """Test that pyproject.toml includes argcomplete dependency."""
        repo_root = Path(__file__).parent.parent.parent.parent
        pyproject = repo_root / "pyproject.toml"

        assert pyproject.exists(), "pyproject.toml should exist"

        content = pyproject.read_text()
        assert "argcomplete" in content


class TestCompletionDocumentation:
    """Test that documentation includes completion information."""

    def test_main_readme_has_completion_section(self):
        """Test that main README has shell completion section."""
        repo_root = Path(__file__).parent.parent.parent.parent
        readme = repo_root / "README.md"

        assert readme.exists(), "README.md should exist"

        content = readme.read_text()
        assert "Shell Completion" in content
        assert "argcomplete" in content
        assert "completions" in content.lower()

    def test_installation_docs_have_completion_section(self):
        """Test that installation docs have shell completion section."""
        repo_root = Path(__file__).parent.parent.parent.parent
        install_docs = repo_root / "docs" / "02-Installation.md"

        if install_docs.exists():
            content = install_docs.read_text()
            assert "Shell Completion" in content or "completion" in content.lower()
            assert "argcomplete" in content or "bash" in content.lower()
