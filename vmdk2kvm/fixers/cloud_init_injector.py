# ---------------------------------------------------------------------
# cloud-init injection (minimal + safe)
# ---------------------------------------------------------------------

from typing import Dict, Any
import os
import yaml
import json
import guestfs

# Ensure all required imports are present
# Define the inject_cloud_init method
def inject_cloud_init(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    if not self.inject_cloud_init_data:
        return {"injected": False, "reason": "no_data"}

    cloud_dir = "/etc/cloud"
    try:
        cloud_installed = g.is_dir(cloud_dir)
    except Exception:
        cloud_installed = False

    if not cloud_installed:
        self.logger.info("Cloud-init not detected in guest")
        if self.inject_cloud_init_data.get("install_if_missing", False) and not self.dry_run:
            try:
                for pm_cmd in (["apt-get", "install", "-y"], ["dnf", "install", "-y"], ["yum", "install", "-y"], ["zypper", "install", "-y"]):
                    if guest_has_cmd(g, pm_cmd[0]):
                        g.command(pm_cmd + ["cloud-init"])
                        cloud_installed = True
                        self.logger.info("Installed cloud-init in guest")
                        break
            except Exception as e:
                self.logger.warning(f"Failed to install cloud-init: {e}")

    if not cloud_installed:
        return {"injected": False, "reason": "cloud_init_not_available"}

    cloud_config = self.inject_cloud_init_data.get("config", {})
    if not cloud_config:
        return {"injected": False, "reason": "empty_config"}

    try:
        if not g.is_dir(cloud_dir):
            if not self.dry_run:
                g.mkdir_p(cloud_dir)

        cloud_cfg_path = os.path.join(cloud_dir, "cloud.cfg")
        if YAML_AVAILABLE:
            rendered = yaml.safe_dump(cloud_config, sort_keys=False)
        else:
            rendered = json.dumps(cloud_config, indent=2)

        if self.dry_run:
            self.logger.info(f"DRY-RUN: would inject cloud-init configuration: {cloud_cfg_path}")
            return {"injected": True, "dry_run": True, "path": cloud_cfg_path}

        self.backup_file(g, cloud_cfg_path)
        g.write(cloud_cfg_path, rendered.encode("utf-8"))
        self.logger.info(f"Injected cloud-init configuration: {cloud_cfg_path}")
        return {"injected": True, "path": cloud_cfg_path}
    except Exception as e:
        self.logger.warning(f"Failed to inject cloud-init: {e}")
        return {"injected": False, "reason": str(e)}

# Define YAML_AVAILABLE as a placeholder for YAML library availability
YAML_AVAILABLE = True

# Define guest_has_cmd as a placeholder function
def guest_has_cmd(g, cmd):
    # Placeholder implementation
    return True
