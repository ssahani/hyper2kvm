"""
Admission Webhook for MigrationJob validation and mutation.

This webhook validates MigrationJob resources before they are created,
ensuring they meet all requirements and constraints.
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from kubernetes import client
from pydantic import ValidationError

from hyper2kvm.worker.schemas import OperationType

logger = logging.getLogger(__name__)


class MigrationJobValidator:
    """
    Validates MigrationJob specifications.

    Performs validation checks:
    - Schema validation (required fields)
    - Resource quota checks
    - Worker capacity validation
    - Timeout range validation
    - Priority range validation
    - Image format validation
    """

    def __init__(self):
        self.supported_operations = [op.value for op in OperationType]
        self.supported_formats = ['vmdk', 'vdi', 'vhd', 'vhdx', 'qcow2', 'raw']
        self.max_timeout_hours = 24
        self.max_priority = 100
        self.min_priority = 0

    def validate(self, spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate MigrationJob spec.

        Args:
            spec: MigrationJob spec dict

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate required fields
        if not spec.get('operation'):
            errors.append("operation is required")
        elif spec['operation'] not in self.supported_operations:
            errors.append(f"operation must be one of: {', '.join(self.supported_operations)}")

        image = spec.get('image', {})
        if not image.get('path'):
            errors.append("image.path is required")

        if not image.get('format'):
            errors.append("image.format is required")
        elif image['format'] not in self.supported_formats:
            errors.append(f"image.format must be one of: {', '.join(self.supported_formats)}")

        # Validate priority
        priority = spec.get('priority', 50)
        if not isinstance(priority, int):
            errors.append("priority must be an integer")
        elif priority < self.min_priority or priority > self.max_priority:
            errors.append(f"priority must be between {self.min_priority} and {self.max_priority}")

        # Validate timeout
        timeout = spec.get('timeout', '2h')
        if not self._validate_timeout(timeout):
            errors.append(f"timeout must be in format like '30m', '2h' (max {self.max_timeout_hours}h)")

        # Validate retry policy
        retry_policy = spec.get('retryPolicy', {})
        if retry_policy:
            max_retries = retry_policy.get('maxRetries', 0)
            if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 5:
                errors.append("retryPolicy.maxRetries must be between 0 and 5")

            backoff = retry_policy.get('backoff', 'exponential')
            if backoff not in ['exponential', 'linear', 'fixed']:
                errors.append("retryPolicy.backoff must be one of: exponential, linear, fixed")

        # Validate checksum format (if provided)
        checksum = image.get('checksum')
        if checksum and not checksum.startswith('sha256:'):
            errors.append("image.checksum must start with 'sha256:'")

        is_valid = len(errors) == 0
        return is_valid, errors

    def _validate_timeout(self, timeout: str) -> bool:
        """Validate timeout format and range."""
        if not isinstance(timeout, str):
            return False

        try:
            if timeout.endswith('s'):
                seconds = int(timeout[:-1])
                return 0 < seconds <= self.max_timeout_hours * 3600
            elif timeout.endswith('m'):
                minutes = int(timeout[:-1])
                return 0 < minutes <= self.max_timeout_hours * 60
            elif timeout.endswith('h'):
                hours = int(timeout[:-1])
                return 0 < hours <= self.max_timeout_hours
            else:
                return False
        except (ValueError, IndexError):
            return False

    def check_resource_quota(
        self,
        namespace: str,
        requesting_user: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if namespace has capacity for new job.

        Args:
            namespace: Namespace name
            requesting_user: User requesting the job (optional)

        Returns:
            Tuple of (allowed, denial_reason)
        """
        try:
            custom_api = client.CustomObjectsApi()

            # Get all MigrationJobs in namespace
            jobs = custom_api.list_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="migrationjobs"
            )

            # Count active jobs (not completed/failed/cancelled)
            active_states = ['Created', 'Validated', 'Queued', 'Assigned', 'Running', 'Progressing']
            active_jobs = [
                job for job in jobs.get('items', [])
                if job.get('status', {}).get('state') in active_states
            ]

            # Default quota: 10 active jobs per namespace
            max_jobs_per_namespace = 10

            if len(active_jobs) >= max_jobs_per_namespace:
                return False, f"Namespace quota exceeded: {len(active_jobs)}/{max_jobs_per_namespace} active jobs"

            return True, None

        except Exception as e:
            logger.warning(f"Could not check resource quota: {e}")
            # Allow job if quota check fails (fail open)
            return True, None

    def check_worker_capacity(self, namespace: str) -> Tuple[bool, Optional[str]]:
        """
        Check if workers are available to handle new job.

        Args:
            namespace: Namespace to check for workers

        Returns:
            Tuple of (has_capacity, warning_message)
        """
        try:
            v1 = client.CoreV1Api()

            # Get worker pods
            pods = v1.list_namespaced_pod(
                namespace=namespace,
                label_selector="app=hyper2kvm-worker"
            )

            running_workers = [
                pod for pod in pods.items
                if pod.status.phase == "Running"
            ]

            if len(running_workers) == 0:
                return False, "No worker pods available in namespace"

            return True, None

        except Exception as e:
            logger.warning(f"Could not check worker capacity: {e}")
            # Allow job if capacity check fails
            return True, None


class MigrationJobMutator:
    """
    Mutates MigrationJob specifications to add defaults.

    Applied mutations:
    - Set default priority (50)
    - Set default timeout (2h)
    - Set default retry policy (maxRetries: 2, backoff: exponential)
    - Add creation timestamp annotation
    """

    def mutate(self, spec: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply default values to MigrationJob spec.

        Args:
            spec: MigrationJob spec dict
            metadata: MigrationJob metadata dict

        Returns:
            Mutated spec dict
        """
        # Set default priority
        if 'priority' not in spec:
            spec['priority'] = 50
            logger.debug(f"Set default priority: 50")

        # Set default timeout
        if 'timeout' not in spec:
            spec['timeout'] = '2h'
            logger.debug(f"Set default timeout: 2h")

        # Set default retry policy
        if 'retryPolicy' not in spec:
            spec['retryPolicy'] = {
                'maxRetries': 2,
                'backoff': 'exponential'
            }
            logger.debug(f"Set default retryPolicy: maxRetries=2, backoff=exponential")

        # Set default artifacts output format if not specified
        if 'artifacts' in spec and 'output_format' not in spec['artifacts']:
            spec['artifacts']['output_format'] = 'qcow2'
            logger.debug(f"Set default artifacts.output_format: qcow2")

        # Add creation timestamp annotation
        if 'annotations' not in metadata:
            metadata['annotations'] = {}

        metadata['annotations']['hyper2kvm.io/created-at'] = datetime.utcnow().isoformat() + 'Z'
        metadata['annotations']['hyper2kvm.io/webhook-version'] = 'v1.5.0'

        return spec


def create_admission_review_response(
    uid: str,
    allowed: bool,
    message: str = None,
    patch: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create AdmissionReview response.

    Args:
        uid: Request UID
        allowed: Whether request is allowed
        message: Status message (for denials)
        patch: JSON patch operations (for mutations)

    Returns:
        AdmissionReview response dict
    """
    response = {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": uid,
            "allowed": allowed
        }
    }

    if message:
        response["response"]["status"] = {
            "message": message
        }

    if patch:
        import base64
        patch_bytes = json.dumps(patch).encode('utf-8')
        response["response"]["patch"] = base64.b64encode(patch_bytes).decode('utf-8')
        response["response"]["patchType"] = "JSONPatch"

    return response


def handle_validation_webhook(admission_review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle validation webhook request.

    Args:
        admission_review: AdmissionReview request

    Returns:
        AdmissionReview response
    """
    request = admission_review.get('request', {})
    uid = request.get('uid')
    obj = request.get('object', {})

    spec = obj.get('spec', {})
    metadata = obj.get('metadata', {})
    namespace = metadata.get('namespace', 'default')

    logger.info(f"Validating MigrationJob: {metadata.get('name')} in namespace {namespace}")

    validator = MigrationJobValidator()

    # Validate spec
    is_valid, errors = validator.validate(spec)
    if not is_valid:
        error_message = f"Validation failed: {'; '.join(errors)}"
        logger.warning(f"Validation failed for {metadata.get('name')}: {error_message}")
        return create_admission_review_response(
            uid=uid,
            allowed=False,
            message=error_message
        )

    # Check resource quota
    quota_allowed, quota_message = validator.check_resource_quota(namespace)
    if not quota_allowed:
        logger.warning(f"Quota check failed for {metadata.get('name')}: {quota_message}")
        return create_admission_review_response(
            uid=uid,
            allowed=False,
            message=quota_message
        )

    # Check worker capacity (warning only)
    has_capacity, capacity_warning = validator.check_worker_capacity(namespace)
    if not has_capacity:
        logger.warning(f"Capacity warning for {metadata.get('name')}: {capacity_warning}")
        # Still allow, but log warning

    logger.info(f"Validation passed for {metadata.get('name')}")
    return create_admission_review_response(
        uid=uid,
        allowed=True,
        message="Validation passed"
    )


def handle_mutation_webhook(admission_review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle mutation webhook request.

    Args:
        admission_review: AdmissionReview request

    Returns:
        AdmissionReview response with mutations
    """
    request = admission_review.get('request', {})
    uid = request.get('uid')
    obj = request.get('object', {})

    spec = obj.get('spec', {})
    metadata = obj.get('metadata', {})

    logger.info(f"Mutating MigrationJob: {metadata.get('name')}")

    mutator = MigrationJobMutator()

    # Apply mutations
    original_spec = json.dumps(spec, sort_keys=True)
    mutated_spec = mutator.mutate(spec, metadata)
    new_spec = json.dumps(mutated_spec, sort_keys=True)

    # Create JSON patch if spec was modified
    patch = []
    if original_spec != new_spec:
        patch.append({
            "op": "replace",
            "path": "/spec",
            "value": mutated_spec
        })
        logger.debug(f"Applied mutations to {metadata.get('name')}")

    # Always add annotations
    patch.append({
        "op": "add",
        "path": "/metadata/annotations",
        "value": metadata.get('annotations', {})
    })

    return create_admission_review_response(
        uid=uid,
        allowed=True,
        patch=patch if patch else None
    )
