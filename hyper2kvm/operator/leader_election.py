"""
Leader Election for Kubernetes Operator

Implements leader election using Kubernetes Lease API to enable
high-availability multi-replica operator deployments.

Features:
- Leader election using coordination.k8s.io/v1 Lease
- Automatic leader failover
- Graceful leadership handoff
- Health check integration
- Metrics for leader status

Usage:
    from hyper2kvm.operator.leader_election import LeaderElection

    leader = LeaderElection(
        name="hyper2kvm-operator",
        namespace="hyper2kvm-system",
        identity="operator-pod-xyz"
    )

    if leader.is_leader():
        # Perform leader-only operations
        pass
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class LeaderElection:
    """
    Leader election using Kubernetes Lease API.

    Ensures only one operator replica actively reconciles resources
    while other replicas stand by for failover.
    """

    def __init__(
        self,
        name: str = "hyper2kvm-operator-leader",
        namespace: Optional[str] = None,
        identity: Optional[str] = None,
        lease_duration: int = 15,
        renew_deadline: int = 10,
        retry_period: int = 2
    ):
        """
        Initialize leader election.

        Args:
            name: Name of the lease object
            namespace: Namespace for the lease (defaults to current namespace)
            identity: Identity of this operator instance (defaults to pod name)
            lease_duration: Duration (seconds) for which leader holds the lease
            renew_deadline: Duration (seconds) leader has to renew before losing leadership
            retry_period: Duration (seconds) between lease acquisition attempts
        """
        self.name = name
        self.namespace = namespace or self._get_namespace()
        self.identity = identity or self._get_identity()

        self.lease_duration = lease_duration
        self.renew_deadline = renew_deadline
        self.retry_period = retry_period

        # Kubernetes API client
        self.coordination_api = client.CoordinationV1Api()

        # State
        self._is_leader = False
        self._lease_holder = None
        self._last_renew_time = None
        self._renew_task = None

        logger.info(
            f"Leader election initialized: name={self.name}, "
            f"namespace={self.namespace}, identity={self.identity}"
        )

    def _get_namespace(self) -> str:
        """Get current namespace from environment or default."""
        namespace = os.environ.get("OPERATOR_NAMESPACE")
        if namespace:
            return namespace

        # Try to read from mounted service account
        try:
            with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            return "default"

    def _get_identity(self) -> str:
        """Get identity for this operator instance."""
        # Use pod name if available
        pod_name = os.environ.get("OPERATOR_POD_NAME")
        if pod_name:
            return pod_name

        # Fallback to hostname
        import socket
        return socket.gethostname()

    async def start(self):
        """
        Start leader election process.

        Attempts to acquire lease and starts renewal loop if successful.
        """
        logger.info(f"Starting leader election for {self.identity}")

        while True:
            try:
                if await self._try_acquire_or_renew():
                    if not self._is_leader:
                        logger.info(f"🎉 {self.identity} became leader!")
                        self._is_leader = True

                    # Start renewal loop if not already running
                    if not self._renew_task or self._renew_task.done():
                        self._renew_task = asyncio.create_task(self._renew_loop())
                else:
                    if self._is_leader:
                        logger.warning(f"❌ {self.identity} lost leadership to {self._lease_holder}")
                        self._is_leader = False

                        # Cancel renewal loop
                        if self._renew_task and not self._renew_task.done():
                            self._renew_task.cancel()

                # Wait before next attempt
                await asyncio.sleep(self.retry_period)

            except asyncio.CancelledError:
                logger.info("Leader election cancelled")
                break
            except Exception as e:
                logger.error(f"Leader election error: {e}", exc_info=True)
                await asyncio.sleep(self.retry_period)

    async def _try_acquire_or_renew(self) -> bool:
        """
        Try to acquire or renew the lease.

        Returns:
            True if this instance is the leader, False otherwise
        """
        try:
            # Try to get existing lease
            try:
                lease = self.coordination_api.read_namespaced_lease(
                    name=self.name,
                    namespace=self.namespace
                )

                # Check if lease is held by this instance
                if lease.spec.holder_identity == self.identity:
                    # Renew lease
                    return await self._renew_lease(lease)
                else:
                    # Check if lease is expired
                    if self._is_lease_expired(lease):
                        # Try to take over
                        logger.info(
                            f"Lease expired (holder: {lease.spec.holder_identity}), "
                            f"attempting takeover"
                        )
                        return await self._acquire_lease(lease)
                    else:
                        # Lease held by another instance
                        self._lease_holder = lease.spec.holder_identity
                        return False

            except ApiException as e:
                if e.status == 404:
                    # Lease doesn't exist, create it
                    logger.info("Lease not found, creating new lease")
                    return await self._create_lease()
                else:
                    raise

        except Exception as e:
            logger.error(f"Error acquiring/renewing lease: {e}")
            return False

    def _is_lease_expired(self, lease) -> bool:
        """
        Check if a lease is expired.

        Args:
            lease: Kubernetes Lease object

        Returns:
            True if lease is expired, False otherwise
        """
        if not lease.spec.renew_time:
            return True

        renew_time = lease.spec.renew_time
        now = datetime.utcnow()

        # Lease is expired if renew_time + lease_duration < now
        expiry_time = renew_time + timedelta(seconds=self.lease_duration)

        return expiry_time < now

    async def _create_lease(self) -> bool:
        """
        Create a new lease.

        Returns:
            True if lease was created successfully, False otherwise
        """
        try:
            now = datetime.utcnow()

            lease = client.V1Lease(
                metadata=client.V1ObjectMeta(
                    name=self.name,
                    namespace=self.namespace
                ),
                spec=client.V1LeaseSpec(
                    holder_identity=self.identity,
                    lease_duration_seconds=self.lease_duration,
                    acquire_time=now,
                    renew_time=now,
                    lease_transitions=0
                )
            )

            self.coordination_api.create_namespaced_lease(
                namespace=self.namespace,
                body=lease
            )

            self._last_renew_time = now
            logger.info(f"Created lease {self.name}")
            return True

        except ApiException as e:
            if e.status == 409:
                # Conflict - another instance created the lease
                logger.debug("Lease creation conflict, will retry")
                return False
            else:
                logger.error(f"Error creating lease: {e}")
                return False

    async def _acquire_lease(self, lease) -> bool:
        """
        Acquire an existing lease (takeover from expired holder).

        Args:
            lease: Existing Kubernetes Lease object

        Returns:
            True if lease was acquired successfully, False otherwise
        """
        try:
            now = datetime.utcnow()

            # Update lease to this instance
            lease.spec.holder_identity = self.identity
            lease.spec.acquire_time = now
            lease.spec.renew_time = now
            lease.spec.lease_transitions = (lease.spec.lease_transitions or 0) + 1

            self.coordination_api.replace_namespaced_lease(
                name=self.name,
                namespace=self.namespace,
                body=lease
            )

            self._last_renew_time = now
            logger.info(f"Acquired lease {self.name} (transitions: {lease.spec.lease_transitions})")
            return True

        except ApiException as e:
            if e.status == 409:
                # Conflict - another instance took the lease
                logger.debug("Lease acquisition conflict, will retry")
                return False
            else:
                logger.error(f"Error acquiring lease: {e}")
                return False

    async def _renew_lease(self, lease) -> bool:
        """
        Renew an existing lease held by this instance.

        Args:
            lease: Kubernetes Lease object held by this instance

        Returns:
            True if lease was renewed successfully, False otherwise
        """
        try:
            now = datetime.utcnow()

            # Update renew time
            lease.spec.renew_time = now

            self.coordination_api.replace_namespaced_lease(
                name=self.name,
                namespace=self.namespace,
                body=lease
            )

            self._last_renew_time = now
            logger.debug(f"Renewed lease {self.name}")
            return True

        except ApiException as e:
            if e.status == 409 or e.status == 404:
                # Conflict or lease deleted - lost leadership
                logger.warning("Lease renewal conflict or deleted")
                return False
            else:
                logger.error(f"Error renewing lease: {e}")
                return False

    async def _renew_loop(self):
        """Background loop to renew the lease periodically."""
        while True:
            try:
                # Sleep for retry_period before renewing
                await asyncio.sleep(self.retry_period)

                if not self._is_leader:
                    break

                # Renew lease
                lease = self.coordination_api.read_namespaced_lease(
                    name=self.name,
                    namespace=self.namespace
                )

                if lease.spec.holder_identity != self.identity:
                    logger.warning("Lease holder changed during renewal")
                    self._is_leader = False
                    break

                if not await self._renew_lease(lease):
                    logger.error("Failed to renew lease")
                    self._is_leader = False
                    break

            except asyncio.CancelledError:
                logger.info("Lease renewal loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in renewal loop: {e}", exc_info=True)
                await asyncio.sleep(self.retry_period)

    def is_leader(self) -> bool:
        """
        Check if this instance is currently the leader.

        Returns:
            True if this instance holds the lease, False otherwise
        """
        return self._is_leader

    def get_leader(self) -> Optional[str]:
        """
        Get the identity of the current leader.

        Returns:
            Identity of the current leader, or None if unknown
        """
        if self._is_leader:
            return self.identity
        return self._lease_holder

    def get_status(self) -> dict:
        """
        Get leader election status information.

        Returns:
            Dictionary with status information
        """
        return {
            "is_leader": self._is_leader,
            "identity": self.identity,
            "leader": self.get_leader(),
            "last_renew_time": self._last_renew_time.isoformat() if self._last_renew_time else None,
            "lease_name": self.name,
            "namespace": self.namespace
        }

    async def release(self):
        """
        Release the lease if held by this instance.

        This is typically called during graceful shutdown.
        """
        if not self._is_leader:
            logger.info("Not leader, nothing to release")
            return

        try:
            logger.info(f"Releasing lease {self.name}")

            # Delete the lease to allow immediate takeover
            self.coordination_api.delete_namespaced_lease(
                name=self.name,
                namespace=self.namespace
            )

            self._is_leader = False
            logger.info("Lease released successfully")

        except ApiException as e:
            if e.status == 404:
                logger.debug("Lease already deleted")
            else:
                logger.error(f"Error releasing lease: {e}")
        except Exception as e:
            logger.error(f"Error releasing lease: {e}", exc_info=True)
