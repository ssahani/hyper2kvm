"""
Unit tests for leader election functionality.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from kubernetes import client
from kubernetes.client.rest import ApiException

from hyper2kvm.operator.leader_election import LeaderElection


class TestLeaderElection:
    """Test leader election functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_api = Mock()

    @pytest.mark.asyncio
    async def test_create_lease(self):
        """Test creating a new lease."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock successful lease creation
            mock_api.create_namespaced_lease.return_value = None

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            result = await leader._create_lease()

            assert result is True
            mock_api.create_namespaced_lease.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_lease_conflict(self):
        """Test lease creation conflict (another instance created it)."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock 409 Conflict error
            mock_api.create_namespaced_lease.side_effect = ApiException(status=409)

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            result = await leader._create_lease()

            assert result is False

    def test_is_lease_expired(self):
        """Test checking if a lease is expired."""
        leader = LeaderElection(
            name="test-lease",
            namespace="default",
            identity="pod-1",
            lease_duration=15
        )

        # Create expired lease
        expired_lease = Mock()
        expired_lease.spec.renew_time = datetime.utcnow() - timedelta(seconds=20)

        assert leader._is_lease_expired(expired_lease) is True

        # Create valid lease
        valid_lease = Mock()
        valid_lease.spec.renew_time = datetime.utcnow() - timedelta(seconds=5)

        assert leader._is_lease_expired(valid_lease) is False

        # Lease with no renew time is expired
        no_renew_lease = Mock()
        no_renew_lease.spec.renew_time = None

        assert leader._is_lease_expired(no_renew_lease) is True

    @pytest.mark.asyncio
    async def test_acquire_lease(self):
        """Test acquiring an expired lease."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock successful lease replacement
            mock_api.replace_namespaced_lease.return_value = None

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            # Create lease held by another instance
            lease = Mock()
            lease.spec.holder_identity = "pod-2"
            lease.spec.lease_transitions = 5

            result = await leader._acquire_lease(lease)

            assert result is True
            assert lease.spec.holder_identity == "pod-1"
            assert lease.spec.lease_transitions == 6
            mock_api.replace_namespaced_lease.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_lease_conflict(self):
        """Test lease acquisition conflict."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock 409 Conflict error
            mock_api.replace_namespaced_lease.side_effect = ApiException(status=409)

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            lease = Mock()
            lease.spec.holder_identity = "pod-2"

            result = await leader._acquire_lease(lease)

            assert result is False

    @pytest.mark.asyncio
    async def test_renew_lease(self):
        """Test renewing a lease held by this instance."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock successful lease renewal
            mock_api.replace_namespaced_lease.return_value = None

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            lease = Mock()
            lease.spec.holder_identity = "pod-1"
            lease.spec.renew_time = datetime.utcnow() - timedelta(seconds=5)

            result = await leader._renew_lease(lease)

            assert result is True
            assert lease.spec.renew_time is not None
            mock_api.replace_namespaced_lease.assert_called_once()

    @pytest.mark.asyncio
    async def test_renew_lease_conflict(self):
        """Test lease renewal conflict (lost leadership)."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock 409 Conflict error
            mock_api.replace_namespaced_lease.side_effect = ApiException(status=409)

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            lease = Mock()
            lease.spec.holder_identity = "pod-1"

            result = await leader._renew_lease(lease)

            assert result is False

    def test_is_leader(self):
        """Test checking leadership status."""
        leader = LeaderElection(
            name="test-lease",
            namespace="default",
            identity="pod-1"
        )

        # Initially not leader
        assert leader.is_leader() is False

        # Set as leader
        leader._is_leader = True
        assert leader.is_leader() is True

    def test_get_leader(self):
        """Test getting current leader identity."""
        leader = LeaderElection(
            name="test-lease",
            namespace="default",
            identity="pod-1"
        )

        # Not leader, no holder known
        assert leader.get_leader() is None

        # Another instance is leader
        leader._lease_holder = "pod-2"
        assert leader.get_leader() == "pod-2"

        # This instance is leader
        leader._is_leader = True
        assert leader.get_leader() == "pod-1"

    def test_get_status(self):
        """Test getting leader election status."""
        leader = LeaderElection(
            name="test-lease",
            namespace="default",
            identity="pod-1"
        )

        status = leader.get_status()

        assert status["is_leader"] is False
        assert status["identity"] == "pod-1"
        assert status["lease_name"] == "test-lease"
        assert status["namespace"] == "default"

        # Set as leader
        leader._is_leader = True
        leader._last_renew_time = datetime.utcnow()

        status = leader.get_status()

        assert status["is_leader"] is True
        assert status["last_renew_time"] is not None

    @pytest.mark.asyncio
    async def test_release_lease(self):
        """Test releasing lease on shutdown."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock successful lease deletion
            mock_api.delete_namespaced_lease.return_value = None

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            # Set as leader
            leader._is_leader = True

            await leader.release()

            assert leader._is_leader is False
            mock_api.delete_namespaced_lease.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_lease_not_leader(self):
        """Test releasing lease when not leader (no-op)."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            # Not leader
            leader._is_leader = False

            await leader.release()

            # No API call should be made
            mock_api.delete_namespaced_lease.assert_not_called()

    @pytest.mark.asyncio
    async def test_try_acquire_or_renew_no_lease(self):
        """Test acquiring lease when none exists."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock lease not found
            mock_api.read_namespaced_lease.side_effect = ApiException(status=404)
            mock_api.create_namespaced_lease.return_value = None

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            result = await leader._try_acquire_or_renew()

            assert result is True
            mock_api.create_namespaced_lease.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_acquire_or_renew_held_by_self(self):
        """Test renewing lease held by this instance."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock lease held by this instance
            lease = Mock()
            lease.spec.holder_identity = "pod-1"
            lease.spec.renew_time = datetime.utcnow()

            mock_api.read_namespaced_lease.return_value = lease
            mock_api.replace_namespaced_lease.return_value = None

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1"
            )

            result = await leader._try_acquire_or_renew()

            assert result is True
            mock_api.replace_namespaced_lease.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_acquire_or_renew_held_by_other_expired(self):
        """Test taking over expired lease from another instance."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock expired lease held by another instance
            lease = Mock()
            lease.spec.holder_identity = "pod-2"
            lease.spec.renew_time = datetime.utcnow() - timedelta(seconds=30)
            lease.spec.lease_transitions = 2

            mock_api.read_namespaced_lease.return_value = lease
            mock_api.replace_namespaced_lease.return_value = None

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1",
                lease_duration=15
            )

            result = await leader._try_acquire_or_renew()

            assert result is True
            # Verify lease was updated
            assert lease.spec.holder_identity == "pod-1"
            assert lease.spec.lease_transitions == 3

    @pytest.mark.asyncio
    async def test_try_acquire_or_renew_held_by_other_valid(self):
        """Test standby when lease held by another instance and valid."""
        with patch('hyper2kvm.operator.leader_election.client.CoordinationV1Api') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api

            # Mock valid lease held by another instance
            lease = Mock()
            lease.spec.holder_identity = "pod-2"
            lease.spec.renew_time = datetime.utcnow() - timedelta(seconds=5)

            mock_api.read_namespaced_lease.return_value = lease

            leader = LeaderElection(
                name="test-lease",
                namespace="default",
                identity="pod-1",
                lease_duration=15
            )

            result = await leader._try_acquire_or_renew()

            assert result is False
            assert leader._lease_holder == "pod-2"
            # Should not try to update lease
            mock_api.replace_namespaced_lease.assert_not_called()


class TestLeaderAwareController:
    """Test leader-aware controller wrapper."""

    @pytest.mark.asyncio
    async def test_leader_election_disabled(self):
        """Test controller with leader election disabled."""
        from hyper2kvm.operator.leader_aware_controller import LeaderAwareController

        controller = LeaderAwareController()

        # Start with leader election disabled
        await controller.start_leader_election(enabled=False)

        # Should always be leader
        assert controller.is_leader() is True

        status = controller.get_leader_status()
        assert status["enabled"] is False
        assert status["is_leader"] is True
        assert status["mode"] == "single-replica"

    @pytest.mark.asyncio
    async def test_get_leader_status_enabled(self):
        """Test getting leader status when election enabled."""
        from hyper2kvm.operator.leader_aware_controller import LeaderAwareController

        with patch('hyper2kvm.operator.leader_aware_controller.LeaderElection') as mock_election_class:
            mock_election = Mock()
            mock_election.is_leader.return_value = True
            mock_election.get_status.return_value = {
                "is_leader": True,
                "identity": "pod-1",
                "leader": "pod-1"
            }
            mock_election.start = AsyncMock()

            mock_election_class.return_value = mock_election

            controller = LeaderAwareController()
            await controller.start_leader_election(enabled=True)

            status = controller.get_leader_status()

            assert status["enabled"] is True
            assert status["is_leader"] is True

    @pytest.mark.asyncio
    async def test_require_leadership_decorator(self):
        """Test require_leadership decorator."""
        from hyper2kvm.operator.leader_aware_controller import require_leadership, leader_controller

        # Set as leader
        leader_controller.leader_election = Mock()
        leader_controller.leader_election.is_leader.return_value = True

        @require_leadership
        async def test_func():
            return "executed"

        result = await test_func()
        assert result == "executed"

        # Set as standby
        leader_controller.leader_election.is_leader.return_value = False
        leader_controller.leader_election.get_leader.return_value = "pod-2"

        result = await test_func()
        assert result is None  # Should not execute
