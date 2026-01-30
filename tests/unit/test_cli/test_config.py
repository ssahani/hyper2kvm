# SPDX-License-Identifier: LGPL-3.0-or-later
"""
Unit Tests for CLI Configuration Loading

Tests YAML/JSON configuration file loading, merging, and two-phase parsing.
"""

import unittest
import tempfile
import os
import yaml
import json
from pathlib import Path

from hyper2kvm.cli.argument_parser import parse_args_with_config


class TestCLIConfigTwoPhaseParse(unittest.TestCase):
    """Test two-phase config parsing (config files + CLI args)"""

    def test_config_satisfies_required_vmdk(self):
        """Test that config file can satisfy required --vmdk argument"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vmdk = td / "vm.vmdk"
            vmdk.write_bytes(b"dummy")
            cfg = td / "cfg.yaml"
            cfg.write_text(f"vmdk: {vmdk}\n", encoding="utf-8")

            # This would fail if argparse enforces --vmdk before config defaults are applied.
            args, conf, _logger = parse_args_with_config(argv=["--config", str(cfg), "local"])

            self.assertEqual(Path(args.vmdk), vmdk)
            self.assertIn("vmdk", conf)

    def test_cli_args_override_config(self):
        """Test that CLI arguments override config file values"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vmdk = td / "vm.vmdk"
            vmdk.write_bytes(b"dummy")
            cfg = td / "cfg.yaml"
            cfg.write_text(f"""
vmdk: {vmdk}
compress: false
flatten: false
""", encoding="utf-8")

            # CLI args should override config
            args, conf, _logger = parse_args_with_config(
                argv=["--config", str(cfg), "local", "--compress", "--flatten"]
            )

            # CLI overrides
            self.assertTrue(args.compress)
            self.assertTrue(args.flatten)

    def test_multiple_config_files_merge(self):
        """Test merging multiple config files (later overrides earlier)"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vmdk = td / "vm.vmdk"
            vmdk.write_bytes(b"dummy")

            # Base config
            cfg1 = td / "base.yaml"
            cfg1.write_text(f"""
vmdk: {vmdk}
compress: false
log_level: INFO
""", encoding="utf-8")

            # Override config
            cfg2 = td / "override.yaml"
            cfg2.write_text("""
compress: true
log_level: DEBUG
""", encoding="utf-8")

            args, conf, _logger = parse_args_with_config(
                argv=["--config", str(cfg1), "--config", str(cfg2), "local"]
            )

            # Second config should override first
            self.assertTrue(args.compress)

    def test_json_config_format(self):
        """Test loading JSON format config files"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vmdk = td / "vm.vmdk"
            vmdk.write_bytes(b"dummy")
            cfg = td / "cfg.json"

            config_data = {
                "vmdk": str(vmdk),
                "compress": True,
                "flatten": True
            }
            cfg.write_text(json.dumps(config_data), encoding="utf-8")

            args, conf, _logger = parse_args_with_config(
                argv=["--config", str(cfg), "local"]
            )

            self.assertEqual(Path(args.vmdk), vmdk)
            self.assertTrue(args.compress)


class TestConfigFileFormats(unittest.TestCase):
    """Test different configuration file formats"""

    def test_yaml_with_nested_objects(self):
        """Test YAML config with nested objects"""
        config_str = """
cmd: vsphere
vcenter: vcenter.example.com
libvirt_config:
  memory_mb: 8192
  vcpus: 4
  disk_bus: virtio
"""
        config = yaml.safe_load(config_str)

        self.assertEqual(config["libvirt_config"]["memory_mb"], 8192)
        self.assertEqual(config["libvirt_config"]["vcpus"], 4)

    def test_yaml_with_lists(self):
        """Test YAML config with list values"""
        config_str = """
vm_names:
  - vm1
  - vm2
  - vm3
fix_options:
  - fix_fstab
  - fix_grub
"""
        config = yaml.safe_load(config_str)

        self.assertEqual(len(config["vm_names"]), 3)
        self.assertIn("vm2", config["vm_names"])

    def test_yaml_multiline_strings(self):
        """Test YAML config with multiline strings (scripts)"""
        config_str = """
post_migration_script: |
  #!/bin/bash
  set -e
  virsh define vm.xml
  virsh start vm
"""
        config = yaml.safe_load(config_str)

        self.assertIn("#!/bin/bash", config["post_migration_script"])
        self.assertIn("virsh", config["post_migration_script"])

    def test_json_nested_objects(self):
        """Test JSON config with nested objects"""
        config_str = """
{
  "cmd": "vsphere",
  "vcenter": "vcenter.example.com",
  "network_config": {
    "type": "bridge",
    "bridge": "br0"
  }
}
"""
        config = json.loads(config_str)

        self.assertEqual(config["network_config"]["type"], "bridge")
        self.assertEqual(config["network_config"]["bridge"], "br0")

    def test_boolean_values(self):
        """Test boolean configuration values"""
        config_str = """
flatten: true
compress: false
dry_run: true
"""
        config = yaml.safe_load(config_str)

        self.assertTrue(config["flatten"])
        self.assertFalse(config["compress"])
        self.assertTrue(config["dry_run"])


if __name__ == "__main__":
    unittest.main()
