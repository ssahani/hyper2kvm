"""
Migration Policy Controller for validating and managing MigrationPolicy CRs.

Handles:
- Policy validation on create/update
- VM label matching and policy lookup
- Policy violation detection
- Status updates
"""

import logging
import kopf
from kubernetes import client
from datetime import datetime
from typing import Dict, Any, Optional, List
import re

logger = logging.getLogger(__name__)

# Global metrics instance
_metrics = None


def set_metrics(metrics):
    """Set the global metrics instance."""
    global _metrics
    _metrics = metrics


def validate_policy_spec(spec: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate MigrationPolicy specification.

    Args:
        spec: Policy spec to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Validate bandwidth format
    bandwidth = spec.get('bandwidthPerMigration', '0')
    if bandwidth != '0':
        pattern = r'^[0-9]+[KMGT]i$'
        if not re.match(pattern, bandwidth):
            errors.append(
                f"Invalid bandwidthPerMigration format: {bandwidth}. "
                "Expected format: <number>[KMGT]i (e.g., '100Mi', '1Gi')"
            )

    # Validate timeout
    completion_timeout = spec.get('completionTimeoutPerGiB', 800)
    if completion_timeout < 60:
        errors.append(
            f"completionTimeoutPerGiB must be >= 60 seconds, got {completion_timeout}"
        )

    # Validate parallelism limits
    max_cluster = spec.get('maxParallelMigrationsPerCluster', 5)
    max_node = spec.get('maxParallelMigrationsPerNode', 2)

    if max_cluster < 1 or max_cluster > 100:
        errors.append(
            f"maxParallelMigrationsPerCluster must be 1-100, got {max_cluster}"
        )

    if max_node < 1 or max_node > 10:
        errors.append(
            f"maxParallelMigrationsPerNode must be 1-10, got {max_node}"
        )

    if max_node > max_cluster:
        errors.append(
            f"maxParallelMigrationsPerNode ({max_node}) cannot exceed "
            f"maxParallelMigrationsPerCluster ({max_cluster})"
        )

    # Validate progress timeout
    progress_timeout = spec.get('progressTimeout', 150)
    if progress_timeout < 30:
        errors.append(
            f"progressTimeout must be >= 30 seconds, got {progress_timeout}"
        )

    return len(errors) == 0, errors


def lookup_policy_for_vm(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    vm_labels: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """
    Find the MigrationPolicy that applies to a VM.

    Args:
        custom_api: Kubernetes API client
        namespace: VM namespace
        vm_labels: VM labels

    Returns:
        Policy spec or None
    """
    try:
        policies = custom_api.list_cluster_custom_object(
            group='hyper2kvm.io',
            version='v1alpha1',
            plural='migrationpolicies'
        )

        # Find first matching policy
        for policy in policies.get('items', []):
            spec = policy.get('spec', {})
            vm_selector = spec.get('vmSelector', {})

            if not vm_selector:
                # Default policy
                return spec

            # Check matchLabels
            match_labels = vm_selector.get('matchLabels', {})
            if match_labels:
                if all(vm_labels.get(k) == v for k, v in match_labels.items()):
                    return spec

            # Check matchExpressions
            match_expressions = vm_selector.get('matchExpressions', [])
            if match_expressions:
                if _match_expressions(vm_labels, match_expressions):
                    return spec

        return None

    except client.ApiException as e:
        logger.warning(f"Failed to lookup policy for VM: {e}")
        return None


def _match_expressions(labels: Dict[str, str], expressions: List[Dict[str, Any]]) -> bool:
    """Check if labels match selector expressions."""
    for expr in expressions:
        key = expr.get('key')
        operator = expr.get('operator')
        values = expr.get('values', [])

        if operator == 'In':
            if key not in labels or labels[key] not in values:
                return False
        elif operator == 'NotIn':
            if key in labels and labels[key] in values:
                return False
        elif operator == 'Exists':
            if key not in labels:
                return False
        elif operator == 'DoesNotExist':
            if key in labels:
                return False

    return True


async def update_policy_status(
    custom_api: client.CustomObjectsApi,
    policy_name: str,
    applied_vms: int,
    active_migrations: int
):
    """
    Update MigrationPolicy status.

    Args:
        custom_api: Kubernetes API client
        policy_name: Policy name
        applied_vms: Number of VMs matching this policy
        active_migrations: Number of active migrations using this policy
    """
    try:
        # Get current policy
        policy = custom_api.get_cluster_custom_object(
            group='hyper2kvm.io',
            version='v1alpha1',
            plural='migrationpolicies',
            name=policy_name
        )

        # Update status
        status = policy.get('status', {})
        status['observedGeneration'] = policy.get('metadata', {}).get('generation', 0)
        status['appliedToVMs'] = applied_vms
        status['activeMigrations'] = active_migrations
        status['lastApplied'] = datetime.utcnow().isoformat() + 'Z'

        # Set Valid condition
        conditions = status.get('conditions', [])

        # Update or add Valid condition
        valid_condition = None
        for cond in conditions:
            if cond['type'] == 'Valid':
                valid_condition = cond
                break

        if valid_condition:
            valid_condition['status'] = 'True'
            valid_condition['lastTransitionTime'] = datetime.utcnow().isoformat() + 'Z'
            valid_condition['reason'] = 'ValidationSucceeded'
            valid_condition['message'] = 'Policy specification is valid'
        else:
            conditions.append({
                'type': 'Valid',
                'status': 'True',
                'lastTransitionTime': datetime.utcnow().isoformat() + 'Z',
                'reason': 'ValidationSucceeded',
                'message': 'Policy specification is valid'
            })

        status['conditions'] = conditions

        # Patch status
        custom_api.patch_cluster_custom_object_status(
            group='hyper2kvm.io',
            version='v1alpha1',
            plural='migrationpolicies',
            name=policy_name,
            body={'status': status}
        )

        logger.debug(f"Updated status for policy {policy_name}")

    except client.ApiException as e:
        logger.warning(f"Failed to update policy status: {e}")


@kopf.on.create('hyper2kvm.io', 'v1alpha1', 'migrationpolicies')
async def on_policy_created(spec, meta, name, **kwargs):
    """Handle MigrationPolicy creation."""
    logger.info(f"MigrationPolicy created: {name}")

    # Validate policy
    is_valid, errors = validate_policy_spec(spec)

    if not is_valid:
        logger.error(f"Invalid MigrationPolicy {name}: {errors}")
        # Update status with error
        try:
            custom_api = client.CustomObjectsApi()
            status = {
                'observedGeneration': meta.get('generation', 0),
                'conditions': [{
                    'type': 'Valid',
                    'status': 'False',
                    'lastTransitionTime': datetime.utcnow().isoformat() + 'Z',
                    'reason': 'ValidationFailed',
                    'message': '; '.join(errors)
                }]
            }

            custom_api.patch_cluster_custom_object_status(
                group='hyper2kvm.io',
                version='v1alpha1',
                plural='migrationpolicies',
                name=name,
                body={'status': status}
            )
        except Exception as e:
            logger.warning(f"Failed to update policy status: {e}")

        raise kopf.PermanentError(f"Invalid policy: {'; '.join(errors)}")

    # Initialize status
    custom_api = client.CustomObjectsApi()
    await update_policy_status(custom_api, name, 0, 0)

    logger.info(f"✅ MigrationPolicy {name} validated and initialized")


@kopf.on.update('hyper2kvm.io', 'v1alpha1', 'migrationpolicies')
async def on_policy_updated(spec, meta, name, **kwargs):
    """Handle MigrationPolicy updates."""
    logger.info(f"MigrationPolicy updated: {name}")

    # Validate policy
    is_valid, errors = validate_policy_spec(spec)

    if not is_valid:
        logger.error(f"Invalid MigrationPolicy update for {name}: {errors}")
        raise kopf.PermanentError(f"Invalid policy: {'; '.join(errors)}")

    # Update status
    custom_api = client.CustomObjectsApi()
    await update_policy_status(custom_api, name, 0, 0)

    logger.info(f"✅ MigrationPolicy {name} updated and validated")


@kopf.on.validate('hyper2kvm.io', 'v1alpha1', 'migrationpolicies')
def validate_policy(spec, **kwargs):
    """Admission validation for MigrationPolicy."""
    is_valid, errors = validate_policy_spec(spec)

    if not is_valid:
        return kopf.AdmissionResponse(
            allowed=False,
            status=f"Validation failed: {'; '.join(errors)}"
        )

    return kopf.AdmissionResponse(allowed=True)
