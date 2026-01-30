"""
Admission webhook validation for MigrationJob CRD.

Validates MigrationJob resources before they're created or updated.
Prevents invalid configurations and checks prerequisites.
"""
import logging
import re
from typing import Dict, List, Tuple, Any, Optional
from kubernetes import client

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class MigrationJobValidator:
    """Validates MigrationJob resources."""

    def __init__(self, k8s_core_api: Optional[client.CoreV1Api] = None):
        """
        Initialize validator.

        Args:
            k8s_core_api: Kubernetes CoreV1 API client (for checking PVC existence)
        """
        self.core_api = k8s_core_api
        self.warnings = []

    def validate(self, spec: Dict[str, Any], namespace: str, dry_run: bool = False) -> Tuple[bool, List[str], List[str]]:
        """
        Validate a MigrationJob spec.

        Args:
            spec: MigrationJob spec dict
            namespace: Kubernetes namespace
            dry_run: Whether this is a dry-run validation

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors = []
        self.warnings = []

        try:
            # Required fields
            self._validate_required_fields(spec, errors)

            # Source validation
            self._validate_source(spec.get('source', {}), namespace, errors)

            # Migration options validation
            self._validate_migration_options(spec.get('migration', {}), errors)

            # Destination validation
            self._validate_destination(spec.get('destination', {}), errors)

            # VM creation validation
            self._validate_vm_creation(spec.get('createVM', {}), errors)

            # Cleanup policy validation
            self._validate_cleanup_policy(spec.get('cleanupPolicy'), errors)

            # Timeout validation
            self._validate_timeout(spec.get('timeout'), errors)

            # Cross-field validations
            self._validate_cross_fields(spec, errors)

            # Dry-run specific validations
            if dry_run:
                self._validate_dry_run_prerequisites(spec, namespace, errors)

        except Exception as e:
            logger.error(f"Validation exception: {e}")
            errors.append(f"Internal validation error: {str(e)}")

        is_valid = len(errors) == 0
        return is_valid, errors, self.warnings

    def _validate_required_fields(self, spec: Dict[str, Any], errors: List[str]):
        """Validate required fields are present."""
        if 'source' not in spec:
            errors.append("spec.source is required")

        if 'destination' not in spec:
            errors.append("spec.destination is required")

    def _validate_source(self, source: Dict[str, Any], namespace: str, errors: List[str]):
        """Validate source configuration."""
        if not source:
            return

        source_type = source.get('type', 'vmdk-url')

        if source_type not in ['vmdk-url', 'vmdk-pvc', 'pvc']:
            errors.append(f"Invalid source.type: {source_type}. Must be one of: vmdk-url, vmdk-pvc, pvc")
            return

        if source_type == 'vmdk-url':
            vmdk = source.get('vmdk', {})
            url = vmdk.get('url')
            if not url:
                errors.append("source.vmdk.url is required for source.type=vmdk-url")
            elif not url.startswith(('http://', 'https://')):
                errors.append(f"source.vmdk.url must be HTTP(S) URL, got: {url}")

        elif source_type == 'vmdk-pvc':
            vmdk = source.get('vmdk', {})
            pvc_name = vmdk.get('pvcName')
            if not pvc_name:
                errors.append("source.vmdk.pvcName is required for source.type=vmdk-pvc")
            else:
                # Check if PVC exists (if API available)
                if self.core_api:
                    try:
                        self.core_api.read_namespaced_persistent_volume_claim(pvc_name, namespace)
                    except client.exceptions.ApiException as e:
                        if e.status == 404:
                            errors.append(f"Source PVC not found: {pvc_name}")

        elif source_type == 'pvc':
            pvc_spec = source.get('pvc', {})
            pvc_name = pvc_spec.get('name')
            if not pvc_name:
                errors.append("source.pvc.name is required for source.type=pvc")
            else:
                # Check if PVC exists
                if self.core_api:
                    try:
                        self.core_api.read_namespaced_persistent_volume_claim(pvc_name, namespace)
                    except client.exceptions.ApiException as e:
                        if e.status == 404:
                            errors.append(f"Source PVC not found: {pvc_name}")

    def _validate_migration_options(self, migration: Dict[str, Any], errors: List[str]):
        """Validate migration options."""
        if not migration:
            return

        # Offline fixes validation
        offline_fixes = migration.get('offlineFixes', {})
        if offline_fixes:
            fstab_mode = offline_fixes.get('fstabMode')
            if fstab_mode and fstab_mode not in ['none', 'uuid-only', 'stabilize-partitions', 'stabilize-all']:
                errors.append(f"Invalid fstabMode: {fstab_mode}")

            initramfs_modules = offline_fixes.get('initramfsModules', [])
            if initramfs_modules and not isinstance(initramfs_modules, list):
                errors.append("initramfsModules must be a list")

        # Conversion validation
        conversion = migration.get('conversion', {})
        if conversion:
            fmt = conversion.get('format')
            if fmt and fmt not in ['qcow2', 'raw']:
                errors.append(f"Invalid conversion format: {fmt}")

            compression_type = conversion.get('compressionType')
            if compression_type and compression_type not in ['zstd', 'zlib']:
                errors.append(f"Invalid compression type: {compression_type}")

    def _validate_destination(self, destination: Dict[str, Any], errors: List[str]):
        """Validate destination configuration."""
        if not destination:
            return

        size = destination.get('size')
        if not size:
            errors.append("destination.size is required")
        elif not re.match(r'^\d+[KMGT]i$', size):
            errors.append(f"Invalid destination.size format: {size}. Expected format: 10Gi, 20Gi, etc.")

        storage_class = destination.get('storageClass')
        if storage_class:
            # Validate storage class name format
            if not re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', storage_class):
                errors.append(f"Invalid storageClass name: {storage_class}")

    def _validate_vm_creation(self, create_vm: Dict[str, Any], errors: List[str]):
        """Validate VM creation options."""
        if not create_vm or not create_vm.get('enabled', False):
            return

        # CPU validation
        cpu = create_vm.get('cpu')
        if cpu and not re.match(r'^\d+$', str(cpu)):
            errors.append(f"Invalid cpu value: {cpu}. Must be a number")

        # Memory validation
        memory = create_vm.get('memory')
        if memory and not re.match(r'^\d+[KMGT]i$', str(memory)):
            errors.append(f"Invalid memory format: {memory}. Expected format: 2Gi, 4Gi, etc.")

        # Network type validation
        network_type = create_vm.get('networkType')
        if network_type and network_type not in ['pod', 'masquerade', 'bridge']:
            errors.append(f"Invalid networkType: {network_type}")

    def _validate_cleanup_policy(self, cleanup_policy: Optional[str], errors: List[str]):
        """Validate cleanup policy."""
        if cleanup_policy and cleanup_policy not in ['Always', 'OnSuccess', 'Never']:
            errors.append(f"Invalid cleanupPolicy: {cleanup_policy}")

    def _validate_timeout(self, timeout: Optional[str], errors: List[str]):
        """Validate timeout format."""
        if timeout:
            if not re.match(r'^\d+[smh]$', timeout):
                errors.append(f"Invalid timeout format: {timeout}. Expected format: 30m, 1h, 2h, etc.")

    def _validate_cross_fields(self, spec: Dict[str, Any], errors: List[str]):
        """Validate cross-field dependencies."""
        # If createVM.enabled is true, ensure destination PVC size is reasonable
        create_vm = spec.get('createVM', {})
        if create_vm.get('enabled'):
            destination = spec.get('destination', {})
            size_str = destination.get('size', '10Gi')

            # Parse size
            match = re.match(r'^(\d+)([KMGT])i$', size_str)
            if match:
                value = int(match.group(1))
                unit = match.group(2)

                # Convert to GiB for comparison
                multipliers = {'K': 0.001, 'M': 0.001, 'G': 1, 'T': 1024}
                size_gb = value * multipliers[unit]

                if size_gb < 1:
                    self.warnings.append(
                        f"Destination size {size_str} is very small for a VM. "
                        "Consider at least 10Gi for most Linux VMs"
                    )

        # Check if multi-disk is specified but not supported yet
        source = spec.get('source', {})
        if 'disks' in source:
            # This will be supported in multi-disk feature
            pass

    def _validate_dry_run_prerequisites(self, spec: Dict[str, Any], namespace: str, errors: List[str]):
        """Additional validations for dry-run mode."""
        # Check if nodes with NBD capability exist
        # Check if storage class exists
        # Check if KubeVirt is installed
        # These would require API access

        destination = spec.get('destination', {})
        storage_class = destination.get('storageClass', 'local-path')

        self.warnings.append(
            f"Dry-run: ensure StorageClass '{storage_class}' exists and has sufficient capacity"
        )

        if spec.get('createVM', {}).get('enabled'):
            self.warnings.append(
                "Dry-run: ensure KubeVirt is installed for VM creation"
            )


def validate_migration_job(spec: Dict[str, Any], namespace: str, dry_run: bool = False) -> Tuple[bool, List[str], List[str]]:
    """
    Validate a MigrationJob spec.

    Args:
        spec: MigrationJob spec dict
        namespace: Kubernetes namespace
        dry_run: Whether this is a dry-run validation

    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    validator = MigrationJobValidator()
    return validator.validate(spec, namespace, dry_run)


# Kopf webhook handler
def validate_webhook(spec: Dict[str, Any], namespace: str, **kwargs) -> str:
    """
    Kopf webhook validation handler.

    Returns:
        Validation message (empty string if valid)
    """
    is_valid, errors, warnings = validate_migration_job(spec, namespace)

    if not is_valid:
        error_msg = "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        if warnings:
            error_msg += "\n\nWarnings:\n" + "\n".join(f"  - {w}" for w in warnings)
        return error_msg

    return ""  # Valid
