"""
Tests for Kubernetes operator leader election and HA
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from hyper2kvm.operator.leader_election import LeaderElector
from hyper2kvm.operator.leader_aware_controller import LeaderAwareController


class TestLeaderElection:
    """Test leader election functionality"""

    @pytest.fixture
    def mock_k8s_client(self):
        """Create mock Kubernetes client"""
        mock_client = Mock()
        return mock_client

    @pytest.fixture
    def leader_elector(self, mock_k8s_client):
        """Create LeaderElector instance"""
        with patch('hyper2kvm.operator.leader_election.client', mock_k8s_client):
            elector = LeaderElector(
                name="test-operator",
                namespace="test-namespace",
                identity="test-pod-1"
            )
            return elector

    def test_leader_elector_initialization(self, leader_elector):
        """Test leader elector initializes correctly"""
        assert leader_elector.name == "test-operator"
        assert leader_elector.namespace == "test-namespace"
        assert leader_elector.identity == "test-pod-1"
        assert leader_elector.is_leader is False

    def test_acquire_leadership(self, leader_elector, mock_k8s_client):
        """Test acquiring leadership"""
        # Mock successful lease acquisition
        mock_lease = Mock()
        mock_lease.spec.holder_identity = None

        with patch.object(leader_elector, 'get_lease', return_value=mock_lease):
            with patch.object(leader_elector, 'update_lease', return_value=True):
                success = leader_elector.try_acquire_or_renew()

                assert success is True
                assert leader_elector.is_leader is True

    def test_leadership_already_held(self, leader_elector):
        """Test when leadership is already held by another instance"""
        # Mock lease held by different identity
        mock_lease = Mock()
        mock_lease.spec.holder_identity = "other-pod"
        mock_lease.spec.lease_duration_seconds = 15
        mock_lease.spec.renew_time = time.time()

        with patch.object(leader_elector, 'get_lease', return_value=mock_lease):
            success = leader_elector.try_acquire_or_renew()

            assert success is False
            assert leader_elector.is_leader is False

    def test_renew_leadership(self, leader_elector):
        """Test renewing existing leadership"""
        leader_elector.is_leader = True

        # Mock lease held by this identity
        mock_lease = Mock()
        mock_lease.spec.holder_identity = "test-pod-1"
        mock_lease.spec.lease_duration_seconds = 15
        mock_lease.spec.renew_time = time.time() - 5  # 5 seconds ago

        with patch.object(leader_elector, 'get_lease', return_value=mock_lease):
            with patch.object(leader_elector, 'update_lease', return_value=True):
                success = leader_elector.try_acquire_or_renew()

                assert success is True
                assert leader_elector.is_leader is True

    def test_release_leadership(self, leader_elector):
        """Test releasing leadership"""
        leader_elector.is_leader = True

        with patch.object(leader_elector, 'delete_lease', return_value=True):
            leader_elector.release()

            assert leader_elector.is_leader is False

    def test_leadership_lost_on_failed_renewal(self, leader_elector):
        """Test losing leadership when renewal fails"""
        leader_elector.is_leader = True

        # Mock failed renewal
        with patch.object(leader_elector, 'try_acquire_or_renew', return_value=False):
            leader_elector.try_acquire_or_renew()

            assert leader_elector.is_leader is False

    def test_lease_expiration(self, leader_elector):
        """Test lease expiration logic"""
        # Mock expired lease
        mock_lease = Mock()
        mock_lease.spec.holder_identity = "other-pod"
        mock_lease.spec.lease_duration_seconds = 15
        mock_lease.spec.renew_time = time.time() - 20  # Expired

        is_expired = leader_elector.is_lease_expired(mock_lease)

        assert is_expired is True

    def test_lease_not_expired(self, leader_elector):
        """Test lease not expired"""
        # Mock valid lease
        mock_lease = Mock()
        mock_lease.spec.holder_identity = "other-pod"
        mock_lease.spec.lease_duration_seconds = 15
        mock_lease.spec.renew_time = time.time() - 5  # Still valid

        is_expired = leader_elector.is_lease_expired(mock_lease)

        assert is_expired is False

    def test_leadership_transition(self, leader_elector):
        """Test leadership transition between instances"""
        # Start as follower
        assert leader_elector.is_leader is False

        # Acquire leadership
        mock_lease = Mock()
        mock_lease.spec.holder_identity = None

        with patch.object(leader_elector, 'get_lease', return_value=mock_lease):
            with patch.object(leader_elector, 'update_lease', return_value=True):
                leader_elector.try_acquire_or_renew()

        assert leader_elector.is_leader is True

        # Release leadership
        with patch.object(leader_elector, 'delete_lease', return_value=True):
            leader_elector.release()

        assert leader_elector.is_leader is False


class TestLeaderAwareController:
    """Test leader-aware controller"""

    @pytest.fixture
    def controller(self):
        """Create LeaderAwareController instance"""
        return LeaderAwareController(
            namespace="test-namespace",
            identity="test-pod-1"
        )

    def test_controller_starts_as_follower(self, controller):
        """Test controller starts in follower mode"""
        assert controller.is_leader() is False

    def test_leader_election_callback(self, controller):
        """Test callback when becoming leader"""
        callback_called = []

        def on_become_leader():
            callback_called.append(True)

        controller.on_start_leading = on_become_leader

        # Simulate becoming leader
        with patch.object(controller.elector, 'is_leader', True):
            controller.on_started_leading()

        assert len(callback_called) == 1

    def test_follower_callback(self, controller):
        """Test callback when becoming follower"""
        callback_called = []

        def on_become_follower():
            callback_called.append(True)

        controller.on_stop_leading = on_become_follower

        # Simulate losing leadership
        controller.on_stopped_leading()

        assert len(callback_called) == 1

    def test_leader_processes_events(self, controller):
        """Test leader processes events"""
        with patch.object(controller, 'is_leader', return_value=True):
            # Leader should process
            should_process = controller.should_process_event()
            assert should_process is True

    def test_follower_skips_events(self, controller):
        """Test follower skips event processing"""
        with patch.object(controller, 'is_leader', return_value=False):
            # Follower should not process
            should_process = controller.should_process_event()
            assert should_process is False

    def test_leadership_change_handling(self, controller):
        """Test handling leadership changes"""
        # Start as follower
        assert controller.is_leader() is False

        # Become leader
        with patch.object(controller.elector, 'try_acquire_or_renew', return_value=True):
            with patch.object(controller.elector, 'is_leader', True):
                controller.elector.try_acquire_or_renew()
                controller.on_started_leading()

        # Lose leadership
        with patch.object(controller.elector, 'is_leader', False):
            controller.on_stopped_leading()

        assert controller.is_leader() is False


class TestHighAvailability:
    """Test HA scenarios"""

    def test_multiple_replicas_election(self):
        """Test leader election with multiple replicas"""
        # Create multiple elector instances
        electors = [
            LeaderElector(
                name="test-operator",
                namespace="test-namespace",
                identity=f"test-pod-{i}"
            )
            for i in range(3)
        ]

        # Mock lease object
        mock_lease = Mock()
        mock_lease.spec.holder_identity = None

        # First instance acquires leadership
        with patch.object(electors[0], 'get_lease', return_value=mock_lease):
            with patch.object(electors[0], 'update_lease', return_value=True):
                success = electors[0].try_acquire_or_renew()

        assert success is True
        assert electors[0].is_leader is True

        # Other instances should fail to acquire
        mock_lease.spec.holder_identity = "test-pod-0"
        for elector in electors[1:]:
            with patch.object(elector, 'get_lease', return_value=mock_lease):
                success = elector.try_acquire_or_renew()
                assert success is False
                assert elector.is_leader is False

    def test_leader_failover(self):
        """Test failover when leader becomes unavailable"""
        # Create two electors
        leader = LeaderElector(
            name="test-operator",
            namespace="test-namespace",
            identity="leader-pod"
        )
        standby = LeaderElector(
            name="test-operator",
            namespace="test-namespace",
            identity="standby-pod"
        )

        # Leader acquires lease
        mock_lease = Mock()
        mock_lease.spec.holder_identity = "leader-pod"
        mock_lease.spec.lease_duration_seconds = 15
        mock_lease.spec.renew_time = time.time()

        leader.is_leader = True

        # Leader fails (lease expires)
        mock_lease.spec.renew_time = time.time() - 20  # Expired

        # Standby should be able to acquire
        with patch.object(standby, 'get_lease', return_value=mock_lease):
            with patch.object(standby, 'is_lease_expired', return_value=True):
                with patch.object(standby, 'update_lease', return_value=True):
                    success = standby.try_acquire_or_renew()

        assert success is True
        assert standby.is_leader is True

    def test_split_brain_prevention(self):
        """Test prevention of split-brain scenario"""
        # Create two electors
        elector1 = LeaderElector(
            name="test-operator",
            namespace="test-namespace",
            identity="pod-1"
        )
        elector2 = LeaderElector(
            name="test-operator",
            namespace="test-namespace",
            identity="pod-2"
        )

        # Both try to acquire simultaneously
        mock_lease = Mock()
        mock_lease.spec.holder_identity = None

        # Use version/resourceVersion to prevent split brain
        mock_lease.metadata.resource_version = "1"

        # First update succeeds
        with patch.object(elector1, 'get_lease', return_value=mock_lease):
            with patch.object(elector1, 'update_lease', return_value=True):
                success1 = elector1.try_acquire_or_renew()

        # Second update should fail due to version conflict
        mock_lease.metadata.resource_version = "2"  # Version changed
        mock_lease.spec.holder_identity = "pod-1"

        with patch.object(elector2, 'get_lease', return_value=mock_lease):
            success2 = elector2.try_acquire_or_renew()

        assert success1 is True
        assert elector1.is_leader is True
        assert success2 is False
        assert elector2.is_leader is False

    def test_graceful_shutdown(self):
        """Test graceful shutdown releases leadership"""
        elector = LeaderElector(
            name="test-operator",
            namespace="test-namespace",
            identity="test-pod"
        )

        elector.is_leader = True

        # Shutdown should release leadership
        with patch.object(elector, 'release') as mock_release:
            elector.shutdown()
            mock_release.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
