"""
Unit tests for error handling and exception management

Tests exception handling, error recovery, retry logic, circuit breakers,
and graceful degradation.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import time


class TestExceptionHandling:
    """Test exception handling patterns"""

    def test_specific_exception_handling(self):
        """Test handling specific exceptions"""
        def risky_operation(value):
            if value < 0:
                raise ValueError("Negative value not allowed")
            if value == 0:
                raise ZeroDivisionError("Cannot divide by zero")
            return 100 / value

        # Test ValueError handling
        with pytest.raises(ValueError) as exc_info:
            risky_operation(-1)
        assert "Negative value" in str(exc_info.value)

        # Test ZeroDivisionError handling
        with pytest.raises(ZeroDivisionError):
            risky_operation(0)

        # Test success case
        result = risky_operation(10)
        assert result == 10.0

    def test_exception_chaining(self):
        """Test exception chaining for context"""
        def outer_operation():
            try:
                inner_operation()
            except ValueError as e:
                raise RuntimeError("Outer operation failed") from e

        def inner_operation():
            raise ValueError("Inner operation error")

        with pytest.raises(RuntimeError) as exc_info:
            outer_operation()

        # Should have cause chain
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)

    def test_custom_exception_hierarchy(self):
        """Test custom exception hierarchy"""
        class MigrationError(Exception):
            pass

        class ConversionError(MigrationError):
            pass

        class FixerError(MigrationError):
            pass

        def handle_migration_error(error_type):
            if error_type == "conversion":
                raise ConversionError("Conversion failed")
            elif error_type == "fixer":
                raise FixerError("Fixer failed")

        # Test exception hierarchy
        with pytest.raises(MigrationError):
            handle_migration_error("conversion")

        with pytest.raises(ConversionError):
            handle_migration_error("conversion")

    def test_finally_cleanup(self):
        """Test cleanup in finally block"""
        resources = {"allocated": False, "released": False}

        def operation_with_cleanup():
            try:
                resources["allocated"] = True
                raise RuntimeError("Operation failed")
            finally:
                resources["released"] = True

        with pytest.raises(RuntimeError):
            operation_with_cleanup()

        # Cleanup should happen even on exception
        assert resources["allocated"] is True
        assert resources["released"] is True

    def test_context_manager_exception_handling(self):
        """Test exception handling with context managers"""
        class Resource:
            def __init__(self):
                self.opened = False
                self.closed = False

            def __enter__(self):
                self.opened = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.closed = True
                return False  # Don't suppress exception

        resource = Resource()
        with pytest.raises(RuntimeError):
            with resource:
                raise RuntimeError("Error during operation")

        # Resource should be cleaned up
        assert resource.opened is True
        assert resource.closed is True


class TestRetryLogic:
    """Test retry mechanisms"""

    def test_basic_retry_on_failure(self):
        """Test basic retry logic"""
        attempts = {"count": 0}
        max_retries = 3

        def unreliable_operation():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("Temporary failure")
            return "success"

        # Retry loop
        for attempt in range(max_retries):
            try:
                result = unreliable_operation()
                break
            except RuntimeError:
                if attempt == max_retries - 1:
                    raise

        assert result == "success"
        assert attempts["count"] == 3

    def test_exponential_backoff(self):
        """Test exponential backoff between retries"""
        retry_delays = []
        base_delay = 0.1

        for attempt in range(5):
            delay = base_delay * (2 ** attempt)
            retry_delays.append(delay)

        # Delays should double each time
        assert retry_delays == [0.1, 0.2, 0.4, 0.8, 1.6]

    def test_jittered_backoff(self):
        """Test backoff with jitter"""
        import random
        random.seed(42)

        base_delay = 1.0
        max_jitter = 0.2

        delays = []
        for _ in range(5):
            jitter = random.uniform(-max_jitter, max_jitter)
            delay = base_delay + jitter
            delays.append(delay)

        # All delays should be near base_delay
        assert all(0.8 <= d <= 1.2 for d in delays)

    def test_retry_with_exception_filter(self):
        """Test retry only on specific exceptions"""
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise IOError("Transient error")  # Retryable
            if attempts["count"] == 2:
                raise ValueError("Invalid input")  # Not retryable
            return "success"

        retryable_exceptions = (IOError, TimeoutError)

        try:
            for attempt in range(3):
                try:
                    result = operation()
                    break
                except retryable_exceptions:
                    continue
                except Exception:
                    raise
        except ValueError:
            # Should propagate non-retryable exception
            pass

        assert attempts["count"] == 2

    def test_max_retry_timeout(self):
        """Test overall retry timeout"""
        start_time = time.time()
        max_timeout = 0.5
        attempts = {"count": 0}

        def slow_operation():
            attempts["count"] += 1
            time.sleep(0.2)
            raise RuntimeError("Still failing")

        try:
            while (time.time() - start_time) < max_timeout:
                try:
                    slow_operation()
                except RuntimeError:
                    pass
        except:
            pass

        # Should have made 2-3 attempts in 0.5s
        assert 2 <= attempts["count"] <= 3


class TestCircuitBreaker:
    """Test circuit breaker pattern"""

    def test_circuit_breaker_states(self):
        """Test circuit breaker state transitions"""
        circuit = {
            "state": "closed",
            "failures": 0,
            "threshold": 3,
            "timeout": 1.0,
            "open_time": None,
        }

        def record_failure():
            circuit["failures"] += 1
            if circuit["failures"] >= circuit["threshold"]:
                circuit["state"] = "open"
                circuit["open_time"] = time.time()

        def record_success():
            circuit["failures"] = 0
            circuit["state"] = "closed"

        def check_circuit():
            if circuit["state"] == "open":
                elapsed = time.time() - circuit["open_time"]
                if elapsed >= circuit["timeout"]:
                    circuit["state"] = "half_open"
            return circuit["state"]

        # Initially closed
        assert check_circuit() == "closed"

        # Record failures
        for _ in range(3):
            record_failure()

        # Should be open
        assert circuit["state"] == "open"

        # After timeout, should be half-open
        circuit["open_time"] = time.time() - 2.0
        assert check_circuit() == "half_open"

    def test_circuit_breaker_blocks_calls(self):
        """Test circuit breaker blocks calls when open"""
        circuit_open = False
        failures = 0
        max_failures = 3

        def protected_operation():
            nonlocal failures, circuit_open

            if circuit_open:
                raise RuntimeError("Circuit breaker is open")

            # Simulate failure
            failures += 1
            if failures >= max_failures:
                circuit_open = True
            raise RuntimeError("Operation failed")

        # First 3 calls should execute
        for _ in range(3):
            with pytest.raises(RuntimeError):
                protected_operation()

        # Circuit should be open now
        assert circuit_open is True

        # Next call should fail immediately
        with pytest.raises(RuntimeError) as exc_info:
            protected_operation()
        assert "Circuit breaker is open" in str(exc_info.value)

    def test_circuit_breaker_half_open_probe(self):
        """Test circuit breaker half-open state"""
        circuit = {
            "state": "half_open",
            "test_request_sent": False,
            "test_request_success": False,
        }

        def send_test_request():
            circuit["test_request_sent"] = True
            # Simulate successful probe
            circuit["test_request_success"] = True
            if circuit["test_request_success"]:
                circuit["state"] = "closed"

        send_test_request()

        assert circuit["state"] == "closed"


class TestGracefulDegradation:
    """Test graceful degradation patterns"""

    def test_fallback_to_default_value(self):
        """Test falling back to default on error"""
        def get_config_value(key, default=None):
            config = {"timeout": 30}
            try:
                value = config[key]
                if value is None:
                    return default
                return value
            except KeyError:
                return default

        # Existing key
        assert get_config_value("timeout") == 30

        # Missing key with default
        assert get_config_value("missing", default=10) == 10

        # Missing key without default
        assert get_config_value("missing") is None

    def test_partial_failure_handling(self):
        """Test handling partial failures"""
        services = ["service_a", "service_b", "service_c"]
        results = {}
        errors = {}

        def call_service(service):
            if service == "service_b":
                raise RuntimeError(f"{service} unavailable")
            return f"{service}_response"

        for service in services:
            try:
                results[service] = call_service(service)
            except Exception as e:
                errors[service] = str(e)

        # Should have 2 successes and 1 failure
        assert len(results) == 2
        assert len(errors) == 1
        assert "service_b" in errors

    def test_degraded_mode_operation(self):
        """Test operating in degraded mode"""
        cache_available = False
        database_available = True

        def get_data(key):
            if cache_available:
                # Fast path: get from cache
                return f"cached_{key}"
            elif database_available:
                # Slower path: get from database
                return f"db_{key}"
            else:
                # Degraded: return stale data
                return f"stale_{key}"

        # With cache unavailable, should use database
        result = get_data("test")
        assert result == "db_test"

    def test_timeout_based_degradation(self):
        """Test degrading based on timeouts"""
        def operation_with_timeout(timeout):
            start = time.time()
            max_quality_time = 0.1

            # Simulate work
            elapsed = time.time() - start

            if elapsed < max_quality_time:
                return "high_quality_result"
            elif elapsed < timeout:
                return "acceptable_result"
            else:
                return "degraded_result"

        # Fast completion
        result = operation_with_timeout(1.0)
        assert result in ["high_quality_result", "acceptable_result"]


class TestErrorRecovery:
    """Test error recovery strategies"""

    def test_checkpoint_and_resume(self):
        """Test resuming from checkpoint after error"""
        checkpoint = {"last_completed": 0}
        items = list(range(10))

        def process_items():
            for i in items:
                # Resume from checkpoint
                if i <= checkpoint["last_completed"]:
                    continue

                # Process item
                if i == 5:
                    # Simulate error
                    checkpoint["last_completed"] = i - 1
                    raise RuntimeError("Processing failed at item 5")

                checkpoint["last_completed"] = i

        # First attempt
        with pytest.raises(RuntimeError):
            process_items()

        # Checkpoint saved at item 4
        assert checkpoint["last_completed"] == 4

        # Resume should skip first 5 items
        resume_point = checkpoint["last_completed"] + 1
        assert resume_point == 5

    def test_compensating_transaction(self):
        """Test compensating transaction on error"""
        actions = []

        def multi_step_operation():
            try:
                # Step 1
                actions.append("allocate_resource")

                # Step 2
                actions.append("configure_resource")

                # Step 3 - fails
                raise RuntimeError("Configuration failed")

            except Exception:
                # Compensate in reverse order
                if "configure_resource" in actions:
                    actions.append("undo_configure")
                if "allocate_resource" in actions:
                    actions.append("release_resource")
                raise

        with pytest.raises(RuntimeError):
            multi_step_operation()

        # Compensating actions should be present
        assert "undo_configure" in actions
        assert "release_resource" in actions

    def test_rollback_on_error(self):
        """Test rollback on error"""
        state = {"value": 10, "backup": None}

        def update_with_rollback(new_value):
            # Backup current state
            state["backup"] = state["value"]

            try:
                # Apply change
                state["value"] = new_value

                # Validate
                if new_value < 0:
                    raise ValueError("Invalid value")

            except Exception:
                # Rollback
                state["value"] = state["backup"]
                raise

        # Successful update
        update_with_rollback(20)
        assert state["value"] == 20

        # Failed update should rollback
        with pytest.raises(ValueError):
            update_with_rollback(-5)

        # Value should be rolled back
        assert state["value"] == 20


class TestResourceExhaustion:
    """Test handling resource exhaustion"""

    def test_memory_limit_exceeded(self):
        """Test handling memory limit errors"""
        max_memory_mb = 100
        current_usage_mb = 95

        def allocate_memory(size_mb):
            if current_usage_mb + size_mb > max_memory_mb:
                raise MemoryError("Memory limit exceeded")
            return True

        # Should succeed
        assert allocate_memory(4) is True

        # Should fail
        with pytest.raises(MemoryError):
            allocate_memory(10)

    def test_file_descriptor_exhaustion(self):
        """Test handling file descriptor exhaustion"""
        max_fds = 10
        open_fds = list(range(8))

        def open_file():
            if len(open_fds) >= max_fds:
                raise OSError("Too many open files")
            open_fds.append(len(open_fds))

        # Should succeed
        open_file()
        assert len(open_fds) == 9

        # One more should succeed
        open_file()

        # Should fail
        with pytest.raises(OSError):
            open_file()

    def test_disk_space_exhaustion(self):
        """Test handling disk space errors"""
        available_space_gb = 5
        file_size_gb = 10

        def write_file(size_gb):
            if size_gb > available_space_gb:
                raise IOError("No space left on device")
            return True

        with pytest.raises(IOError) as exc_info:
            write_file(file_size_gb)
        assert "No space left" in str(exc_info.value)


class TestErrorPropagation:
    """Test error propagation through layers"""

    def test_layer_error_propagation(self):
        """Test errors propagating through layers"""
        def data_layer():
            raise IOError("Database connection failed")

        def business_layer():
            try:
                return data_layer()
            except IOError as e:
                raise RuntimeError("Business logic failed") from e

        def presentation_layer():
            try:
                return business_layer()
            except RuntimeError as e:
                return {"error": str(e), "cause": str(e.__cause__)}

        result = presentation_layer()
        assert "Business logic failed" in result["error"]
        assert "Database connection" in result["cause"]

    def test_error_enrichment(self):
        """Test adding context to errors as they propagate"""
        def low_level_operation(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        def mid_level_operation(file_path):
            try:
                return low_level_operation(file_path)
            except FileNotFoundError as e:
                raise RuntimeError(
                    f"Failed to process file: {file_path}"
                ) from e

        with pytest.raises(RuntimeError) as exc_info:
            mid_level_operation("/tmp/missing.txt")

        # Error should have context
        assert "/tmp/missing.txt" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, FileNotFoundError)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
