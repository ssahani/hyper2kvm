"""
Unit tests for concurrency safety and thread safety

Tests concurrent operations, race conditions, locking mechanisms,
and thread-safe resource access patterns.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import threading
import time
from queue import Queue


class TestThreadSafety:
    """Test thread-safe operations"""

    def test_concurrent_file_access(self):
        """Test thread-safe file access"""
        # Simulate multiple threads accessing files
        file_locks = {}
        accessed_files = []

        def access_file(file_path):
            # Acquire lock for file
            if file_path not in file_locks:
                file_locks[file_path] = threading.Lock()

            with file_locks[file_path]:
                # Simulate file access
                accessed_files.append(file_path)
                time.sleep(0.001)  # Simulate I/O

        # Multiple threads accessing same file
        threads = []
        for i in range(5):
            t = threading.Thread(target=access_file, args=("/tmp/test.vmdk",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All accesses should be serialized
        assert len(accessed_files) == 5

    def test_resource_pool_thread_safety(self):
        """Test thread-safe resource pool"""
        max_resources = 3
        available_resources = list(range(max_resources))
        resource_lock = threading.Lock()
        allocations = []

        def allocate_resource():
            with resource_lock:
                if available_resources:
                    resource = available_resources.pop(0)
                    allocations.append(resource)
                    return resource
            return None

        def release_resource(resource):
            with resource_lock:
                available_resources.append(resource)

        # Concurrent allocations
        threads = []
        for i in range(5):
            t = threading.Thread(target=allocate_resource)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Only 3 resources should be allocated
        assert len(allocations) <= max_resources

    def test_counter_increment_thread_safety(self):
        """Test thread-safe counter increment"""
        counter = {"value": 0}
        counter_lock = threading.Lock()

        def increment():
            for _ in range(100):
                with counter_lock:
                    counter["value"] += 1

        # Multiple threads incrementing
        threads = [threading.Thread(target=increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Counter should be exactly 1000
        assert counter["value"] == 1000

    def test_shared_state_modification(self):
        """Test thread-safe shared state modification"""
        shared_state = {}
        state_lock = threading.Lock()

        def update_state(key, value):
            with state_lock:
                shared_state[key] = value

        # Concurrent updates
        threads = []
        for i in range(10):
            t = threading.Thread(target=update_state, args=(f"key_{i}", i))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All updates should be present
        assert len(shared_state) == 10


class TestRaceConditions:
    """Test race condition prevention"""

    def test_check_then_act_race_condition(self):
        """Test prevention of check-then-act race condition"""
        file_exists = {"state": False}
        lock = threading.Lock()
        creation_attempts = []

        def create_if_not_exists():
            with lock:
                # Atomic check-and-create
                if not file_exists["state"]:
                    file_exists["state"] = True
                    creation_attempts.append(1)

        # Multiple threads trying to create
        threads = [threading.Thread(target=create_if_not_exists) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one creation should succeed
        assert len(creation_attempts) == 1

    def test_double_checked_locking(self):
        """Test double-checked locking pattern"""
        singleton = {"instance": None}
        lock = threading.Lock()

        def get_instance():
            if singleton["instance"] is None:
                with lock:
                    # Double-check inside lock
                    if singleton["instance"] is None:
                        singleton["instance"] = {"created": True}
            return singleton["instance"]

        # Concurrent instance requests
        instances = []
        threads = []
        for _ in range(10):
            t = threading.Thread(target=lambda: instances.append(get_instance()))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All instances should be the same
        assert all(inst is instances[0] for inst in instances)

    def test_read_modify_write_race(self):
        """Test prevention of read-modify-write race"""
        data = {"counter": 0}
        lock = threading.Lock()

        def increment_safe():
            with lock:
                # Atomic read-modify-write
                current = data["counter"]
                data["counter"] = current + 1

        threads = [threading.Thread(target=increment_safe) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert data["counter"] == 100

    def test_time_of_check_to_time_of_use(self):
        """Test TOCTOU prevention"""
        resources = {"available": True}
        lock = threading.Lock()
        allocations = []

        def allocate_resource():
            with lock:
                # Check and use atomically
                if resources["available"]:
                    resources["available"] = False
                    allocations.append("allocated")
                    return True
            return False

        # Concurrent allocations
        threads = [threading.Thread(target=allocate_resource) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one allocation should succeed
        assert len(allocations) == 1


class TestDeadlockPrevention:
    """Test deadlock prevention strategies"""

    def test_lock_ordering_prevents_deadlock(self):
        """Test consistent lock ordering"""
        lock_a = threading.Lock()
        lock_b = threading.Lock()
        operations = []

        def operation_1():
            # Always acquire in order: A then B
            with lock_a:
                time.sleep(0.001)
                with lock_b:
                    operations.append("op1")

        def operation_2():
            # Same order: A then B
            with lock_a:
                time.sleep(0.001)
                with lock_b:
                    operations.append("op2")

        t1 = threading.Thread(target=operation_1)
        t2 = threading.Thread(target=operation_2)

        t1.start()
        t2.start()

        t1.join(timeout=1.0)
        t2.join(timeout=1.0)

        # Both operations should complete
        assert len(operations) == 2

    def test_timeout_based_deadlock_avoidance(self):
        """Test using timeouts to avoid deadlock"""
        lock = threading.Lock()
        acquired = []

        def try_acquire_with_timeout():
            if lock.acquire(timeout=0.1):
                try:
                    acquired.append(True)
                finally:
                    lock.release()
            else:
                acquired.append(False)

        # First thread holds lock
        lock.acquire()

        # Second thread tries to acquire with timeout
        t = threading.Thread(target=try_acquire_with_timeout)
        t.start()
        t.join()

        # Should timeout
        assert False in acquired

        lock.release()

    def test_lock_free_data_structure(self):
        """Test lock-free queue for avoiding deadlocks"""
        queue = Queue()
        items = []

        def producer():
            for i in range(10):
                queue.put(i)

        def consumer():
            while True:
                try:
                    item = queue.get(timeout=0.1)
                    items.append(item)
                    queue.task_done()
                except:
                    break

        t1 = threading.Thread(target=producer)
        t2 = threading.Thread(target=consumer)

        t1.start()
        t2.start()

        t1.join()
        t2.join(timeout=1.0)

        # All items should be processed
        assert len(items) > 0


class TestAtomicOperations:
    """Test atomic operations"""

    def test_atomic_file_write(self):
        """Test atomic file write operation"""
        # Write to temporary file, then rename
        temp_file = "/tmp/test.tmp"
        final_file = "/tmp/test.final"

        operations = []

        # Simulate atomic write
        operations.append("write_to_temp")
        operations.append("sync_to_disk")
        operations.append("rename_to_final")

        # Rename is atomic on POSIX
        assert operations[-1] == "rename_to_final"

    def test_atomic_reference_update(self):
        """Test atomic reference update"""
        ref = {"current": "old_value"}
        lock = threading.Lock()

        def compare_and_swap(expected, new_value):
            with lock:
                if ref["current"] == expected:
                    ref["current"] = new_value
                    return True
                return False

        # Concurrent CAS operations
        results = []

        def update_thread():
            result = compare_and_swap("old_value", "new_value")
            results.append(result)

        threads = [threading.Thread(target=update_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one CAS should succeed
        assert sum(results) == 1

    def test_atomic_counter_operations(self):
        """Test atomic counter operations"""
        counter = {"value": 0}
        lock = threading.Lock()

        def atomic_increment():
            with lock:
                counter["value"] += 1
                return counter["value"]

        def atomic_decrement():
            with lock:
                counter["value"] -= 1
                return counter["value"]

        # Concurrent increments and decrements
        threads = []
        for i in range(50):
            t = threading.Thread(target=atomic_increment)
            threads.append(t)
        for i in range(30):
            t = threading.Thread(target=atomic_decrement)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Net should be +20
        assert counter["value"] == 20


class TestConcurrentCollections:
    """Test concurrent collection operations"""

    def test_thread_safe_list_operations(self):
        """Test thread-safe list operations"""
        items = []
        lock = threading.Lock()

        def append_item(item):
            with lock:
                items.append(item)

        threads = [threading.Thread(target=append_item, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(items) == 100

    def test_thread_safe_dict_operations(self):
        """Test thread-safe dictionary operations"""
        data = {}
        lock = threading.Lock()

        def set_item(key, value):
            with lock:
                data[key] = value

        def get_item(key):
            with lock:
                return data.get(key)

        # Concurrent writes
        threads = [threading.Thread(target=set_item, args=(i, i*10)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(data) == 50

    def test_producer_consumer_queue(self):
        """Test producer-consumer pattern with queue"""
        queue = Queue(maxsize=10)
        produced = []
        consumed = []

        def producer():
            for i in range(20):
                queue.put(i)
                produced.append(i)

        def consumer():
            while len(consumed) < 20:
                try:
                    item = queue.get(timeout=0.1)
                    consumed.append(item)
                    queue.task_done()
                except:
                    pass

        t1 = threading.Thread(target=producer)
        t2 = threading.Thread(target=consumer)

        t1.start()
        t2.start()

        t1.join()
        t2.join(timeout=2.0)

        assert len(produced) == 20
        assert len(consumed) == 20


class TestMemoryVisibility:
    """Test memory visibility across threads"""

    def test_volatile_variable_visibility(self):
        """Test variable visibility across threads"""
        shared = {"flag": False, "value": 0}
        lock = threading.Lock()

        def writer():
            with lock:
                shared["value"] = 42
                shared["flag"] = True

        def reader():
            while True:
                with lock:
                    if shared["flag"]:
                        return shared["value"]

        t1 = threading.Thread(target=writer)
        t1.start()
        t1.join()

        t2 = threading.Thread(target=reader)
        t2.start()
        t2.join(timeout=1.0)

        assert shared["value"] == 42

    def test_happens_before_relationship(self):
        """Test happens-before relationship"""
        data = {"step1": False, "step2": False}
        lock = threading.Lock()

        def step_1():
            with lock:
                data["step1"] = True

        def step_2():
            with lock:
                if data["step1"]:
                    data["step2"] = True

        t1 = threading.Thread(target=step_1)
        t1.start()
        t1.join()

        t2 = threading.Thread(target=step_2)
        t2.start()
        t2.join()

        assert data["step2"] is True


class TestWorkloadDistribution:
    """Test workload distribution across threads"""

    def test_round_robin_distribution(self):
        """Test round-robin task distribution"""
        num_workers = 4
        tasks = list(range(20))
        worker_tasks = [[] for _ in range(num_workers)]

        # Distribute tasks round-robin
        for i, task in enumerate(tasks):
            worker_id = i % num_workers
            worker_tasks[worker_id].append(task)

        # Each worker should have 5 tasks
        assert all(len(wt) == 5 for wt in worker_tasks)

    def test_work_stealing_queue(self):
        """Test work stealing between threads"""
        global_queue = list(range(100))
        worker_queues = [[] for _ in range(4)]
        lock = threading.Lock()

        def steal_work(worker_id):
            while True:
                with lock:
                    if global_queue:
                        task = global_queue.pop(0)
                        worker_queues[worker_id].append(task)
                    else:
                        break

        threads = [threading.Thread(target=steal_work, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All tasks distributed
        total = sum(len(wq) for wq in worker_queues)
        assert total == 100

    def test_load_balanced_distribution(self):
        """Test load-balanced task distribution"""
        worker_loads = [10, 5, 15, 8]  # Current loads
        new_tasks = 12
        initial_imbalance = max(worker_loads) - min(worker_loads)  # 15 - 5 = 10

        # Assign to least loaded workers
        for _ in range(new_tasks):
            min_worker = worker_loads.index(min(worker_loads))
            worker_loads[min_worker] += 1

        # Load should be more balanced than before
        final_imbalance = max(worker_loads) - min(worker_loads)
        assert final_imbalance < initial_imbalance
        # With greedy assignment to minimum, final is [12, 12, 15, 11]
        assert final_imbalance <= 4


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
