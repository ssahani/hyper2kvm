"""
Prometheus metrics for Kubernetes Operator.

Tracks operator performance, job lifecycle, and worker utilization.
"""

import logging
from prometheus_client import Counter, Histogram, Gauge, Info, Summary
from typing import Optional

logger = logging.getLogger(__name__)


class OperatorMetrics:
    """
    Prometheus metrics for the operator.

    Metrics exposed:
    - Reconciliation performance (duration, rate, errors)
    - Job lifecycle (created, assigned, completed, failed)
    - Worker utilization (active workers, job distribution)
    - Queue depth (pending jobs)
    - Admission webhook (validation, mutation, rejections)
    """

    def __init__(self, operator_id: str = "hyper2kvm-operator"):
        """
        Initialize operator metrics.

        Args:
            operator_id: Unique operator identifier
        """
        self.operator_id = operator_id

        # Operator info
        self.operator_info = Info(
            'hyper2kvm_operator',
            'Operator information'
        )
        self.operator_info.info({
            'operator_id': operator_id,
            'version': 'v1.9.0'
        })

        # Reconciliation metrics
        self.reconciliation_total = Counter(
            'hyper2kvm_operator_reconciliation_total',
            'Total number of reconciliation loops',
            ['namespace']
        )

        self.reconciliation_duration = Histogram(
            'hyper2kvm_operator_reconciliation_duration_seconds',
            'Duration of reconciliation loops',
            ['namespace'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )

        self.reconciliation_errors = Counter(
            'hyper2kvm_operator_reconciliation_errors_total',
            'Total reconciliation errors',
            ['namespace', 'error_type']
        )

        # Job lifecycle metrics
        self.jobs_created = Counter(
            'hyper2kvm_operator_jobs_created_total',
            'Total jobs created',
            ['namespace']
        )

        self.jobs_validated = Counter(
            'hyper2kvm_operator_jobs_validated_total',
            'Total jobs validated',
            ['namespace', 'result']  # result: success, failure
        )

        self.jobs_assigned = Counter(
            'hyper2kvm_operator_jobs_assigned_total',
            'Total jobs assigned to workers',
            ['namespace']
        )

        self.jobs_completed = Counter(
            'hyper2kvm_operator_jobs_completed_total',
            'Total jobs completed',
            ['namespace', 'result']  # result: success, failure, cancelled
        )

        self.job_assignment_duration = Histogram(
            'hyper2kvm_operator_job_assignment_duration_seconds',
            'Duration to assign job to worker',
            ['namespace'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )

        # Queue metrics
        self.queue_depth = Gauge(
            'hyper2kvm_operator_queue_depth',
            'Number of jobs in queue (QUEUED state)',
            ['namespace']
        )

        self.queue_wait_time = Histogram(
            'hyper2kvm_operator_queue_wait_time_seconds',
            'Time jobs spend in queue before assignment',
            ['namespace'],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600]
        )

        # Worker metrics
        self.workers_discovered = Gauge(
            'hyper2kvm_operator_workers_discovered',
            'Number of workers discovered',
            ['namespace']
        )

        self.workers_available = Gauge(
            'hyper2kvm_operator_workers_available',
            'Number of available workers (0 active jobs)',
            ['namespace']
        )

        self.worker_job_distribution = Gauge(
            'hyper2kvm_operator_worker_jobs',
            'Number of active jobs per worker',
            ['namespace', 'worker']
        )

        self.worker_discovery_duration = Histogram(
            'hyper2kvm_operator_worker_discovery_duration_seconds',
            'Duration of worker discovery',
            ['namespace'],
            buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )

        # Status update metrics
        self.status_updates = Counter(
            'hyper2kvm_operator_status_updates_total',
            'Total CRD status updates',
            ['namespace', 'state']
        )

        self.status_update_errors = Counter(
            'hyper2kvm_operator_status_update_errors_total',
            'Total status update errors',
            ['namespace']
        )

        # Event metrics
        self.events_emitted = Counter(
            'hyper2kvm_operator_events_emitted_total',
            'Total Kubernetes events emitted',
            ['namespace', 'event_type', 'reason']
        )

        # Admission webhook metrics
        self.webhook_validations = Counter(
            'hyper2kvm_operator_webhook_validations_total',
            'Total validation webhook requests',
            ['result']  # result: allowed, denied, error
        )

        self.webhook_mutations = Counter(
            'hyper2kvm_operator_webhook_mutations_total',
            'Total mutation webhook requests',
            ['mutated']  # mutated: yes, no
        )

        self.webhook_duration = Histogram(
            'hyper2kvm_operator_webhook_duration_seconds',
            'Webhook request duration',
            ['type'],  # type: validation, mutation
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0]
        )

        # Operator health
        self.operator_healthy = Gauge(
            'hyper2kvm_operator_healthy',
            'Operator health status (1 = healthy, 0 = unhealthy)'
        )
        self.operator_healthy.set(1)

        # Leader election metrics
        self.leader_election_enabled = Gauge(
            'hyper2kvm_operator_leader_election_enabled',
            'Whether leader election is enabled (1 = enabled, 0 = disabled)'
        )

        self.is_leader = Gauge(
            'hyper2kvm_operator_is_leader',
            'Whether this instance is the leader (1 = leader, 0 = standby)'
        )

        self.leader_transitions = Counter(
            'hyper2kvm_operator_leader_transitions_total',
            'Total number of leadership transitions'
        )

        self.lease_renewal_total = Counter(
            'hyper2kvm_operator_lease_renewal_total',
            'Total number of lease renewals',
            ['result']  # result: success, failure
        )

        self.lease_acquisition_total = Counter(
            'hyper2kvm_operator_lease_acquisition_total',
            'Total number of lease acquisitions',
            ['result']  # result: success, failure
        )

        self.time_since_last_renewal = Gauge(
            'hyper2kvm_operator_time_since_last_renewal_seconds',
            'Seconds since last successful lease renewal'
        )

        # Dependency and DAG metrics
        self.dag_total_jobs = Gauge(
            'hyper2kvm_operator_dag_total_jobs',
            'Total number of jobs in the dependency graph',
            ['namespace']
        )

        self.dag_ready_jobs = Gauge(
            'hyper2kvm_operator_dag_ready_jobs',
            'Number of jobs ready for execution (all dependencies met)',
            ['namespace']
        )

        self.dag_blocked_jobs = Gauge(
            'hyper2kvm_operator_dag_blocked_jobs',
            'Number of jobs blocked by dependencies',
            ['namespace']
        )

        self.dag_max_depth = Gauge(
            'hyper2kvm_operator_dag_max_depth',
            'Maximum depth of the dependency graph',
            ['namespace']
        )

        self.dag_parallelism_potential = Gauge(
            'hyper2kvm_operator_dag_parallelism_potential',
            'Maximum number of jobs that could run in parallel',
            ['namespace']
        )

        self.dependency_violations = Counter(
            'hyper2kvm_operator_dependency_violations_total',
            'Total dependency validation failures',
            ['namespace', 'violation_type']  # violation_type: cycle, missing_ref, self_dependency
        )

        self.dependency_failures_propagated = Counter(
            'hyper2kvm_operator_dependency_failures_propagated_total',
            'Total number of failures propagated to dependent jobs',
            ['namespace']
        )

        self.job_dependency_count = Histogram(
            'hyper2kvm_operator_job_dependency_count',
            'Number of dependencies per job',
            ['namespace'],
            buckets=[0, 1, 2, 3, 5, 10, 20, 50]
        )

        self.dependency_wait_time = Histogram(
            'hyper2kvm_operator_dependency_wait_time_seconds',
            'Time job waited for dependencies to complete',
            ['namespace'],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200]
        )

        # Initialize migration-specific metrics
        self.__init_migration_metrics__()

        logger.info(f"Operator metrics initialized for {operator_id}")

    # Reconciliation methods

    def record_reconciliation(self, namespace: str, duration: float, error: Optional[str] = None):
        """Record reconciliation loop execution."""
        self.reconciliation_total.labels(namespace=namespace).inc()
        self.reconciliation_duration.labels(namespace=namespace).observe(duration)

        if error:
            error_type = error.__class__.__name__ if hasattr(error, '__class__') else 'Unknown'
            self.reconciliation_errors.labels(
                namespace=namespace,
                error_type=error_type
            ).inc()

    # Job lifecycle methods

    def record_job_created(self, namespace: str):
        """Record job creation."""
        self.jobs_created.labels(namespace=namespace).inc()

    def record_job_validated(self, namespace: str, success: bool):
        """Record job validation."""
        result = 'success' if success else 'failure'
        self.jobs_validated.labels(namespace=namespace, result=result).inc()

    def record_job_assigned(self, namespace: str, duration: float):
        """Record job assignment."""
        self.jobs_assigned.labels(namespace=namespace).inc()
        self.job_assignment_duration.labels(namespace=namespace).observe(duration)

    def record_job_completed(self, namespace: str, success: bool, cancelled: bool = False):
        """Record job completion."""
        if cancelled:
            result = 'cancelled'
        elif success:
            result = 'success'
        else:
            result = 'failure'

        self.jobs_completed.labels(namespace=namespace, result=result).inc()

    # Queue methods

    def update_queue_depth(self, namespace: str, depth: int):
        """Update queue depth gauge."""
        self.queue_depth.labels(namespace=namespace).set(depth)

    def record_queue_wait_time(self, namespace: str, wait_time: float):
        """Record time job spent in queue."""
        self.queue_wait_time.labels(namespace=namespace).observe(wait_time)

    # Worker methods

    def update_worker_count(self, namespace: str, total: int, available: int):
        """Update worker count gauges."""
        self.workers_discovered.labels(namespace=namespace).set(total)
        self.workers_available.labels(namespace=namespace).set(available)

    def update_worker_jobs(self, namespace: str, worker: str, active_jobs: int):
        """Update worker job distribution."""
        self.worker_job_distribution.labels(
            namespace=namespace,
            worker=worker
        ).set(active_jobs)

    def record_worker_discovery(self, namespace: str, duration: float):
        """Record worker discovery duration."""
        self.worker_discovery_duration.labels(namespace=namespace).observe(duration)

    # Status update methods

    def record_status_update(self, namespace: str, state: str, error: bool = False):
        """Record CRD status update."""
        self.status_updates.labels(namespace=namespace, state=state).inc()

        if error:
            self.status_update_errors.labels(namespace=namespace).inc()

    # Event methods

    def record_event(self, namespace: str, event_type: str, reason: str):
        """Record Kubernetes event emission."""
        self.events_emitted.labels(
            namespace=namespace,
            event_type=event_type,
            reason=reason
        ).inc()

    # Webhook methods

    def record_validation(self, allowed: bool, error: bool = False):
        """Record validation webhook request."""
        if error:
            result = 'error'
        elif allowed:
            result = 'allowed'
        else:
            result = 'denied'

        self.webhook_validations.labels(result=result).inc()

    def record_mutation(self, mutated: bool):
        """Record mutation webhook request."""
        mutated_str = 'yes' if mutated else 'no'
        self.webhook_mutations.labels(mutated=mutated_str).inc()

    def record_webhook_duration(self, webhook_type: str, duration: float):
        """Record webhook request duration."""
        self.webhook_duration.labels(type=webhook_type).observe(duration)

    # Health methods

    def set_healthy(self, healthy: bool):
        """Set operator health status."""
        self.operator_healthy.set(1 if healthy else 0)

    # Leader election methods

    def set_leader_election_enabled(self, enabled: bool):
        """Set whether leader election is enabled."""
        self.leader_election_enabled.set(1 if enabled else 0)

    def set_leader_status(self, is_leader: bool):
        """Set whether this instance is the leader."""
        self.is_leader.set(1 if is_leader else 0)

    def record_leader_transition(self):
        """Record a leadership transition (became leader or lost leadership)."""
        self.leader_transitions.inc()

    def record_lease_renewal(self, success: bool):
        """Record a lease renewal attempt."""
        result = 'success' if success else 'failure'
        self.lease_renewal_total.labels(result=result).inc()

    def record_lease_acquisition(self, success: bool):
        """Record a lease acquisition attempt."""
        result = 'success' if success else 'failure'
        self.lease_acquisition_total.labels(result=result).inc()

    def update_time_since_renewal(self, seconds: float):
        """Update time since last successful renewal."""
        self.time_since_last_renewal.set(seconds)

    # Dependency and DAG methods

    def update_dag_stats(self, namespace: str, stats: dict):
        """
        Update DAG statistics.

        Args:
            namespace: Kubernetes namespace
            stats: Dict with keys: total_jobs, ready_jobs, blocked_jobs,
                   max_depth, parallelism_potential
        """
        self.dag_total_jobs.labels(namespace=namespace).set(stats.get('total_jobs', 0))
        self.dag_ready_jobs.labels(namespace=namespace).set(stats.get('ready_jobs', 0))
        self.dag_blocked_jobs.labels(namespace=namespace).set(stats.get('blocked_jobs', 0))
        self.dag_max_depth.labels(namespace=namespace).set(stats.get('max_depth', 0))
        self.dag_parallelism_potential.labels(namespace=namespace).set(
            stats.get('parallelism_potential', 0)
        )

    def record_dependency_violation(self, namespace: str, violation_type: str):
        """
        Record a dependency validation failure.

        Args:
            namespace: Kubernetes namespace
            violation_type: Type of violation (cycle, missing_ref, self_dependency)
        """
        self.dependency_violations.labels(
            namespace=namespace,
            violation_type=violation_type
        ).inc()

    def record_failure_propagation(self, namespace: str, count: int):
        """
        Record dependency failure propagation.

        Args:
            namespace: Kubernetes namespace
            count: Number of jobs affected by propagation
        """
        self.dependency_failures_propagated.labels(namespace=namespace).inc(count)

    def record_job_dependencies(self, namespace: str, dependency_count: int):
        """
        Record number of dependencies for a job.

        Args:
            namespace: Kubernetes namespace
            dependency_count: Number of dependencies
        """
        self.job_dependency_count.labels(namespace=namespace).observe(dependency_count)

    def record_dependency_wait_time(self, namespace: str, wait_time: float):
        """
        Record time spent waiting for dependencies.

        Args:
            namespace: Kubernetes namespace
            wait_time: Wait time in seconds
        """
        self.dependency_wait_time.labels(namespace=namespace).observe(wait_time)

    # Migration-specific metrics (MigrationJob CRD)

    def __init_migration_metrics__(self):
        """Initialize migration-specific metrics."""
        # Migration lifecycle
        self.migrations_total = Counter(
            'hyper2kvm_migrations_total',
            'Total number of migration jobs created',
            ['namespace', 'source_type']
        )

        self.migrations_succeeded = Counter(
            'hyper2kvm_migrations_succeeded_total',
            'Total number of successful migrations',
            ['namespace', 'source_type']
        )

        self.migrations_failed = Counter(
            'hyper2kvm_migrations_failed_total',
            'Total number of failed migrations',
            ['namespace', 'source_type', 'reason']
        )

        self.migrations_active = Gauge(
            'hyper2kvm_migrations_active',
            'Number of currently active migrations',
            ['namespace', 'phase']
        )

        self.migration_duration_seconds = Histogram(
            'hyper2kvm_migration_duration_seconds',
            'Time taken to complete a migration',
            ['namespace', 'source_type'],
            buckets=[60, 300, 600, 1200, 1800, 3600, 7200]  # 1m, 5m, 10m, 20m, 30m, 1h, 2h
        )

        # Multi-disk metrics
        self.multi_disk_migrations_total = Counter(
            'hyper2kvm_multi_disk_migrations_total',
            'Total number of multi-disk migrations',
            ['namespace', 'disk_count']
        )

        self.disk_migration_duration_seconds = Histogram(
            'hyper2kvm_disk_migration_duration_seconds',
            'Time taken to migrate a single disk',
            ['namespace', 'disk_index'],
            buckets=[30, 60, 120, 300, 600, 1200, 1800]
        )

        # Dry-run metrics
        self.dry_run_validations_total = Counter(
            'hyper2kvm_dry_run_validations_total',
            'Total number of dry-run validations',
            ['namespace', 'result']  # result: success, failure
        )

        self.dry_run_issues_found = Counter(
            'hyper2kvm_dry_run_issues_found_total',
            'Total number of issues found in dry-run',
            ['namespace', 'issue_type']
        )

        # Conversion metrics
        self.conversion_compression_ratio = Histogram(
            'hyper2kvm_conversion_compression_ratio',
            'Compression ratio achieved (original_size / compressed_size)',
            ['namespace', 'format'],
            buckets=[1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
        )

        # VM metrics
        self.vms_created_total = Counter(
            'hyper2kvm_vms_created_total',
            'Total number of VMs created',
            ['namespace', 'auto_started']
        )

        self.vms_running = Gauge(
            'hyper2kvm_vms_running',
            'Number of VMs currently running',
            ['namespace']
        )

        # Live migration metrics (KubeVirt VirtualMachineInstanceMigration)
        self.live_migrations_total = Counter(
            'hyper2kvm_live_migrations_total',
            'Total number of live migrations initiated',
            ['namespace', 'source_node', 'target_node']
        )

        self.live_migrations_succeeded_total = Counter(
            'hyper2kvm_live_migrations_succeeded_total',
            'Total number of successful live migrations',
            ['namespace']
        )

        self.live_migrations_failed_total = Counter(
            'hyper2kvm_live_migrations_failed_total',
            'Total number of failed live migrations',
            ['namespace', 'reason']
        )

        self.live_migration_duration_seconds = Histogram(
            'hyper2kvm_live_migration_duration_seconds',
            'Duration of live migrations',
            ['namespace'],
            buckets=[10, 30, 60, 120, 300, 600, 900, 1200]  # 10s to 20min
        )

        self.live_migration_data_transferred_bytes = Histogram(
            'hyper2kvm_live_migration_data_transferred_bytes',
            'Amount of data transferred during live migration',
            ['namespace'],
            buckets=[100*1024*1024, 500*1024*1024, 1024*1024*1024,
                    5*1024*1024*1024, 10*1024*1024*1024,
                    25*1024*1024*1024, 50*1024*1024*1024]  # 100MB to 50GB
        )

        self.live_migration_downtime_ms = Histogram(
            'hyper2kvm_live_migration_downtime_ms',
            'VM downtime during live migration in milliseconds',
            ['namespace'],
            buckets=[10, 50, 100, 200, 500, 1000, 2000]  # 10ms to 2s
        )

        self.migration_policy_violations_total = Counter(
            'hyper2kvm_migration_policy_violations_total',
            'Total number of migration policy violations',
            ['namespace', 'policy_name', 'violation_type']
        )

        self.post_copy_activations_total = Counter(
            'hyper2kvm_post_copy_activations_total',
            'Total number of post-copy activations',
            ['namespace']
        )

        self.auto_converge_activations_total = Counter(
            'hyper2kvm_auto_converge_activations_total',
            'Total number of auto-converge activations',
            ['namespace']
        )

        self.live_migrations_active = Gauge(
            'hyper2kvm_live_migrations_active',
            'Number of currently active live migrations',
            ['namespace', 'phase']
        )

        self.migration_bandwidth_bytes_per_second = Gauge(
            'hyper2kvm_migration_bandwidth_bytes_per_second',
            'Current migration bandwidth in bytes per second',
            ['namespace', 'vm_name']
        )

        self.migration_dirty_rate_bytes_per_second = Gauge(
            'hyper2kvm_migration_dirty_rate_bytes_per_second',
            'Current memory dirty rate in bytes per second',
            ['namespace', 'vm_name']
        )

    # Migration methods

    def record_migration_created(self, namespace: str, source_type: str):
        """Record that a migration was created."""
        self.migrations_total.labels(
            namespace=namespace,
            source_type=source_type
        ).inc()

    def record_migration_succeeded(self, namespace: str, source_type: str, duration: float):
        """Record a successful migration."""
        self.migrations_succeeded.labels(
            namespace=namespace,
            source_type=source_type
        ).inc()
        self.migration_duration_seconds.labels(
            namespace=namespace,
            source_type=source_type
        ).observe(duration)

    def record_migration_failed(self, namespace: str, source_type: str, reason: str):
        """Record a failed migration."""
        self.migrations_failed.labels(
            namespace=namespace,
            source_type=source_type,
            reason=reason
        ).inc()

    def update_active_migrations(self, namespace: str, phase: str, count: int):
        """Update the count of active migrations in a phase."""
        self.migrations_active.labels(
            namespace=namespace,
            phase=phase
        ).set(count)

    def record_multi_disk_migration(self, namespace: str, disk_count: int):
        """Record a multi-disk migration."""
        self.multi_disk_migrations_total.labels(
            namespace=namespace,
            disk_count=str(disk_count)
        ).inc()

    def record_disk_migration_duration(self, namespace: str, disk_index: int, duration: float):
        """Record duration for migrating a single disk."""
        self.disk_migration_duration_seconds.labels(
            namespace=namespace,
            disk_index=str(disk_index)
        ).observe(duration)

    def record_dry_run_validation(self, namespace: str, success: bool):
        """Record a dry-run validation."""
        result = 'success' if success else 'failure'
        self.dry_run_validations_total.labels(
            namespace=namespace,
            result=result
        ).inc()

    def record_dry_run_issue(self, namespace: str, issue_type: str):
        """Record an issue found during dry-run."""
        self.dry_run_issues_found.labels(
            namespace=namespace,
            issue_type=issue_type
        ).inc()

    def record_compression_ratio(self, namespace: str, format: str, ratio: float):
        """Record compression ratio."""
        self.conversion_compression_ratio.labels(
            namespace=namespace,
            format=format
        ).observe(ratio)

    def record_vm_created(self, namespace: str, auto_started: bool):
        """Record VM creation."""
        self.vms_created_total.labels(
            namespace=namespace,
            auto_started=str(auto_started).lower()
        ).inc()

    def update_running_vms(self, namespace: str, count: int):
        """Update running VM count."""
        self.vms_running.labels(namespace=namespace).set(count)

    # Live migration methods

    def record_live_migration_started(self, namespace: str, source_node: str, target_node: str):
        """Record that a live migration was started."""
        self.live_migrations_total.labels(
            namespace=namespace,
            source_node=source_node,
            target_node=target_node
        ).inc()

    def record_live_migration_succeeded(self, namespace: str, duration: float,
                                       data_transferred: int = 0, downtime_ms: float = 0):
        """Record a successful live migration."""
        self.live_migrations_succeeded_total.labels(namespace=namespace).inc()
        self.live_migration_duration_seconds.labels(namespace=namespace).observe(duration)
        if data_transferred > 0:
            self.live_migration_data_transferred_bytes.labels(namespace=namespace).observe(data_transferred)
        if downtime_ms > 0:
            self.live_migration_downtime_ms.labels(namespace=namespace).observe(downtime_ms)

    def record_live_migration_failed(self, namespace: str, reason: str):
        """Record a failed live migration."""
        self.live_migrations_failed_total.labels(
            namespace=namespace,
            reason=reason
        ).inc()

    def update_active_live_migrations(self, namespace: str, phase: str, count: int):
        """Update the count of active live migrations in a phase."""
        self.live_migrations_active.labels(
            namespace=namespace,
            phase=phase
        ).set(count)

    def record_migration_policy_violation(self, namespace: str, policy_name: str, violation_type: str):
        """Record a migration policy violation."""
        self.migration_policy_violations_total.labels(
            namespace=namespace,
            policy_name=policy_name,
            violation_type=violation_type
        ).inc()

    def record_post_copy_activation(self, namespace: str):
        """Record that post-copy was activated."""
        self.post_copy_activations_total.labels(namespace=namespace).inc()

    def record_auto_converge_activation(self, namespace: str):
        """Record that auto-converge was activated."""
        self.auto_converge_activations_total.labels(namespace=namespace).inc()

    def update_migration_bandwidth(self, namespace: str, vm_name: str, bandwidth_bps: float):
        """Update current migration bandwidth."""
        self.migration_bandwidth_bytes_per_second.labels(
            namespace=namespace,
            vm_name=vm_name
        ).set(bandwidth_bps)

    def update_migration_dirty_rate(self, namespace: str, vm_name: str, dirty_rate_bps: float):
        """Update current memory dirty rate."""
        self.migration_dirty_rate_bytes_per_second.labels(
            namespace=namespace,
            vm_name=vm_name
        ).set(dirty_rate_bps)
