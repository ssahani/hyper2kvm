"""
Kubernetes Operator Controller for MigrationJob CRD.

This operator watches MigrationJob resources and automatically:
- Discovers available workers
- Assigns jobs to capable workers
- Updates job status in real-time
- Emits Kubernetes events
- Handles retries and failures
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import kopf
import kubernetes
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from hyper2kvm.worker.schemas import JobState
from hyper2kvm.operator.worker_registry import WorkerRegistry
from hyper2kvm.operator.job_assigner import JobAssigner
from hyper2kvm.operator.dependency_manager import DependencyManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global registry, assigner, and dependency manager
worker_registry = WorkerRegistry()
job_assigner = JobAssigner(worker_registry)
dependency_manager = DependencyManager()


@kopf.on.startup()
async def configure(settings: kopf.OperatorSettings, **_):
    """Configure operator settings on startup."""
    settings.persistence.finalizer = 'hyper2kvm.io/finalizer'
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage()

    # Configure Kubernetes client
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration")
    except config.ConfigException:
        config.load_kube_config()
        logger.info("Loaded kubeconfig from ~/.kube/config")

    # Load existing jobs into dependency manager
    try:
        await dependency_manager.load_all_jobs("hyper2kvm-system")
        logger.info("Loaded existing jobs into dependency graph")
    except Exception as e:
        logger.warning(f"Could not load existing jobs: {e}")

    logger.info("Operator startup complete")


@kopf.on.create('hyper2kvm.io', 'v1alpha1', 'migrationjobs')
async def create_migration_job(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    **kwargs
):
    """
    Handle creation of MigrationJob resource.

    Validates the job spec and transitions to VALIDATED state.
    """
    logger.info(f"MigrationJob created: {namespace}/{name}")

    try:
        # Validate job specification
        operation = spec.get('operation')
        image = spec.get('image', {})

        if not operation or not image.get('path'):
            raise ValueError("Invalid job specification: missing operation or image path")

        # Register dependencies
        depends_on = spec.get('dependsOn', [])
        if depends_on:
            logger.info(f"Job {name} has {len(depends_on)} dependencies: {depends_on}")

            success, error = await dependency_manager.register_job(
                namespace=namespace,
                job_name=name,
                depends_on=depends_on,
                state=JobState.CREATED.value
            )

            if not success:
                raise ValueError(f"Invalid dependencies: {error}")
        else:
            # No dependencies, just register the job
            dependency_manager.validator.add_job(name, [], JobState.CREATED.value)

        # Update status to CREATED
        await update_job_status(
            namespace=namespace,
            name=name,
            state=JobState.CREATED.value,
            message=f"Job created with operation: {operation}"
        )

        # Emit Kubernetes event
        await emit_event(
            namespace=namespace,
            name=name,
            reason="JobCreated",
            message=f"MigrationJob {name} created successfully",
            event_type="Normal"
        )

        # Validate and transition to VALIDATED
        await asyncio.sleep(1)  # Simulate validation

        await update_job_status(
            namespace=namespace,
            name=name,
            state=JobState.VALIDATED.value,
            message="Job specification validated"
        )

        logger.info(f"MigrationJob {namespace}/{name} validated")

    except Exception as e:
        logger.error(f"Error creating job {namespace}/{name}: {e}")
        await update_job_status(
            namespace=namespace,
            name=name,
            state=JobState.FAILED.value,
            message=f"Validation failed: {str(e)}",
            error=str(e)
        )
        raise


@kopf.on.update('hyper2kvm.io', 'v1alpha1', 'migrationjobs')
async def update_migration_job(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    old: Dict[str, Any],
    new: Dict[str, Any],
    **kwargs
):
    """
    Handle updates to MigrationJob resource.

    Processes state transitions and job assignment.
    """
    current_state = status.get('state', JobState.CREATED.value)
    logger.info(f"MigrationJob updated: {namespace}/{name} (state: {current_state})")

    try:
        # Handle state transitions
        if current_state == JobState.VALIDATED.value:
            # Move to QUEUED
            await update_job_status(
                namespace=namespace,
                name=name,
                state=JobState.QUEUED.value,
                message="Job queued for worker assignment"
            )

        elif current_state == JobState.QUEUED.value:
            # Attempt worker assignment
            await assign_to_worker(namespace, name, spec, status)

    except Exception as e:
        logger.error(f"Error updating job {namespace}/{name}: {e}")
        raise


@kopf.timer('hyper2kvm.io', 'v1alpha1', 'migrationjobs', interval=30.0)
async def reconcile_migration_job(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    **kwargs
):
    """
    Periodic reconciliation of MigrationJob resources.

    Runs every 30 seconds to:
    - Check worker assignment for queued jobs
    - Update progress from running jobs
    - Handle timeouts
    """
    current_state = status.get('state')

    if current_state == JobState.QUEUED.value:
        # Try to assign to worker
        logger.debug(f"Reconciling queued job: {namespace}/{name}")
        await assign_to_worker(namespace, name, spec, status)

    elif current_state == JobState.ASSIGNED.value:
        # Check if worker started the job
        assigned_worker = status.get('assignedWorker')
        if assigned_worker:
            # Query worker for job status
            job_running = await check_job_running(namespace, assigned_worker, name)
            if job_running:
                await update_job_status(
                    namespace=namespace,
                    name=name,
                    state=JobState.RUNNING.value,
                    message=f"Job started on worker {assigned_worker}"
                )

    elif current_state == JobState.RUNNING.value:
        # Update progress from worker
        await update_job_progress(namespace, name, status)


@kopf.on.delete('hyper2kvm.io', 'v1alpha1', 'migrationjobs')
async def delete_migration_job(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    status: Dict[str, Any],
    **kwargs
):
    """
    Handle deletion of MigrationJob resource.

    Cancels running jobs and cleans up resources.
    """
    logger.info(f"MigrationJob deleted: {namespace}/{name}")

    current_state = status.get('state')
    assigned_worker = status.get('assignedWorker')

    if current_state in [JobState.RUNNING.value, JobState.PROGRESSING.value]:
        # Cancel job on worker
        if assigned_worker:
            logger.info(f"Cancelling job {name} on worker {assigned_worker}")
            await cancel_job_on_worker(namespace, assigned_worker, name)

    await emit_event(
        namespace=namespace,
        name=name,
        reason="JobDeleted",
        message=f"MigrationJob {name} deleted",
        event_type="Normal"
    )


# Helper functions

async def assign_to_worker(
    namespace: str,
    name: str,
    spec: Dict[str, Any],
    status: Dict[str, Any]
) -> bool:
    """
    Assign job to an available worker based on capabilities.

    Returns True if assignment successful, False otherwise.
    """
    try:
        # Check dependencies first
        can_execute, reason = dependency_manager.can_execute(name)
        if not can_execute:
            logger.debug(f"Job {name} cannot execute yet: {reason}")

            # Update dependency status
            dep_status = dependency_manager.get_dependency_status(name)
            await update_job_status(
                namespace=namespace,
                name=name,
                dependencies=dep_status
            )

            return False

        # Discover workers
        workers = await discover_workers(namespace)
        logger.debug(f"Found {len(workers)} workers in namespace {namespace}")

        if not workers:
            logger.warning(f"No workers available for job {namespace}/{name}")
            return False

        # Match job requirements to worker capabilities
        suitable_worker = await job_assigner.find_suitable_worker(
            spec=spec,
            workers=workers
        )

        if not suitable_worker:
            logger.warning(f"No suitable worker found for job {namespace}/{name}")
            return False

        # Assign job to worker
        worker_name = suitable_worker['name']
        logger.info(f"Assigning job {namespace}/{name} to worker {worker_name}")

        # Create job spec file on worker pod
        job_spec = create_job_spec(name, spec)
        await copy_job_to_worker(namespace, worker_name, name, job_spec)

        # Update status to ASSIGNED
        await update_job_status(
            namespace=namespace,
            name=name,
            state=JobState.ASSIGNED.value,
            assigned_worker=worker_name,
            message=f"Job assigned to worker {worker_name}"
        )

        await emit_event(
            namespace=namespace,
            name=name,
            reason="JobAssigned",
            message=f"Job assigned to worker {worker_name}",
            event_type="Normal"
        )

        # Start job execution on worker (async)
        await start_job_on_worker(namespace, worker_name, name)

        return True

    except Exception as e:
        logger.error(f"Error assigning job {namespace}/{name}: {e}")
        return False


async def discover_workers(namespace: str) -> List[Dict[str, Any]]:
    """
    Discover available worker pods in the namespace.

    Returns list of worker pod information.
    """
    v1 = client.CoreV1Api()

    try:
        pods = v1.list_namespaced_pod(
            namespace=namespace,
            label_selector="app=hyper2kvm-worker"
        )

        workers = []
        for pod in pods.items:
            if pod.status.phase == "Running":
                workers.append({
                    'name': pod.metadata.name,
                    'node': pod.spec.node_name,
                    'ip': pod.status.pod_ip,
                    'ready': all(c.ready for c in pod.status.container_statuses or [])
                })

        return workers

    except ApiException as e:
        logger.error(f"Error discovering workers: {e}")
        return []


def create_job_spec(job_name: str, crd_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert MigrationJob CRD spec to Worker Job Protocol format.
    """
    return {
        "version": "1.0",
        "job_id": job_name,
        "operation": crd_spec.get('operation'),
        "image": crd_spec.get('image'),
        "parameters": crd_spec.get('parameters', {}),
        "artifacts": crd_spec.get('artifacts', {}),
        "audit": {
            "requested_by": "kubernetes-operator",
            "request_time": datetime.now(timezone.utc).isoformat()
        }
    }


async def copy_job_to_worker(
    namespace: str,
    worker_pod: str,
    job_name: str,
    job_spec: Dict[str, Any]
):
    """
    Copy job specification to worker pod.
    """
    v1 = client.CoreV1Api()

    job_json = json.dumps(job_spec, indent=2)
    job_path = f"/var/lib/hyper2kvm/jobs/{job_name}.json"

    # Write job spec using kubectl exec equivalent
    exec_command = [
        'sh', '-c',
        f'mkdir -p /var/lib/hyper2kvm/jobs && cat > {job_path}'
    ]

    try:
        resp = kubernetes.stream.stream(
            v1.connect_get_namespaced_pod_exec,
            worker_pod,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False
        )

        resp.write_stdin(job_json)
        resp.close()

        logger.debug(f"Copied job spec to {worker_pod}:{job_path}")

    except ApiException as e:
        logger.error(f"Error copying job to worker: {e}")
        raise


async def start_job_on_worker(namespace: str, worker_pod: str, job_name: str):
    """
    Start job execution on worker pod.
    """
    v1 = client.CoreV1Api()

    exec_command = [
        'python3', '-m', 'hyper2kvm.worker.cli',
        'run', f'/var/lib/hyper2kvm/jobs/{job_name}.json',
        '--background'
    ]

    try:
        resp = kubernetes.stream.stream(
            v1.connect_get_namespaced_pod_exec,
            worker_pod,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False
        )

        logger.info(f"Started job {job_name} on worker {worker_pod}")
        logger.debug(f"Worker response: {resp}")

    except ApiException as e:
        logger.error(f"Error starting job on worker: {e}")
        raise


async def check_job_running(namespace: str, worker_pod: str, job_name: str) -> bool:
    """
    Check if job is running on worker.
    """
    v1 = client.CoreV1Api()

    exec_command = [
        'python3', '-m', 'hyper2kvm.worker.cli',
        'status', job_name, '--format', 'json'
    ]

    try:
        resp = kubernetes.stream.stream(
            v1.connect_get_namespaced_pod_exec,
            worker_pod,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False
        )

        status_json = json.loads(resp)
        state = status_json.get('state')

        return state in [JobState.RUNNING.value, JobState.PROGRESSING.value]

    except Exception as e:
        logger.debug(f"Could not check job status: {e}")
        return False


async def update_job_progress(namespace: str, name: str, status: Dict[str, Any]):
    """
    Update job progress from worker events.
    """
    assigned_worker = status.get('assignedWorker')
    if not assigned_worker:
        return

    v1 = client.CoreV1Api()

    # Read latest event from worker
    exec_command = [
        'sh', '-c',
        f'tail -n 1 /var/lib/hyper2kvm/events/{name}.events.jsonl 2>/dev/null || echo "null"'
    ]

    try:
        resp = kubernetes.stream.stream(
            v1.connect_get_namespaced_pod_exec,
            assigned_worker,
            namespace,
            command=exec_command,
            stderr=False,
            stdin=False,
            stdout=True,
            tty=False
        )

        if resp and resp != "null\n":
            event = json.loads(resp)

            # Update progress in CRD status
            await update_job_status(
                namespace=namespace,
                name=name,
                state=event.get('state', status.get('state')),
                progress={
                    'percentage': event.get('progress', {}).get('percentage', 0),
                    'currentPhase': event.get('progress', {}).get('phase', ''),
                    'message': event.get('message', '')
                }
            )

    except Exception as e:
        logger.debug(f"Could not update progress for {name}: {e}")


async def cancel_job_on_worker(namespace: str, worker_pod: str, job_name: str):
    """
    Cancel running job on worker.
    """
    v1 = client.CoreV1Api()

    exec_command = [
        'python3', '-m', 'hyper2kvm.worker.cli',
        'cancel', job_name
    ]

    try:
        resp = kubernetes.stream.stream(
            v1.connect_get_namespaced_pod_exec,
            worker_pod,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False
        )

        logger.info(f"Cancelled job {job_name} on worker {worker_pod}")

    except ApiException as e:
        logger.warning(f"Error cancelling job (worker may be gone): {e}")


async def update_job_status(
    namespace: str,
    name: str,
    state: Optional[str] = None,
    assigned_worker: Optional[str] = None,
    message: Optional[str] = None,
    progress: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    dependencies: Optional[Dict[str, Any]] = None
):
    """
    Update MigrationJob status in Kubernetes.
    """
    custom_api = client.CustomObjectsApi()

    try:
        # Get current resource
        resource = custom_api.get_namespaced_custom_object(
            group="hyper2kvm.io",
            version="v1alpha1",
            namespace=namespace,
            plural="migrationjobs",
            name=name
        )

        # Update status fields
        status = resource.get('status', {})

        if state:
            status['state'] = state

            # Update dependency manager
            dependency_manager.update_job_state(name, state)

            # Update timestamps
            if state == JobState.RUNNING.value and 'startTime' not in status:
                status['startTime'] = datetime.now(timezone.utc).isoformat()
            elif state in [JobState.COMPLETED.value, JobState.FAILED.value, JobState.CANCELLED.value]:
                status['completionTime'] = datetime.now(timezone.utc).isoformat()

                # Handle failure propagation
                if state == JobState.FAILED.value:
                    failed_jobs = await dependency_manager.propagate_failure(namespace, name)
                    if failed_jobs:
                        logger.warning(
                            f"Propagated failure from {name} to {len(failed_jobs)} dependent jobs"
                        )

        if assigned_worker:
            status['assignedWorker'] = assigned_worker

        if progress:
            status['progress'] = progress

        if dependencies:
            status['dependencies'] = dependencies

        if error:
            status['result'] = status.get('result', {})
            status['result']['success'] = False
            status['result']['errorMessage'] = error

        # Add condition
        if state:
            conditions = status.get('conditions', [])
            conditions.append({
                'type': state,
                'status': 'True',
                'lastTransitionTime': datetime.now(timezone.utc).isoformat(),
                'reason': state,
                'message': message or f'Job transitioned to {state}'
            })
            status['conditions'] = conditions[-10:]  # Keep last 10

        # Update resource
        resource['status'] = status

        custom_api.patch_namespaced_custom_object_status(
            group="hyper2kvm.io",
            version="v1alpha1",
            namespace=namespace,
            plural="migrationjobs",
            name=name,
            body=resource
        )

        logger.debug(f"Updated status for {namespace}/{name}: state={state}")

    except ApiException as e:
        logger.error(f"Error updating job status: {e}")


async def emit_event(
    namespace: str,
    name: str,
    reason: str,
    message: str,
    event_type: str = "Normal"
):
    """
    Emit Kubernetes event for MigrationJob.
    """
    v1 = client.CoreV1Api()

    event = client.CoreV1Event(
        metadata=client.V1ObjectMeta(
            name=f"{name}.{datetime.now().strftime('%s')}",
            namespace=namespace
        ),
        involved_object=client.V1ObjectReference(
            api_version="hyper2kvm.io/v1alpha1",
            kind="MigrationJob",
            name=name,
            namespace=namespace
        ),
        reason=reason,
        message=message,
        type=event_type,
        first_timestamp=datetime.now(timezone.utc),
        last_timestamp=datetime.now(timezone.utc),
        count=1,
        source=client.V1EventSource(component="hyper2kvm-operator")
    )

    try:
        v1.create_namespaced_event(namespace=namespace, body=event)
        logger.debug(f"Emitted event for {namespace}/{name}: {reason}")
    except ApiException as e:
        logger.warning(f"Could not emit event: {e}")
