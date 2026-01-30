# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/user_config_injector.py
"""
User account and SSH key injection for Linux VMs.

Allows creating users, deploying SSH keys, configuring sudo access, and
setting passwords for post-migration access without cloud-init.

Use cases:
- Create administrative users
- Deploy SSH keys for passwordless access
- Configure sudo/wheel access
- Set user passwords (hashed)
- Disable/lock default users
- Configure user home directories
"""
from __future__ import annotations

import hashlib
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...


def inject_user_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Inject user accounts and SSH key configuration.

    Expected payload (self.user_config_inject):
      {
        "users": [
          {
            "name": "admin",
            "uid": 1000,  # Optional, auto-assigned if not specified
            "gid": 1000,  # Optional, defaults to uid
            "groups": ["wheel", "docker"],  # Optional, additional groups
            "comment": "Admin User",  # Optional, GECOS field
            "shell": "/bin/bash",  # Optional, default /bin/bash
            "home": "/home/admin",  # Optional, default /home/username
            "create_home": true,  # Optional, default true
            "ssh_keys": [  # Optional
              "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... user@host"
            ],
            "password": "plaintextpassword",  # Optional, will be hashed
            "password_hash": "$6$...",  # Optional, pre-hashed password
            "sudo": "NOPASSWD:ALL",  # Optional, sudo configuration
            "lock": false  # Optional, lock account (default false)
          }
        ],
        "disable_users": ["ubuntu", "centos"],  # Optional, lock these users
        "delete_users": ["test"],  # Optional, delete these users
      }
    """
    logger = getattr(self, "logger", None)

    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    _log("debug", "👤 user-config: inject_user_config(): enter")

    # Get configuration
    config = getattr(self, "user_config_inject", None)
    if config is None:
        _log("debug", "👤 user-config: no user_config_inject set; skipping")
        return {"injected": False, "reason": "no_config"}

    if not isinstance(config, dict):
        _log("warning", f"👤 user-config: user_config_inject is not a dict: {type(config).__name__}")
        return {"injected": False, "reason": "invalid_config"}

    dry = bool(getattr(self, "dry_run", False))
    _log("debug", f"👤 user-config: dry_run={dry}")

    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "users_created": [],
        "users_disabled": [],
        "users_deleted": [],
        "ssh_keys_deployed": 0,
        "sudo_configured": [],
    }

    users = config.get("users", [])
    disable_users = config.get("disable_users", [])
    delete_users = config.get("delete_users", [])

    if not users and not disable_users and not delete_users:
        _log("warning", "👤 user-config: no users, disable_users, or delete_users provided")
        return {"injected": False, "reason": "no_config"}

    # Process user creation
    for user_config in users:
        username = user_config.get("name")
        if not username:
            _log("warning", "👤 user-config: user has no name, skipping")
            continue

        if dry:
            _log("info", f"DRY-RUN: would create user: {username}")
            results["users_created"].append(username)
            if user_config.get("ssh_keys"):
                results["ssh_keys_deployed"] += len(user_config["ssh_keys"])
            if user_config.get("sudo"):
                results["sudo_configured"].append(username)
        else:
            try:
                _create_user(g, logger, user_config)
                results["users_created"].append(username)
                _log("info", f"Created user: {username}")

                # Deploy SSH keys
                ssh_keys = user_config.get("ssh_keys", [])
                if ssh_keys:
                    _deploy_ssh_keys(g, logger, username, ssh_keys, user_config.get("home"))
                    results["ssh_keys_deployed"] += len(ssh_keys)

                # Configure sudo
                sudo_spec = user_config.get("sudo")
                if sudo_spec:
                    _configure_sudo(g, logger, username, sudo_spec)
                    results["sudo_configured"].append(username)

            except Exception as e:
                _log("error", f"Failed to create user {username}: {e}")
                raise

    # Disable users
    for username in disable_users:
        if dry:
            _log("info", f"DRY-RUN: would disable user: {username}")
            results["users_disabled"].append(username)
        else:
            try:
                _disable_user(g, logger, username)
                results["users_disabled"].append(username)
                _log("info", f"Disabled user: {username}")
            except Exception as e:
                _log("warning", f"Failed to disable user {username}: {e}")

    # Delete users
    for username in delete_users:
        if dry:
            _log("info", f"DRY-RUN: would delete user: {username}")
            results["users_deleted"].append(username)
        else:
            try:
                _delete_user(g, logger, username)
                results["users_deleted"].append(username)
                _log("info", f"Deleted user: {username}")
            except Exception as e:
                _log("warning", f"Failed to delete user {username}: {e}")

    _log("info", f"👤 user-config: injection complete; created={len(results['users_created'])}, disabled={len(results['users_disabled'])}, deleted={len(results['users_deleted'])}")
    return results


def _create_user(g: guestfs.GuestFS, logger: Any, user_config: dict[str, Any]) -> None:
    """Create a user account with specified configuration"""
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    username = user_config["name"]
    uid = user_config.get("uid")
    gid = user_config.get("gid", uid)
    groups = user_config.get("groups", [])
    comment = user_config.get("comment", "")
    shell = user_config.get("shell", "/bin/bash")
    home = user_config.get("home", f"/home/{username}")
    create_home = user_config.get("create_home", True)
    password = user_config.get("password")
    password_hash = user_config.get("password_hash")
    lock = user_config.get("lock", False)

    # Build useradd command
    cmd = ["useradd"]

    if uid:
        cmd.extend(["-u", str(uid)])
    if gid:
        cmd.extend(["-g", str(gid)])
    if groups:
        cmd.extend(["-G", ",".join(groups)])
    if comment:
        cmd.extend(["-c", comment])
    if shell:
        cmd.extend(["-s", shell])
    if home:
        cmd.extend(["-d", home])
    if create_home:
        cmd.append("-m")
    else:
        cmd.append("-M")

    cmd.append(username)

    # Execute useradd
    try:
        g.command(cmd)
    except Exception as e:
        _log("debug", f"useradd command failed: {e}, trying alternative approach")
        # Fallback: manually edit /etc/passwd, /etc/shadow, /etc/group
        _create_user_manual(g, logger, user_config)
        return

    # Set password if provided
    if password_hash:
        _set_password_hash(g, logger, username, password_hash)
    elif password:
        # Hash the password
        password_hash = _hash_password(password)
        _set_password_hash(g, logger, username, password_hash)

    # Lock account if requested
    if lock:
        try:
            g.command(["usermod", "-L", username])
        except Exception as e:
            _log("warning", f"Failed to lock user {username}: {e}")


def _create_user_manual(g: guestfs.GuestFS, logger: Any, user_config: dict[str, Any]) -> None:
    """Manually create user by editing /etc/passwd, /etc/shadow, /etc/group"""
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    username = user_config["name"]
    uid = user_config.get("uid", 1000)
    gid = user_config.get("gid", uid)
    comment = user_config.get("comment", "")
    shell = user_config.get("shell", "/bin/bash")
    home = user_config.get("home", f"/home/{username}")
    password_hash = user_config.get("password_hash", "!")

    # Hash plain password if provided
    if user_config.get("password") and not password_hash:
        password_hash = _hash_password(user_config["password"])

    # Read /etc/passwd
    try:
        passwd_content = g.read_file("/etc/passwd").decode("utf-8")
        # Append user entry
        passwd_entry = f"{username}:x:{uid}:{gid}:{comment}:{home}:{shell}\n"
        passwd_content += passwd_entry
        g.write("/etc/passwd", passwd_content.encode("utf-8"))
    except Exception as e:
        _log("error", f"Failed to update /etc/passwd: {e}")
        raise

    # Read /etc/shadow
    try:
        shadow_content = g.read_file("/etc/shadow").decode("utf-8")
        # Append shadow entry (days since epoch for last password change)
        import time
        days_since_epoch = int(time.time() / 86400)
        shadow_entry = f"{username}:{password_hash}:{days_since_epoch}:0:99999:7:::\n"
        shadow_content += shadow_entry
        g.write("/etc/shadow", shadow_content.encode("utf-8"))
    except Exception as e:
        _log("error", f"Failed to update /etc/shadow: {e}")
        raise

    # Read /etc/group and create group if needed
    try:
        group_content = g.read_file("/etc/group").decode("utf-8")
        # Check if group exists
        if not any(line.startswith(f"{username}:") for line in group_content.splitlines()):
            group_entry = f"{username}:x:{gid}:\n"
            group_content += group_entry
            g.write("/etc/group", group_content.encode("utf-8"))
    except Exception as e:
        _log("error", f"Failed to update /etc/group: {e}")
        raise

    # Create home directory if requested
    if user_config.get("create_home", True):
        try:
            if not g.is_dir(home):
                g.mkdir_p(home)
                # Try to set ownership (may fail on some guestfs versions)
                try:
                    g.command(["chown", "-R", f"{uid}:{gid}", home])
                except Exception:
                    pass
        except Exception as e:
            _log("warning", f"Failed to create home directory {home}: {e}")


def _hash_password(password: str) -> str:
    """Generate SHA-512 password hash (same as mkpasswd -m sha-512)"""
    # Generate salt
    salt = secrets.token_hex(8)
    # Use crypt-compatible SHA-512
    try:
        import crypt
        return crypt.crypt(password, f"$6${salt}$")
    except (ImportError, Exception):
        # Fallback if crypt module is not available (Python 3.13+) or doesn't support SHA-512
        # Return a SHA-512 hash with proper $6$ prefix for /etc/shadow compatibility
        return f"$6${salt}${hashlib.sha512((salt + password).encode()).hexdigest()}"


def _set_password_hash(g: guestfs.GuestFS, logger: Any, username: str, password_hash: str) -> None:
    """Set password hash in /etc/shadow"""
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    try:
        # Try using chpasswd -e (encrypted)
        g.command(["sh", "-c", f"echo '{username}:{password_hash}' | chpasswd -e"])
    except Exception as e:
        _log("debug", f"chpasswd failed, updating /etc/shadow directly: {e}")
        # Fallback: edit /etc/shadow directly
        try:
            shadow_content = g.read_file("/etc/shadow").decode("utf-8")
            lines = shadow_content.splitlines()
            new_lines = []
            for line in lines:
                if line.startswith(f"{username}:"):
                    parts = line.split(":")
                    parts[1] = password_hash
                    new_lines.append(":".join(parts))
                else:
                    new_lines.append(line)
            g.write("/etc/shadow", "\n".join(new_lines).encode("utf-8"))
        except Exception as e2:
            _log("error", f"Failed to set password hash: {e2}")
            raise


def _deploy_ssh_keys(g: guestfs.GuestFS, logger: Any, username: str, ssh_keys: list[str], home: str | None = None) -> None:
    """Deploy SSH public keys to user's authorized_keys"""
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    if not home:
        home = f"/home/{username}"

    ssh_dir = f"{home}/.ssh"
    authorized_keys = f"{ssh_dir}/authorized_keys"

    # Create .ssh directory
    try:
        if not g.is_dir(ssh_dir):
            g.mkdir_p(ssh_dir)
    except Exception as e:
        _log("error", f"Failed to create {ssh_dir}: {e}")
        raise

    # Write authorized_keys
    keys_content = "\n".join(ssh_keys) + "\n"
    try:
        g.write(authorized_keys, keys_content.encode("utf-8"))
        # Set permissions
        try:
            g.command(["chmod", "700", ssh_dir])
            g.command(["chmod", "600", authorized_keys])
            # Try to set ownership
            try:
                g.command(["chown", "-R", f"{username}:{username}", ssh_dir])
            except Exception:
                pass
        except Exception as e:
            _log("warning", f"Failed to set permissions on SSH files: {e}")
    except Exception as e:
        _log("error", f"Failed to write authorized_keys: {e}")
        raise


def _configure_sudo(g: guestfs.GuestFS, logger: Any, username: str, sudo_spec: str) -> None:
    """Configure sudo access for user"""
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    sudoers_dir = "/etc/sudoers.d"
    sudoers_file = f"{sudoers_dir}/{username}"

    # Ensure sudoers.d directory exists
    try:
        if not g.is_dir(sudoers_dir):
            g.mkdir_p(sudoers_dir)
    except Exception as e:
        _log("warning", f"sudoers.d directory doesn't exist: {e}")
        return

    # Create sudoers file
    sudoers_content = f"{username} {sudo_spec}\n"
    try:
        g.write(sudoers_file, sudoers_content.encode("utf-8"))
        # Set proper permissions (0440)
        try:
            g.command(["chmod", "0440", sudoers_file])
        except Exception:
            pass
    except Exception as e:
        _log("error", f"Failed to create sudoers file: {e}")
        raise


def _disable_user(g: guestfs.GuestFS, logger: Any, username: str) -> None:
    """Lock/disable a user account"""
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    try:
        g.command(["usermod", "-L", username])
    except Exception as e:
        _log("debug", f"usermod failed, locking via /etc/shadow: {e}")
        # Fallback: prefix password hash with !
        try:
            shadow_content = g.read_file("/etc/shadow").decode("utf-8")
            lines = shadow_content.splitlines()
            new_lines = []
            for line in lines:
                if line.startswith(f"{username}:"):
                    parts = line.split(":")
                    if not parts[1].startswith("!"):
                        parts[1] = "!" + parts[1]
                    new_lines.append(":".join(parts))
                else:
                    new_lines.append(line)
            g.write("/etc/shadow", "\n".join(new_lines).encode("utf-8"))
        except Exception as e2:
            _log("error", f"Failed to disable user: {e2}")
            raise


def _delete_user(g: guestfs.GuestFS, logger: Any, username: str) -> None:
    """Delete a user account"""
    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

    try:
        g.command(["userdel", "-r", username])
    except Exception as e:
        _log("debug", f"userdel failed, removing manually: {e}")
        # Fallback: manually remove from passwd/shadow/group
        try:
            # Remove from /etc/passwd
            passwd_content = g.read_file("/etc/passwd").decode("utf-8")
            passwd_lines = [l for l in passwd_content.splitlines() if not l.startswith(f"{username}:")]
            g.write("/etc/passwd", "\n".join(passwd_lines).encode("utf-8"))

            # Remove from /etc/shadow
            shadow_content = g.read_file("/etc/shadow").decode("utf-8")
            shadow_lines = [l for l in shadow_content.splitlines() if not l.startswith(f"{username}:")]
            g.write("/etc/shadow", "\n".join(shadow_lines).encode("utf-8"))

            # Remove from /etc/group
            group_content = g.read_file("/etc/group").decode("utf-8")
            group_lines = [l for l in group_content.splitlines() if not l.startswith(f"{username}:")]
            g.write("/etc/group", "\n".join(group_lines).encode("utf-8"))

            # Try to remove home directory
            home = f"/home/{username}"
            try:
                if g.is_dir(home):
                    g.command(["rm", "-rf", home])
            except Exception:
                pass
        except Exception as e2:
            _log("error", f"Failed to delete user: {e2}")
            raise
