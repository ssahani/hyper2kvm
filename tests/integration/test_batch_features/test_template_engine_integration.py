# SPDX-License-Identifier: LGPL-3.0-or-later
"""Integration tests for hook template engine."""

import json
import tempfile
from pathlib import Path

import pytest

from hyper2kvm.hooks.template_engine import (
    TemplateEngine,
    create_hook_context,
)


class TestTemplateEngineIntegration:
    """Integration tests for template engine in hook workflows."""

    def test_basic_variable_substitution(self):
        """Test basic variable substitution."""
        engine = TemplateEngine()

        template = "VM: {{ vm_name }}, Path: {{ output_path }}"
        variables = {
            "vm_name": "test-vm",
            "output_path": "/var/lib/vms/test.qcow2",
        }

        result = engine.substitute(template, variables)
        assert result == "VM: test-vm, Path: /var/lib/vms/test.qcow2"

    def test_multiple_occurrences(self):
        """Test variable used multiple times."""
        engine = TemplateEngine()

        template = "{{ vm_name }}: Starting conversion of {{ vm_name }}"
        variables = {"vm_name": "production-db"}

        result = engine.substitute(template, variables)
        assert result == "production-db: Starting conversion of production-db"

    def test_type_conversion(self):
        """Test automatic type conversion to string."""
        engine = TemplateEngine()

        template = "Port: {{ port }}, Size: {{ size_mb }}MB, Enabled: {{ enabled }}"
        variables = {
            "port": 8080,
            "size_mb": 4096,
            "enabled": True,
        }

        result = engine.substitute(template, variables)
        assert result == "Port: 8080, Size: 4096MB, Enabled: True"

    def test_missing_variables_non_strict(self):
        """Test missing variables in non-strict mode."""
        engine = TemplateEngine()

        template = "VM: {{ vm_name }}, Missing: {{ unknown }}"
        variables = {"vm_name": "test"}

        result = engine.substitute(template, variables)
        # Should leave {{ unknown }} as-is
        assert result == "VM: test, Missing: {{ unknown }}"

    def test_missing_variables_strict(self):
        """Test missing variables in strict mode raises error."""
        engine = TemplateEngine()

        template = "VM: {{ vm_name }}, Missing: {{ unknown }}"
        variables = {"vm_name": "test"}

        with pytest.raises(ValueError, match="Variable 'unknown' not found"):
            engine.substitute(template, variables, strict=True)

    def test_whitespace_in_placeholders(self):
        """Test placeholders with various whitespace."""
        engine = TemplateEngine()

        template = "{{vm_name}} - {{ vm_name }} - {{  vm_name  }}"
        variables = {"vm_name": "test"}

        result = engine.substitute(template, variables)
        assert result == "test - test - test"

    def test_nested_data_structures(self):
        """Test substitution with complex data structures."""
        engine = TemplateEngine()

        template = "List: {{ items }}, Dict: {{ config }}"
        variables = {
            "items": ["a", "b", "c"],
            "config": {"key": "value"},
        }

        result = engine.substitute(template, variables)
        assert "['a', 'b', 'c']" in result
        assert "{'key': 'value'}" in result

    def test_special_characters_in_values(self):
        """Test values with special characters."""
        engine = TemplateEngine()

        template = "Path: {{ path }}"
        variables = {"path": "/tmp/test-vm_123/disk.qcow2"}

        result = engine.substitute(template, variables)
        assert result == "Path: /tmp/test-vm_123/disk.qcow2"

    def test_empty_template(self):
        """Test empty template."""
        engine = TemplateEngine()

        result = engine.substitute("", {"vm_name": "test"})
        assert result == ""

    def test_no_placeholders(self):
        """Test template without placeholders."""
        engine = TemplateEngine()

        template = "This is a static string"
        result = engine.substitute(template, {"vm_name": "test"})
        assert result == template

    def test_substitute_dict(self):
        """Test substituting all strings in a dictionary."""
        engine = TemplateEngine()

        template_dict = {
            "name": "{{ vm_name }}",
            "path": "/vms/{{ vm_name }}/disk.qcow2",
            "size": "{{ size_gb }}GB",
            "static": "no placeholders",
        }

        variables = {
            "vm_name": "test-vm",
            "size_gb": 100,
        }

        result = engine.substitute_dict(template_dict, variables)

        assert result["name"] == "test-vm"
        assert result["path"] == "/vms/test-vm/disk.qcow2"
        assert result["size"] == "100GB"
        assert result["static"] == "no placeholders"

    def test_substitute_list(self):
        """Test substituting all strings in a list."""
        engine = TemplateEngine()

        template_list = [
            "{{ vm_name }}",
            "/path/{{ vm_name }}",
            "static",
            123,
        ]

        variables = {"vm_name": "test"}

        result = engine.substitute_list(template_list, variables)

        assert result[0] == "test"
        assert result[1] == "/path/test"
        assert result[2] == "static"
        assert result[3] == 123

    def test_substitute_nested_structures(self):
        """Test substitution in nested data structures."""
        engine = TemplateEngine()

        template = {
            "vm": {
                "name": "{{ vm_name }}",
                "disks": [
                    "/disk1/{{ vm_name }}.qcow2",
                    "/disk2/{{ vm_name }}.qcow2",
                ],
            },
            "metadata": {
                "owner": "{{ owner }}",
                "tags": ["{{ env }}", "automated"],
            },
        }

        variables = {
            "vm_name": "production-db",
            "owner": "admin",
            "env": "production",
        }

        result = engine.substitute_dict(template, variables)

        assert result["vm"]["name"] == "production-db"
        assert result["vm"]["disks"][0] == "/disk1/production-db.qcow2"
        assert result["vm"]["disks"][1] == "/disk2/production-db.qcow2"
        assert result["metadata"]["owner"] == "admin"
        assert result["metadata"]["tags"][0] == "production"


class TestHookContextCreation:
    """Test creating hook execution context."""

    def test_create_basic_context(self, tmp_path):
        """Test creating basic hook context."""
        manifest = {
            "source": {
                "vm_name": "test-vm",
                "vm_id": "vm-123",
            },
            "disks": [
                {
                    "id": "boot",
                    "local_path": str(tmp_path / "disk.qcow2"),
                    "bytes": 10737418240,
                }
            ],
        }

        context = create_hook_context(manifest)

        assert context["vm_name"] == "test-vm"
        assert context["vm_id"] == "vm-123"
        assert "timestamp" in context
        assert "timestamp_iso" in context

    def test_create_context_with_output(self, tmp_path):
        """Test creating context with output information."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        manifest = {
            "source": {"vm_name": "test-vm"},
            "output": {
                "directory": str(output_dir),
                "format": "qcow2",
            },
        }

        context = create_hook_context(
            manifest,
            output_path=str(output_dir / "converted.qcow2"),
        )

        assert context["output_directory"] == str(output_dir)
        assert context["output_format"] == "qcow2"
        assert context["output_path"] == str(output_dir / "converted.qcow2")

    def test_create_context_with_custom_vars(self):
        """Test creating context with custom variables."""
        manifest = {"source": {"vm_name": "test-vm"}}

        custom_vars = {
            "backup_path": "/backups/test-vm",
            "notification_email": "admin@example.com",
        }

        context = create_hook_context(manifest, **custom_vars)

        assert context["vm_name"] == "test-vm"
        assert context["backup_path"] == "/backups/test-vm"
        assert context["notification_email"] == "admin@example.com"

    def test_context_with_disk_info(self, tmp_path):
        """Test context includes disk information."""
        disk_path = tmp_path / "disk.qcow2"
        disk_path.write_bytes(b"\x00" * 1024)

        manifest = {
            "source": {"vm_name": "test-vm"},
            "disks": [
                {
                    "id": "boot",
                    "local_path": str(disk_path),
                    "bytes": 1024,
                    "source_format": "vmdk",
                }
            ],
        }

        context = create_hook_context(manifest)

        assert "source_path" in context
        # First disk becomes source_path
        assert context["source_path"] == str(disk_path)


class TestTemplateEngineInHooks:
    """Test template engine integration with actual hooks."""

    def test_script_hook_with_templates(self, tmp_path):
        """Test script hook using template variables."""
        # Create test script
        script = tmp_path / "hook.sh"
        script.write_text(
            """#!/bin/bash
echo "Processing VM: $1"
echo "Output: $2"
"""
        )
        script.chmod(0o755)

        engine = TemplateEngine()

        # Hook configuration with templates
        hook_config = {
            "type": "script",
            "path": str(script),
            "args": [
                "{{ vm_name }}",
                "{{ output_path }}",
            ],
        }

        variables = {
            "vm_name": "production-db",
            "output_path": "/vms/production-db.qcow2",
        }

        # Substitute templates in args
        substituted_args = engine.substitute_list(
            hook_config["args"], variables
        )

        assert substituted_args[0] == "production-db"
        assert substituted_args[1] == "/vms/production-db.qcow2"

    def test_http_hook_with_templates(self):
        """Test HTTP hook with templated body."""
        engine = TemplateEngine()

        hook_config = {
            "type": "http",
            "url": "https://api.example.com/webhooks",
            "method": "POST",
            "body": {
                "vm_name": "{{ vm_name }}",
                "status": "{{ status }}",
                "output_path": "{{ output_path }}",
                "timestamp": "{{ timestamp_iso }}",
            },
        }

        variables = {
            "vm_name": "test-vm",
            "status": "completed",
            "output_path": "/vms/test.qcow2",
            "timestamp_iso": "2026-01-23T10:00:00Z",
        }

        substituted_body = engine.substitute_dict(
            hook_config["body"], variables
        )

        assert substituted_body["vm_name"] == "test-vm"
        assert substituted_body["status"] == "completed"
        assert substituted_body["output_path"] == "/vms/test.qcow2"
        assert substituted_body["timestamp"] == "2026-01-23T10:00:00Z"

    def test_hook_env_vars_with_templates(self):
        """Test hook environment variables with templates."""
        engine = TemplateEngine()

        hook_config = {
            "type": "script",
            "path": "/hook.sh",
            "env": {
                "VM_NAME": "{{ vm_name }}",
                "VM_ID": "{{ vm_id }}",
                "OUTPUT_DIR": "{{ output_directory }}",
                "BACKUP_ENABLED": "{{ backup_enabled }}",
            },
        }

        variables = {
            "vm_name": "web-server",
            "vm_id": "vm-456",
            "output_directory": "/vms/output",
            "backup_enabled": True,
        }

        substituted_env = engine.substitute_dict(
            hook_config["env"], variables
        )

        assert substituted_env["VM_NAME"] == "web-server"
        assert substituted_env["VM_ID"] == "vm-456"
        assert substituted_env["OUTPUT_DIR"] == "/vms/output"
        assert substituted_env["BACKUP_ENABLED"] == "True"


class TestTemplateEngineEdgeCases:
    """Test edge cases and error handling."""

    def test_malformed_placeholder(self):
        """Test malformed placeholder syntax."""
        engine = TemplateEngine()

        # Missing closing braces
        template = "{{ vm_name"
        result = engine.substitute(template, {"vm_name": "test"})
        # Should leave as-is (no match)
        assert result == "{{ vm_name"

        # Single braces
        template2 = "{ vm_name }"
        result2 = engine.substitute(template2, {"vm_name": "test"})
        assert result2 == "{ vm_name }"

    def test_none_value(self):
        """Test None value substitution."""
        engine = TemplateEngine()

        template = "Value: {{ value }}"
        variables = {"value": None}

        result = engine.substitute(template, variables)
        assert result == "Value: None"

    def test_empty_variable_name(self):
        """Test empty variable name in placeholder."""
        engine = TemplateEngine()

        template = "{{  }}"
        result = engine.substitute(template, {"test": "value"})
        # Should not match (empty name)
        assert result == "{{  }}"

    def test_unicode_in_values(self):
        """Test Unicode characters in values."""
        engine = TemplateEngine()

        template = "Name: {{ name }}"
        variables = {"name": "测试虚拟机"}

        result = engine.substitute(template, variables)
        assert result == "Name: 测试虚拟机"

    def test_numeric_strings(self):
        """Test numeric strings as variable names."""
        engine = TemplateEngine()

        # Variable names can't start with numbers in the regex
        template = "{{ var123 }}"
        variables = {"var123": "value"}

        result = engine.substitute(template, variables)
        assert result == "value"

    def test_case_sensitivity(self):
        """Test variable names are case-sensitive."""
        engine = TemplateEngine()

        template = "{{ VM_NAME }} vs {{ vm_name }}"
        variables = {
            "VM_NAME": "UPPERCASE",
            "vm_name": "lowercase",
        }

        result = engine.substitute(template, variables)
        assert result == "UPPERCASE vs lowercase"

    def test_large_template(self):
        """Test performance with large template."""
        engine = TemplateEngine()

        # Generate large template
        parts = []
        for i in range(100):
            parts.append(f"VM {i}: {{{{ vm_name }}}} at {{{{ path_{i} }}}}")

        template = "\n".join(parts)

        variables = {"vm_name": "test"}
        # Add path variables
        for i in range(100):
            variables[f"path_{i}"] = f"/vms/path{i}"

        result = engine.substitute(template, variables)

        # Should have all substitutions
        assert "{{ vm_name }}" not in result
        assert result.count("test") == 100

    def test_concurrent_substitution(self):
        """Test thread safety of template engine."""
        import threading

        engine = TemplateEngine()
        results = []

        def substitute_worker(vm_id):
            template = "VM: {{ vm_name }}"
            variables = {"vm_name": f"vm-{vm_id}"}
            result = engine.substitute(template, variables)
            results.append(result)

        threads = [
            threading.Thread(target=substitute_worker, args=(i,))
            for i in range(20)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All substitutions should be correct
        assert len(results) == 20
        assert all(r.startswith("VM: vm-") for r in results)

    def test_json_serialization_after_substitution(self):
        """Test that substituted dictionaries remain JSON-serializable."""
        engine = TemplateEngine()

        template_dict = {
            "vm_name": "{{ vm_name }}",
            "metadata": {
                "created": "{{ timestamp_iso }}",
                "size": "{{ size_gb }}",
            },
        }

        variables = {
            "vm_name": "test",
            "timestamp_iso": "2026-01-23T10:00:00Z",
            "size_gb": 100,
        }

        result = engine.substitute_dict(template_dict, variables)

        # Should be JSON-serializable
        json_str = json.dumps(result)
        assert json_str is not None

        # Verify deserialized data
        parsed = json.loads(json_str)
        assert parsed["vm_name"] == "test"
        assert parsed["metadata"]["size"] == "100"
