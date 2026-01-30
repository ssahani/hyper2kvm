"""
Leader-Aware Operator Controller Wrapper

Integrates leader election with the operator controller to ensure
only the leader replica performs reconciliation.

Usage:
    The controller automatically handles leader election. Only the leader
    replica will actively reconcile MigrationJob resources.
"""

import asyncio
import logging
import os
from typing import Optional

import kopf

from hyper2kvm.operator.leader_election import LeaderElection

logger = logging.getLogger(__name__)


class LeaderAwareController:
    """
    Wrapper for operator controller that integrates leader election.

    Ensures only the leader replica performs reconciliations while
    other replicas stand by for failover.
    """

    def __init__(self):
        """Initialize leader-aware controller."""
        self.leader_election: Optional[LeaderElection] = None
        self._election_task: Optional[asyncio.Task] = None

    async def start_leader_election(
        self,
        name: str = "hyper2kvm-operator-leader",
        namespace: Optional[str] = None,
        enabled: bool = True
    ):
        """
        Start leader election process.

        Args:
            name: Name of the lease object
            namespace: Namespace for the lease
            enabled: Whether leader election is enabled
        """
        if not enabled:
            logger.info("Leader election disabled, assuming single replica")
            return

        logger.info(f"Starting leader election: {name}")

        self.leader_election = LeaderElection(
            name=name,
            namespace=namespace,
            lease_duration=15,
            renew_deadline=10,
            retry_period=2
        )

        # Start election process in background
        self._election_task = asyncio.create_task(
            self.leader_election.start()
        )

        # Wait briefly for initial leader determination
        await asyncio.sleep(3)

        if self.is_leader():
            logger.info("🎉 This replica is the leader")
        else:
            logger.info(f"⏸️  Standby replica (leader: {self.leader_election.get_leader()})")

    def is_leader(self) -> bool:
        """
        Check if this instance is the leader.

        Returns:
            True if leader or leader election disabled, False if standby
        """
        # If leader election not enabled, assume we're the leader
        if not self.leader_election:
            return True

        return self.leader_election.is_leader()

    def get_leader_status(self) -> dict:
        """
        Get leader election status.

        Returns:
            Dictionary with leader status information
        """
        if not self.leader_election:
            return {
                "enabled": False,
                "is_leader": True,
                "mode": "single-replica"
            }

        status = self.leader_election.get_status()
        status["enabled"] = True
        return status

    async def stop_leader_election(self):
        """
        Stop leader election and release lease if held.
        """
        if not self.leader_election:
            return

        logger.info("Stopping leader election")

        # Release lease if we're the leader
        if self.is_leader():
            await self.leader_election.release()

        # Cancel election task
        if self._election_task and not self._election_task.done():
            self._election_task.cancel()
            try:
                await self._election_task
            except asyncio.CancelledError:
                pass

        logger.info("Leader election stopped")


# Global instance
leader_controller = LeaderAwareController()


def require_leadership(func):
    """
    Decorator to ensure operation only runs on leader replica.

    Usage:
        @require_leadership
        async def reconcile_job(...):
            # This only runs on leader
            pass
    """
    async def wrapper(*args, **kwargs):
        if not leader_controller.is_leader():
            logger.debug(
                f"Skipping {func.__name__} - not leader "
                f"(leader: {leader_controller.leader_election.get_leader() if leader_controller.leader_election else 'unknown'})"
            )
            return None

        return await func(*args, **kwargs)

    return wrapper


@kopf.on.startup()
async def startup_with_leader_election(settings: kopf.OperatorSettings, **kwargs):
    """
    Operator startup with leader election.

    Initializes leader election before operator starts processing events.
    """
    logger.info("Operator starting up...")

    # Check if leader election is enabled
    leader_election_enabled = os.environ.get("LEADER_ELECTION_ENABLED", "true").lower() == "true"
    namespace = os.environ.get("OPERATOR_NAMESPACE")

    # Start leader election
    await leader_controller.start_leader_election(
        name="hyper2kvm-operator-leader",
        namespace=namespace,
        enabled=leader_election_enabled
    )

    # Configure Kopf peering for additional coordination
    if leader_election_enabled:
        settings.peering.name = "hyper2kvm-operator"
        settings.peering.mandatory = True
        logger.info("Kopf peering enabled for operator coordination")

    logger.info(f"Operator startup complete (leader: {leader_controller.is_leader()})")


@kopf.on.cleanup()
async def cleanup_with_leader_election(**kwargs):
    """
    Operator cleanup with leader election.

    Releases lease on graceful shutdown.
    """
    logger.info("Operator shutting down...")

    await leader_controller.stop_leader_election()

    logger.info("Operator shutdown complete")
