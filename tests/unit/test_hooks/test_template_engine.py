# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for template engine."""

import pytest

from hyper2kvm.hooks.template_engine import TemplateEngine, create_hook_context


class TestTemplateEngine:
    """Test TemplateEngine functionality."""

    def test_simple_substitution(self):
        """Test basic variable substitution."""
        engine = TemplateEngine()
        template = "Hello {{ name }}, welcome to {{ place }}!"
        variables = {"name": "World", "place": "Earth"}

        result = engine.substitute(template, variables)
        assert result == "Hello World, welcome to Earth!"

    def test_substitution_with_whitespace(self):
        """Test that whitespace around variable names is handled."""
        engine = TemplateEngine()
        template = "{{ var1 }} and {{var2}} and {{  var3  }}"
        variables = {"var1": "A", "var2": "B", "var3": "C"}

        result = engine.substitute(template, variables)
        assert result == "A and B and C"

    def test_missing_variable_strict_mode(self):
        """Test that missing variable raises error in strict mode."""
        engine = TemplateEngine()
        template = "Value: {{ missing }}"
        variables = {}

        with pytest.raises(ValueError, match="Variable 'missing' not found"):
            engine.substitute(template, variables, strict=True)

    def test_missing_variable_non_strict(self):
        """Test that missing variable is left as-is in non-strict mode."""
        engine = TemplateEngine()
        template = "Value: {{ missing }}"
        variables = {}

        result = engine.substitute(template, variables, strict=False)
        assert result == "Value: {{ missing }}"

    def test_none_value_substitution(self):
        """Test that None values are replaced with empty string."""
        engine = TemplateEngine()
        template = "Value: {{ value }}"
        variables = {"value": None}

        result = engine.substitute(template, variables)
        assert result == "Value: "

    def test_numeric_value_conversion(self):
        """Test that numeric values are converted to strings."""
        engine = TemplateEngine()
        template = "Port: {{ port }}, Count: {{ count }}"
        variables = {"port": 8080, "count": 42}

        result = engine.substitute(template, variables)
        assert result == "Port: 8080, Count: 42"

    def test_boolean_value_conversion(self):
        """Test that boolean values are converted to strings."""
        engine = TemplateEngine()
        template = "Enabled: {{ enabled }}, Debug: {{ debug }}"
        variables = {"enabled": True, "debug": False}

        result = engine.substitute(template, variables)
        assert result == "Enabled: True, Debug: False"

    def test_substitute_dict(self):
        """Test substituting variables in a dictionary."""
        engine = TemplateEngine()
        template_dict = {
            "name": "{{ vm_name }}",
            "path": "/data/{{ vm_name }}/disk.qcow2",
            "count": "{{ count }}",
        }
        variables = {"vm_name": "test-vm", "count": 5}

        result = engine.substitute_dict(template_dict, variables)

        assert result["name"] == "test-vm"
        assert result["path"] == "/data/test-vm/disk.qcow2"
        assert result["count"] == "5"

    def test_substitute_dict_nested(self):
        """Test substituting in nested dictionaries."""
        engine = TemplateEngine()
        template_dict = {
            "server": {
                "host": "{{ hostname }}",
                "port": "{{ port }}",
            },
            "database": {
                "name": "{{ db_name }}",
            },
        }
        variables = {"hostname": "localhost", "port": 5432, "db_name": "testdb"}

        result = engine.substitute_dict(template_dict, variables)

        assert result["server"]["host"] == "localhost"
        assert result["server"]["port"] == "5432"
        assert result["database"]["name"] == "testdb"

    def test_substitute_dict_with_lists(self):
        """Test substituting in dictionaries containing lists."""
        engine = TemplateEngine()
        template_dict = {
            "args": ["{{ arg1 }}", "{{ arg2 }}", "static"],
            "count": 3,
        }
        variables = {"arg1": "first", "arg2": "second"}

        result = engine.substitute_dict(template_dict, variables)

        assert result["args"] == ["first", "second", "static"]
        assert result["count"] == 3

    def test_substitute_dict_non_string_values(self):
        """Test that non-string values in dict are preserved."""
        engine = TemplateEngine()
        template_dict = {
            "text": "{{ value }}",
            "number": 42,
            "flag": True,
            "none": None,
        }
        variables = {"value": "test"}

        result = engine.substitute_dict(template_dict, variables)

        assert result["text"] == "test"
        assert result["number"] == 42
        assert result["flag"] is True
        assert result["none"] is None

    def test_extract_variables(self):
        """Test extracting variable names from template."""
        engine = TemplateEngine()
        template = "{{ var1 }} and {{ var2 }} and {{ var1 }} again"

        variables = engine.extract_variables(template)

        assert set(variables) == {"var1", "var2"}

    def test_extract_variables_no_duplicates(self):
        """Test that extract_variables returns unique names."""
        engine = TemplateEngine()
        template = "{{ name }} {{ name }} {{ name }}"

        variables = engine.extract_variables(template)

        assert variables == ["name"]

    def test_extract_variables_empty_template(self):
        """Test extracting from template with no variables."""
        engine = TemplateEngine()
        template = "This template has no variables"

        variables = engine.extract_variables(template)

        assert variables == []

    def test_validate_template_all_present(self):
        """Test template validation when all required vars present."""
        engine = TemplateEngine()
        template = "{{ var1 }} and {{ var2 }}"
        required = ["var1", "var2"]

        is_valid, missing = engine.validate_template(template, required)

        assert is_valid is True
        assert missing == []

    def test_validate_template_missing_vars(self):
        """Test template validation when required vars missing."""
        engine = TemplateEngine()
        template = "{{ var1 }}"
        required = ["var1", "var2", "var3"]

        is_valid, missing = engine.validate_template(template, required)

        assert is_valid is False
        assert set(missing) == {"var2", "var3"}

    def test_validate_template_extra_vars_ok(self):
        """Test that extra variables in template don't fail validation."""
        engine = TemplateEngine()
        template = "{{ var1 }} and {{ var2 }} and {{ var3 }}"
        required = ["var1", "var2"]

        is_valid, missing = engine.validate_template(template, required)

        assert is_valid is True
        assert missing == []


class TestCreateHookContext:
    """Test create_hook_context function."""

    def test_create_basic_context(self):
        """Test creating basic hook context."""
        context = create_hook_context(
            stage="pre_fix",
            vm_name="test-vm",
            source_path="/data/vm.vmdk",
            output_path="/converted/vm.qcow2",
        )

        assert context["stage"] == "pre_fix"
        assert context["vm_name"] == "test-vm"
        assert context["source_path"] == "/data/vm.vmdk"
        assert context["output_path"] == "/converted/vm.qcow2"

    def test_context_has_timestamps(self):
        """Test that context includes timestamp fields."""
        context = create_hook_context(stage="test")

        assert "timestamp" in context
        assert "timestamp_iso" in context
        assert isinstance(context["timestamp"], int)
        assert isinstance(context["timestamp_iso"], str)

    def test_context_has_environment_vars(self):
        """Test that context includes environment variables."""
        context = create_hook_context(stage="test")

        assert "user" in context
        assert "hostname" in context
        assert "pwd" in context

    def test_context_derived_path_fields(self):
        """Test that derived path fields are created."""
        context = create_hook_context(
            stage="test",
            source_path="/data/vms/test-vm/boot.vmdk",
            output_path="/converted/test-vm/boot.qcow2",
        )

        assert context["source_dir"] == "/data/vms/test-vm"
        assert context["source_filename"] == "boot.vmdk"
        assert context["output_dir"] == "/converted/test-vm"
        assert context["output_filename"] == "boot.qcow2"

    def test_context_extra_variables(self):
        """Test adding extra variables to context."""
        context = create_hook_context(
            stage="test",
            vm_name="test",
            custom_var="custom_value",
            another_var=123,
        )

        assert context["custom_var"] == "custom_value"
        assert context["another_var"] == 123

    def test_context_defaults_for_missing_paths(self):
        """Test that missing paths result in empty strings."""
        context = create_hook_context(stage="test")

        assert context["vm_name"] == "unknown"
        assert context["source_path"] == ""
        assert context["output_path"] == ""
        assert context["source_dir"] == "."
        assert context["source_filename"] == ""
