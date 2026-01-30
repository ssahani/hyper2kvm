"""
Backup and Restore Manager for Operator State.

Manages state backup, restore, and disaster recovery.
"""

import logging
import json
import gzip
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path
from kubernetes import client

logger = logging.getLogger(__name__)


class BackupManager:
    """
    Manages operator state backup and restore.

    Handles:
    - State serialization
    - Backup scheduling
    - Restore operations
    - Backup validation
    """

    def __init__(self, backup_dir: str = "/var/lib/hyper2kvm/backups"):
        """
        Initialize backup manager.

        Args:
            backup_dir: Directory for storing backups
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.custom_api = client.CustomObjectsApi()

    async def create_backup(
        self,
        namespace: str,
        backup_name: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Create a backup of operator state.

        Args:
            namespace: Kubernetes namespace
            backup_name: Optional backup name (auto-generated if not provided)

        Returns:
            Tuple of (backup_path, error_message)
        """
        if not backup_name:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            backup_name = f"backup-{timestamp}"

        try:
            # Collect all operator resources
            backup_data = {
                'version': '2.0.0',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'namespace': namespace,
                'resources': {}
            }

            # Backup MigrationJobs
            jobs = self.custom_api.list_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="migrationjobs"
            )
            backup_data['resources']['migrationjobs'] = jobs.get('items', [])

            # Backup JobTemplates
            templates = self.custom_api.list_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="jobtemplates"
            )
            backup_data['resources']['jobtemplates'] = templates.get('items', [])

            # Backup ConfigMaps (operator configuration)
            v1 = client.CoreV1Api()
            configmaps = v1.list_namespaced_config_map(
                namespace=namespace,
                label_selector="app.kubernetes.io/component=operator"
            )
            backup_data['resources']['configmaps'] = [
                self._serialize_k8s_object(cm) for cm in configmaps.items
            ]

            # Serialize and compress
            backup_json = json.dumps(backup_data, indent=2)
            backup_bytes = backup_json.encode('utf-8')
            compressed = gzip.compress(backup_bytes)

            # Write to file
            backup_path = self.backup_dir / f"{backup_name}.json.gz"
            backup_path.write_bytes(compressed)

            logger.info(f"Created backup: {backup_path}")

            # Write metadata
            metadata = {
                'name': backup_name,
                'timestamp': backup_data['timestamp'],
                'namespace': namespace,
                'resource_counts': {
                    'migrationjobs': len(backup_data['resources']['migrationjobs']),
                    'jobtemplates': len(backup_data['resources']['jobtemplates']),
                    'configmaps': len(backup_data['resources']['configmaps'])
                },
                'size_bytes': len(compressed),
                'compressed': True
            }

            metadata_path = self.backup_dir / f"{backup_name}.meta.json"
            metadata_path.write_text(json.dumps(metadata, indent=2))

            return str(backup_path), None

        except Exception as e:
            error_msg = f"Backup creation failed: {e}"
            logger.error(error_msg)
            return None, error_msg

    def _serialize_k8s_object(self, obj: Any) -> Dict[str, Any]:
        """
        Serialize a Kubernetes object to dict.

        Args:
            obj: Kubernetes API object

        Returns:
            Dictionary representation
        """
        import kubernetes.client

        # Convert to dict
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return obj

    async def restore_backup(
        self,
        backup_path: str,
        namespace: Optional[str] = None,
        dry_run: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Restore operator state from backup.

        Args:
            backup_path: Path to backup file
            namespace: Optional namespace override
            dry_run: If True, validate only without applying

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Read and decompress backup
            backup_file = Path(backup_path)
            if not backup_file.exists():
                return False, f"Backup file not found: {backup_path}"

            compressed_data = backup_file.read_bytes()
            backup_bytes = gzip.decompress(compressed_data)
            backup_data = json.loads(backup_bytes.decode('utf-8'))

            # Validate backup version
            version = backup_data.get('version', '1.0.0')
            if version != '2.0.0':
                logger.warning(f"Backup version mismatch: {version} (expected 2.0.0)")

            # Use specified namespace or backup namespace
            target_namespace = namespace or backup_data.get('namespace')

            if dry_run:
                logger.info(f"DRY RUN: Would restore to namespace {target_namespace}")
                logger.info(f"Resources in backup: {backup_data.get('resources', {}).keys()}")
                return True, None

            # Restore MigrationJobs
            jobs = backup_data.get('resources', {}).get('migrationjobs', [])
            for job in jobs:
                job_name = job['metadata']['name']
                job['metadata']['namespace'] = target_namespace

                try:
                    self.custom_api.create_namespaced_custom_object(
                        group="hyper2kvm.io",
                        version="v1alpha1",
                        namespace=target_namespace,
                        plural="migrationjobs",
                        body=job
                    )
                    logger.info(f"Restored MigrationJob: {job_name}")
                except client.rest.ApiException as e:
                    if e.status == 409:  # Already exists
                        logger.warning(f"MigrationJob {job_name} already exists, skipping")
                    else:
                        raise

            # Restore JobTemplates
            templates = backup_data.get('resources', {}).get('jobtemplates', [])
            for template in templates:
                template_name = template['metadata']['name']
                template['metadata']['namespace'] = target_namespace

                try:
                    self.custom_api.create_namespaced_custom_object(
                        group="hyper2kvm.io",
                        version="v1alpha1",
                        namespace=target_namespace,
                        plural="jobtemplates",
                        body=template
                    )
                    logger.info(f"Restored JobTemplate: {template_name}")
                except client.rest.ApiException as e:
                    if e.status == 409:
                        logger.warning(f"JobTemplate {template_name} already exists, skipping")
                    else:
                        raise

            logger.info(f"Restore completed successfully from {backup_path}")
            return True, None

        except Exception as e:
            error_msg = f"Restore failed: {e}"
            logger.error(error_msg)
            return False, error_msg

    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List available backups.

        Returns:
            List of backup metadata
        """
        backups = []

        for meta_file in self.backup_dir.glob("*.meta.json"):
            try:
                metadata = json.loads(meta_file.read_text())
                backups.append(metadata)
            except Exception as e:
                logger.warning(f"Could not read backup metadata {meta_file}: {e}")

        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        return backups

    def delete_backup(self, backup_name: str) -> bool:
        """
        Delete a backup.

        Args:
            backup_name: Name of backup to delete

        Returns:
            True if deleted successfully
        """
        try:
            backup_file = self.backup_dir / f"{backup_name}.json.gz"
            meta_file = self.backup_dir / f"{backup_name}.meta.json"

            if backup_file.exists():
                backup_file.unlink()

            if meta_file.exists():
                meta_file.unlink()

            logger.info(f"Deleted backup: {backup_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting backup {backup_name}: {e}")
            return False

    def validate_backup(self, backup_path: str) -> tuple[bool, Optional[str]]:
        """
        Validate a backup file.

        Args:
            backup_path: Path to backup file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                return False, f"Backup file not found: {backup_path}"

            # Read and decompress
            compressed_data = backup_file.read_bytes()
            backup_bytes = gzip.decompress(compressed_data)
            backup_data = json.loads(backup_bytes.decode('utf-8'))

            # Check required fields
            required_fields = ['version', 'timestamp', 'namespace', 'resources']
            for field in required_fields:
                if field not in backup_data:
                    return False, f"Missing required field: {field}"

            # Validate resources
            resources = backup_data.get('resources', {})
            for resource_type, items in resources.items():
                if not isinstance(items, list):
                    return False, f"Invalid resource type: {resource_type}"

            return True, None

        except gzip.BadGzipFile:
            return False, "Invalid gzip format"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

    def cleanup_old_backups(self, keep_count: int = 10):
        """
        Delete old backups, keeping only the most recent.

        Args:
            keep_count: Number of backups to keep
        """
        backups = self.list_backups()

        if len(backups) <= keep_count:
            return

        # Delete oldest backups
        to_delete = backups[keep_count:]
        for backup in to_delete:
            self.delete_backup(backup['name'])

        logger.info(f"Cleaned up {len(to_delete)} old backups")
