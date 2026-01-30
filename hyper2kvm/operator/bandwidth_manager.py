"""
Bandwidth Manager for controlling migration network bandwidth.

Provides:
- Bandwidth allocation and enforcement
- Fair sharing across active migrations
- Per-migration and cluster-wide limits
- Integration with MigrationPolicy
"""

import logging
from kubernetes import client
from typing import Dict, Any, Optional
import re

logger = logging.getLogger(__name__)


class BandwidthManager:
    """Manager for migration bandwidth control."""

    def __init__(self, custom_api: client.CustomObjectsApi):
        """
        Initialize BandwidthManager.

        Args:
            custom_api: Kubernetes CustomObjectsApi client
        """
        self.custom_api = custom_api

    def parse_bandwidth(self, bandwidth_str: str) -> int:
        """
        Parse bandwidth string to bytes per second.

        Args:
            bandwidth_str: Bandwidth string (e.g., "100Mi", "1Gi")

        Returns:
            Bandwidth in bytes per second
        """
        if not bandwidth_str or bandwidth_str == '0':
            return 0

        bandwidth_str = bandwidth_str.strip()
        multipliers = {
            'Ki': 1024,
            'Mi': 1024 * 1024,
            'Gi': 1024 * 1024 * 1024,
            'Ti': 1024 * 1024 * 1024 * 1024,
            'K': 1000,
            'M': 1000 * 1000,
            'G': 1000 * 1000 * 1000,
            'T': 1000 * 1000 * 1000 * 1000,
        }

        for suffix, multiplier in multipliers.items():
            if bandwidth_str.endswith(suffix):
                try:
                    value = float(bandwidth_str[:-len(suffix)])
                    return int(value * multiplier)
                except ValueError:
                    return 0

        try:
            return int(bandwidth_str)
        except ValueError:
            return 0

    def format_bandwidth(self, bandwidth_bps: int) -> str:
        """
        Format bandwidth bytes per second to human-readable string.

        Args:
            bandwidth_bps: Bandwidth in bytes per second

        Returns:
            Formatted string (e.g., "100Mi")
        """
        if bandwidth_bps == 0:
            return "0"

        units = [
            ('Ti', 1024 * 1024 * 1024 * 1024),
            ('Gi', 1024 * 1024 * 1024),
            ('Mi', 1024 * 1024),
            ('Ki', 1024),
        ]

        for unit, divisor in units:
            if bandwidth_bps >= divisor:
                value = bandwidth_bps / divisor
                return f"{value:.1f}{unit}"

        return f"{bandwidth_bps}"

    async def allocate_bandwidth(
        self,
        namespace: str,
        vmim_name: str,
        policy: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Allocate bandwidth for a migration.

        Args:
            namespace: Migration namespace
            vmim_name: VirtualMachineInstanceMigration name
            policy: MigrationPolicy spec (optional)

        Returns:
            Allocated bandwidth in bytes per second, or None if unlimited
        """
        if not policy:
            return None

        bandwidth_per_migration = policy.get('bandwidthPerMigration', '0')
        if bandwidth_per_migration == '0':
            return None

        bandwidth_bps = self.parse_bandwidth(bandwidth_per_migration)

        if bandwidth_bps == 0:
            return None

        logger.info(
            f"Allocated bandwidth for migration {vmim_name}: "
            f"{self.format_bandwidth(bandwidth_bps)}/s"
        )

        return bandwidth_bps

    async def apply_bandwidth_limit(
        self,
        namespace: str,
        vmim_name: str,
        bandwidth_bps: int
    ) -> bool:
        """
        Apply bandwidth limit to a migration.

        Note: KubeVirt doesn't directly support bandwidth limiting via VMIM API.
        This would typically be done via:
        1. MigrationConfiguration resource (cluster-wide)
        2. Network policies
        3. CNI plugins with bandwidth limiting

        For now, this method annotates the VMIM with the desired bandwidth
        which can be used by network policies or external controllers.

        Args:
            namespace: Migration namespace
            vmim_name: VirtualMachineInstanceMigration name
            bandwidth_bps: Bandwidth limit in bytes per second

        Returns:
            True if applied successfully
        """
        try:
            # Annotate VMIM with bandwidth limit
            patch = {
                'metadata': {
                    'annotations': {
                        'hyper2kvm.io/bandwidth-limit': self.format_bandwidth(bandwidth_bps),
                        'hyper2kvm.io/bandwidth-limit-bytes': str(bandwidth_bps)
                    }
                }
            }

            self.custom_api.patch_namespaced_custom_object(
                group='kubevirt.io',
                version='v1',
                namespace=namespace,
                plural='virtualmachineinstancemigrations',
                name=vmim_name,
                body=patch
            )

            logger.info(
                f"Applied bandwidth limit to {vmim_name}: "
                f"{self.format_bandwidth(bandwidth_bps)}/s"
            )

            return True

        except client.ApiException as e:
            logger.error(f"Failed to apply bandwidth limit to {vmim_name}: {e}")
            return False

    async def get_cluster_bandwidth_usage(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current cluster-wide bandwidth usage.

        Args:
            namespace: Namespace filter (None for all)

        Returns:
            Dict with total allocated bandwidth and active migrations
        """
        try:
            if namespace:
                vmims = self.custom_api.list_namespaced_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    namespace=namespace,
                    plural='virtualmachineinstancemigrations'
                )
            else:
                vmims = self.custom_api.list_cluster_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    plural='virtualmachineinstancemigrations'
                )

            total_bandwidth = 0
            active_count = 0

            for vmim in vmims.get('items', []):
                status = vmim.get('status', {})
                phase = status.get('phase', '')

                if phase in ['Running', 'Scheduling', 'Pending']:
                    active_count += 1

                    # Get bandwidth from annotation
                    annotations = vmim.get('metadata', {}).get('annotations', {})
                    bandwidth_str = annotations.get('hyper2kvm.io/bandwidth-limit-bytes', '0')

                    try:
                        bandwidth = int(bandwidth_str)
                        total_bandwidth += bandwidth
                    except ValueError:
                        pass

            return {
                'total_bandwidth_bps': total_bandwidth,
                'total_bandwidth': self.format_bandwidth(total_bandwidth),
                'active_migrations': active_count
            }

        except client.ApiException as e:
            logger.error(f"Failed to get bandwidth usage: {e}")
            return {
                'total_bandwidth_bps': 0,
                'total_bandwidth': '0',
                'active_migrations': 0
            }

    async def fair_share_bandwidth(
        self,
        namespace: Optional[str],
        total_bandwidth_bps: int
    ) -> bool:
        """
        Distribute bandwidth fairly across active migrations.

        Args:
            namespace: Namespace to apply to (None for all)
            total_bandwidth_bps: Total bandwidth to distribute

        Returns:
            True if applied successfully
        """
        try:
            if namespace:
                vmims = self.custom_api.list_namespaced_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    namespace=namespace,
                    plural='virtualmachineinstancemigrations'
                )
            else:
                vmims = self.custom_api.list_cluster_custom_object(
                    group='kubevirt.io',
                    version='v1',
                    plural='virtualmachineinstancemigrations'
                )

            active_migrations = []
            for vmim in vmims.get('items', []):
                status = vmim.get('status', {})
                phase = status.get('phase', '')

                if phase in ['Running', 'Scheduling', 'Pending']:
                    active_migrations.append(vmim)

            if not active_migrations:
                logger.info("No active migrations to share bandwidth")
                return True

            # Calculate fair share
            bandwidth_per_migration = total_bandwidth_bps // len(active_migrations)

            logger.info(
                f"Fair sharing {self.format_bandwidth(total_bandwidth_bps)}/s "
                f"across {len(active_migrations)} migrations: "
                f"{self.format_bandwidth(bandwidth_per_migration)}/s each"
            )

            # Apply to each migration
            for vmim in active_migrations:
                vmim_name = vmim['metadata']['name']
                vmim_namespace = vmim['metadata']['namespace']

                await self.apply_bandwidth_limit(
                    vmim_namespace,
                    vmim_name,
                    bandwidth_per_migration
                )

            return True

        except client.ApiException as e:
            logger.error(f"Failed to fair share bandwidth: {e}")
            return False
