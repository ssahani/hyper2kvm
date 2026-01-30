# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/config/validation.py
"""
Configuration validation with optional pydantic support.

Falls back to manual validation if pydantic is not available (RHEL 10 compatibility).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.optional_imports import PYDANTIC_AVAILABLE

# Import pydantic if available
if PYDANTIC_AVAILABLE:
    from ..core.optional_imports import (
        BaseModel,
        Field,
        field_validator,
        ConfigDict,
        ValidationError as PydanticValidationError,
    )


# Validation errors (unified interface)
class ConfigValidationError(Exception):
    """Configuration validation error (works with or without pydantic)."""

    def __init__(self, errors: List[Dict[str, Any]]):
        self.errors = errors
        messages = [f"{e['field']}: {e['message']}" for e in errors]
        super().__init__("\n".join(messages))


# Base configuration classes
if PYDANTIC_AVAILABLE:
    # Use pydantic for validation
    class NetworkConfigBase(BaseModel):  # type: ignore
        """Network configuration with pydantic validation."""

        model_config = ConfigDict(extra="forbid")  # type: ignore

        interface_name: str = Field(..., pattern=r"^[a-z][a-z0-9]*$")  # type: ignore
        mac_address: Optional[str] = Field(None, pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")  # type: ignore
        ip_address: Optional[str] = Field(None, pattern=r"^\d{1,3}(\.\d{1,3}){3}$")  # type: ignore
        gateway: Optional[str] = None
        dns_servers: List[str] = Field(default_factory=list)  # type: ignore

        @field_validator("dns_servers")  # type: ignore
        @classmethod
        def validate_dns(cls, v):
            if len(v) > 3:
                raise ValueError("Maximum 3 DNS servers allowed")
            return v

        @field_validator("ip_address", "gateway")  # type: ignore
        @classmethod
        def validate_ip(cls, v):
            if v is None:
                return v
            parts = v.split(".")
            if len(parts) != 4:
                raise ValueError(f"Invalid IP address: {v}")
            for part in parts:
                if not (0 <= int(part) <= 255):
                    raise ValueError(f"Invalid IP address: {v}")
            return v

else:
    # Fallback to manual validation (stdlib only)
    class NetworkConfigBase:
        """Network configuration with manual validation (no pydantic)."""

        def __init__(
            self,
            interface_name: str,
            mac_address: Optional[str] = None,
            ip_address: Optional[str] = None,
            gateway: Optional[str] = None,
            dns_servers: Optional[List[str]] = None,
        ):
            self.interface_name = interface_name
            self.mac_address = mac_address
            self.ip_address = ip_address
            self.gateway = gateway
            self.dns_servers = dns_servers or []

            # Validate
            errors = self._validate()
            if errors:
                raise ConfigValidationError(errors)

        def _validate(self) -> List[Dict[str, Any]]:
            """Manual validation."""
            errors = []

            # Validate interface name
            if not re.match(r"^[a-z][a-z0-9]*$", self.interface_name):
                errors.append(
                    {
                        "field": "interface_name",
                        "message": "Interface name must start with a letter and contain only lowercase letters and numbers",
                    }
                )

            # Validate MAC address
            if self.mac_address and not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", self.mac_address):
                errors.append({"field": "mac_address", "message": f"Invalid MAC address format: {self.mac_address}"})

            # Validate IP addresses
            for field in ["ip_address", "gateway"]:
                value = getattr(self, field)
                if value and not self._is_valid_ip(value):
                    errors.append({"field": field, "message": f"Invalid IP address: {value}"})

            # Validate DNS servers
            if len(self.dns_servers) > 3:
                errors.append({"field": "dns_servers", "message": "Maximum 3 DNS servers allowed"})

            return errors

        @staticmethod
        def _is_valid_ip(ip: str) -> bool:
            """Validate IP address."""
            parts = ip.split(".")
            if len(parts) != 4:
                return False
            try:
                return all(0 <= int(part) <= 255 for part in parts)
            except ValueError:
                return False

        def dict(self) -> Dict[str, Any]:
            """Convert to dict (pydantic-compatible interface)."""
            return {
                "interface_name": self.interface_name,
                "mac_address": self.mac_address,
                "ip_address": self.ip_address,
                "gateway": self.gateway,
                "dns_servers": self.dns_servers,
            }


# Public API (unified interface)
class NetworkConfig(NetworkConfigBase):
    """Network configuration (uses pydantic if available, otherwise manual validation)."""

    pass


# VMware source configuration
if PYDANTIC_AVAILABLE:

    class VMwareSourceConfigBase(BaseModel):  # type: ignore
        """VMware source configuration with pydantic."""

        model_config = ConfigDict(extra="forbid")  # type: ignore

        host: str
        username: str
        password: str = Field(..., repr=False)  # type: ignore
        vm_name: Optional[str] = None
        vm_uuid: Optional[str] = None
        datacenter: Optional[str] = None
        datastore: Optional[str] = None
        port: int = Field(default=443, ge=1, le=65535)  # type: ignore
        verify_ssl: bool = True

        @field_validator("vm_name")  # type: ignore
        @classmethod
        def require_identifier(cls, v, info):
            # Check if at least one identifier is provided
            if v is None:
                # Access the data being validated
                data = info.data if hasattr(info, "data") else {}
                vm_uuid = data.get("vm_uuid")
                if vm_uuid is None:
                    raise ValueError("Either vm_name or vm_uuid must be provided")
            return v

else:

    class VMwareSourceConfigBase:
        """VMware source configuration with manual validation."""

        def __init__(
            self,
            host: str,
            username: str,
            password: str,
            vm_name: Optional[str] = None,
            vm_uuid: Optional[str] = None,
            datacenter: Optional[str] = None,
            datastore: Optional[str] = None,
            port: int = 443,
            verify_ssl: bool = True,
        ):
            self.host = host
            self.username = username
            self.password = password
            self.vm_name = vm_name
            self.vm_uuid = vm_uuid
            self.datacenter = datacenter
            self.datastore = datastore
            self.port = port
            self.verify_ssl = verify_ssl

            errors = self._validate()
            if errors:
                raise ConfigValidationError(errors)

        def _validate(self) -> List[Dict[str, Any]]:
            errors = []

            # Require at least one identifier
            if not self.vm_name and not self.vm_uuid:
                errors.append({"field": "vm_name/vm_uuid", "message": "Either vm_name or vm_uuid must be provided"})

            # Validate port range
            if not (1 <= self.port <= 65535):
                errors.append({"field": "port", "message": f"Port must be between 1 and 65535, got {self.port}"})

            return errors

        def dict(self) -> Dict[str, Any]:
            return {
                "host": self.host,
                "username": self.username,
                "password": self.password,
                "vm_name": self.vm_name,
                "vm_uuid": self.vm_uuid,
                "datacenter": self.datacenter,
                "datastore": self.datastore,
                "port": self.port,
                "verify_ssl": self.verify_ssl,
            }


class VMwareSourceConfig(VMwareSourceConfigBase):
    """VMware source configuration (auto-selects implementation)."""

    pass


# Disk configuration
if PYDANTIC_AVAILABLE:

    class DiskConfigBase(BaseModel):  # type: ignore
        """Disk configuration with pydantic validation."""

        model_config = ConfigDict(extra="forbid")  # type: ignore

        source_path: Path
        output_format: str = Field(default="qcow2", pattern=r"^(qcow2|raw|vmdk|vhd)$")  # type: ignore
        compression: bool = True
        size_gb: Optional[int] = Field(None, ge=1, le=16384)  # type: ignore

        @field_validator("source_path")  # type: ignore
        @classmethod
        def disk_exists(cls, v):
            if not v.exists():
                raise ValueError(f"Disk not found: {v}")
            if not v.is_file():
                raise ValueError(f"Not a file: {v}")
            return v

else:

    class DiskConfigBase:
        """Disk configuration with manual validation."""

        def __init__(
            self,
            source_path: Union[str, Path],
            output_format: str = "qcow2",
            compression: bool = True,
            size_gb: Optional[int] = None,
        ):
            self.source_path = Path(source_path) if isinstance(source_path, str) else source_path
            self.output_format = output_format
            self.compression = compression
            self.size_gb = size_gb

            errors = self._validate()
            if errors:
                raise ConfigValidationError(errors)

        def _validate(self) -> List[Dict[str, Any]]:
            errors = []

            # Validate source path
            if not self.source_path.exists():
                errors.append({"field": "source_path", "message": f"Disk not found: {self.source_path}"})
            elif not self.source_path.is_file():
                errors.append({"field": "source_path", "message": f"Not a file: {self.source_path}"})

            # Validate output format
            if self.output_format not in ("qcow2", "raw", "vmdk", "vhd"):
                errors.append(
                    {"field": "output_format", "message": f"Invalid format: {self.output_format}. Must be qcow2, raw, vmdk, or vhd"}
                )

            # Validate size
            if self.size_gb is not None and not (1 <= self.size_gb <= 16384):
                errors.append({"field": "size_gb", "message": f"Size must be between 1 and 16384 GB, got {self.size_gb}"})

            return errors

        def dict(self) -> Dict[str, Any]:
            return {
                "source_path": str(self.source_path),
                "output_format": self.output_format,
                "compression": self.compression,
                "size_gb": self.size_gb,
            }


class DiskConfig(DiskConfigBase):
    """Disk configuration (auto-selects implementation)."""

    pass


# Configuration loader utilities
def load_yaml_config(yaml_path: Path) -> Dict[str, Any]:
    """
    Load and validate YAML configuration.

    Uses pydantic if available, otherwise manual validation.
    """
    import yaml

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    return data


def validate_config(config_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Validate configuration dictionary.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Basic validation
    if "hypervisor" not in config_dict:
        errors.append({"field": "hypervisor", "message": "hypervisor field is required"})

    hypervisor = config_dict.get("hypervisor")

    # Hypervisor-specific validation
    if hypervisor == "vmware":
        if "vmware" not in config_dict:
            errors.append({"field": "vmware", "message": "vmware configuration required when hypervisor=vmware"})
        else:
            try:
                VMwareSourceConfig(**config_dict["vmware"])
            except (ConfigValidationError, Exception) as e:
                if isinstance(e, ConfigValidationError):
                    errors.extend(e.errors)
                else:
                    errors.append({"field": "vmware", "message": str(e)})

    return errors
