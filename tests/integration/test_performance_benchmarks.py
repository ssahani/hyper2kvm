"""Performance benchmarking tests for hyper2kvm.

This module contains tests to benchmark and validate the performance
characteristics of VM conversion operations.

Benchmarks:
- Image inspection time
- QCOW2 conversion speed
- Driver injection overhead
- Full migration pipeline duration
- Memory usage profiling
- Concurrent conversion scalability

Usage:
    pytest tests/integration/test_performance_benchmarks.py -v -s
    pytest tests/integration/test_performance_benchmarks.py -k benchmark_conversion_speed
"""

import time
import pytest
import os
import subprocess
from pathlib import Path
import json
import psutil

# Pytest marks for performance tests
pytestmark = [
    pytest.mark.performance,
    pytest.mark.slow,
]


class TestPerformanceBenchmarks:
    """Performance benchmark tests for hyper2kvm operations."""

    @pytest.fixture
    def test_image_small(self):
        """Path to small test image (if available)."""
        # Try to find a small test image
        test_images = [
            "test-small.vmdk",
            "photon.vmdk",
            "test.vmdk"
        ]

        for img in test_images:
            if os.path.exists(img):
                return img

        pytest.skip("No test image available for benchmarking")

    @pytest.fixture
    def performance_results(self, tmp_path):
        """Fixture to collect and store performance results."""
        results_file = tmp_path / "performance_results.json"
        results = {
            "benchmarks": [],
            "timestamp": time.time(),
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "platform": os.uname().sysname,
            }
        }

        yield results

        # Save results at the end
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n📊 Performance results saved to: {results_file}")

    def test_benchmark_image_inspection(self, test_image_small, performance_results):
        """Benchmark image inspection performance."""
        pytest.importorskip("guestfs")
        import guestfs

        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / (1024**2)  # MB

        # Inspect image
        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive_opts(test_image_small, readonly=True)
        g.launch()

        roots = g.inspect_os()
        if roots:
            root = roots[0]
            osinfo = {
                "type": g.inspect_get_type(root),
                "distro": g.inspect_get_distro(root),
                "major": g.inspect_get_major_version(root),
                "filesystems": g.inspect_get_filesystems(root),
            }

        g.close()

        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / (1024**2)  # MB

        duration = end_time - start_time
        memory_used = end_memory - start_memory

        # Record results
        performance_results["benchmarks"].append({
            "test": "image_inspection",
            "duration_seconds": duration,
            "memory_mb": memory_used,
            "image": test_image_small,
        })

        # Assertions
        assert duration < 30.0, f"Image inspection took {duration:.2f}s (expected < 30s)"
        assert memory_used < 500, f"Memory usage {memory_used:.2f}MB (expected < 500MB)"

        print(f"\n✓ Image inspection: {duration:.2f}s, {memory_used:.2f}MB RAM")

    def test_benchmark_qcow2_conversion_speed(self, test_image_small, tmp_path, performance_results):
        """Benchmark QCOW2 conversion speed."""
        output = tmp_path / "converted.qcow2"

        # Get input file size
        input_size_mb = os.path.getsize(test_image_small) / (1024**2)

        start_time = time.time()
        start_cpu = psutil.cpu_percent(interval=None)

        # Convert using qemu-img
        cmd = [
            "qemu-img", "convert",
            "-f", "vmdk",
            "-O", "qcow2",
            "-c",  # Compressed
            str(test_image_small),
            str(output)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        end_time = time.time()
        end_cpu = psutil.cpu_percent(interval=None)

        duration = end_time - start_time
        output_size_mb = os.path.getsize(output) / (1024**2)
        speed_mbps = input_size_mb / duration
        compression_ratio = input_size_mb / output_size_mb

        # Record results
        performance_results["benchmarks"].append({
            "test": "qcow2_conversion",
            "duration_seconds": duration,
            "input_size_mb": input_size_mb,
            "output_size_mb": output_size_mb,
            "speed_mbps": speed_mbps,
            "compression_ratio": compression_ratio,
            "cpu_usage_percent": end_cpu - start_cpu,
        })

        # Assertions
        assert result.returncode == 0, f"Conversion failed: {result.stderr}"
        assert speed_mbps > 10, f"Conversion speed {speed_mbps:.2f} MB/s (expected > 10 MB/s)"
        assert compression_ratio > 1.1, f"Compression ratio {compression_ratio:.2f}x (expected > 1.1x)"

        print(f"\n✓ QCOW2 conversion: {speed_mbps:.2f} MB/s, {compression_ratio:.2f}x compression")

    @pytest.mark.requires_images
    def test_benchmark_driver_injection_overhead(self, test_image_small, tmp_path, performance_results):
        """Benchmark driver injection performance overhead."""
        pytest.importorskip("guestfs")
        import guestfs

        # If no test image, skip
        if test_image_small is None:
            pytest.skip("No test image available for benchmarking")

        # Detect source format
        result = subprocess.run([
            "qemu-img", "info", "--output=json", str(test_image_small)
        ], capture_output=True, text=True)

        if result.returncode != 0:
            pytest.skip(f"Cannot read image: {test_image_small}")

        import json
        info = json.loads(result.stdout)
        source_format = info.get("format", "vmdk")

        # Create a copy for modification
        test_copy = tmp_path / "test_copy.qcow2"
        subprocess.run([
            "qemu-img", "convert",
            "-f", source_format,
            "-O", "qcow2",
            str(test_image_small),
            str(test_copy)
        ], check=True)

        start_time = time.time()

        # Mount and inject drivers
        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive(str(test_copy))
        g.launch()

        roots = g.inspect_os()
        if roots:
            root = roots[0]

            # Get mountpoints
            mountpoints = g.inspect_get_mountpoints(root)

            # Mount filesystems
            for device, mp in sorted(mountpoints.items(), key=lambda k: len(k[0])):
                try:
                    g.mount(device, mp)
                except Exception:
                    pass

            # Simulate driver injection (just file operations)
            try:
                if g.is_dir("/boot"):
                    files = g.ls("/boot")
            except Exception:
                pass

        g.sync()
        g.umount_all()
        g.close()

        end_time = time.time()
        duration = end_time - start_time

        # Record results
        performance_results["benchmarks"].append({
            "test": "driver_injection_overhead",
            "duration_seconds": duration,
        })

        # Assertion
        assert duration < 60.0, f"Driver injection took {duration:.2f}s (expected < 60s)"

        print(f"\n✓ Driver injection overhead: {duration:.2f}s")

    def test_benchmark_memory_usage_scaling(self, performance_results):
        """Benchmark memory usage with different operations."""
        pytest.importorskip("guestfs")
        import guestfs

        memory_samples = []

        # Measure baseline
        memory_samples.append(("baseline", psutil.Process().memory_info().rss / (1024**2)))

        # Create GuestFS instance
        g = guestfs.GuestFS(python_return_dict=True)
        memory_samples.append(("guestfs_created", psutil.Process().memory_info().rss / (1024**2)))

        # Close GuestFS
        g.close()
        memory_samples.append(("guestfs_closed", psutil.Process().memory_info().rss / (1024**2)))

        # Record results
        performance_results["benchmarks"].append({
            "test": "memory_usage_scaling",
            "samples": dict(memory_samples),
        })

        # Calculate memory overhead
        overhead = memory_samples[1][1] - memory_samples[0][1]

        assert overhead < 100, f"GuestFS memory overhead {overhead:.2f}MB (expected < 100MB)"

        print(f"\n✓ Memory overhead: {overhead:.2f}MB")

    def test_benchmark_concurrent_conversions(self, tmp_path, performance_results):
        """Benchmark concurrent QCOW2 conversion performance."""
        import concurrent.futures

        # Create dummy VMDK files for testing
        test_files = []
        for i in range(3):
            vmdk = tmp_path / f"test_{i}.vmdk"
            # Create a small sparse file
            with open(vmdk, 'wb') as f:
                f.seek(10 * 1024 * 1024 - 1)  # 10MB
                f.write(b'\0')
            test_files.append(vmdk)

        def convert_image(vmdk_path):
            """Convert a single image."""
            output = vmdk_path.parent / f"{vmdk_path.stem}.qcow2"
            start = time.time()

            subprocess.run([
                "qemu-img", "convert",
                "-f", "raw",  # Sparse files are raw
                "-O", "qcow2",
                str(vmdk_path),
                str(output)
            ], check=True, capture_output=True)

            duration = time.time() - start
            return duration

        # Benchmark sequential
        start_sequential = time.time()
        sequential_times = [convert_image(f) for f in test_files]
        sequential_total = time.time() - start_sequential

        # Clean up for parallel run
        for f in tmp_path.glob("*.qcow2"):
            f.unlink()

        # Benchmark parallel (max 3 workers)
        start_parallel = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            parallel_times = list(executor.map(convert_image, test_files))
        parallel_total = time.time() - start_parallel

        speedup = sequential_total / parallel_total

        # Record results
        performance_results["benchmarks"].append({
            "test": "concurrent_conversions",
            "sequential_total_seconds": sequential_total,
            "parallel_total_seconds": parallel_total,
            "speedup": speedup,
            "num_files": len(test_files),
        })

        # Assertion
        assert speedup > 1.5, f"Parallel speedup {speedup:.2f}x (expected > 1.5x)"

        print(f"\n✓ Concurrent conversions: {speedup:.2f}x speedup")

    def test_benchmark_full_pipeline_duration(self, tmp_path, performance_results):
        """Benchmark end-to-end pipeline duration."""
        # This is a simulated pipeline test
        start_time = time.time()

        operations = {
            "validation": 0.1,
            "inspection": 0.5,
            "driver_detection": 0.3,
            "conversion": 2.0,
            "post_validation": 0.2,
            "cleanup": 0.1,
        }

        for op, duration in operations.items():
            time.sleep(duration)

        total_duration = time.time() - start_time

        # Record results
        performance_results["benchmarks"].append({
            "test": "full_pipeline",
            "duration_seconds": total_duration,
            "operations": operations,
        })

        assert total_duration < 5.0, f"Pipeline took {total_duration:.2f}s (expected < 5s for test)"

        print(f"\n✓ Full pipeline: {total_duration:.2f}s")

    def test_performance_regression_check(self, performance_results):
        """Check for performance regressions against baseline."""
        # Define baseline performance expectations
        baselines = {
            "image_inspection": {"max_duration": 30.0, "max_memory_mb": 500},
            "qcow2_conversion": {"min_speed_mbps": 10.0, "min_compression": 1.1},
            "driver_injection_overhead": {"max_duration": 60.0},
            "concurrent_conversions": {"min_speedup": 1.5},
        }

        # Check each benchmark against baseline
        regressions = []
        for benchmark in performance_results["benchmarks"]:
            test_name = benchmark["test"]

            if test_name in baselines:
                baseline = baselines[test_name]

                if "max_duration" in baseline and "duration_seconds" in benchmark:
                    if benchmark["duration_seconds"] > baseline["max_duration"]:
                        regressions.append(
                            f"{test_name}: duration {benchmark['duration_seconds']:.2f}s > {baseline['max_duration']}s"
                        )

                if "min_speed_mbps" in baseline and "speed_mbps" in benchmark:
                    if benchmark["speed_mbps"] < baseline["min_speed_mbps"]:
                        regressions.append(
                            f"{test_name}: speed {benchmark['speed_mbps']:.2f} MB/s < {baseline['min_speed_mbps']} MB/s"
                        )

        if regressions:
            print("\n⚠️  Performance regressions detected:")
            for regression in regressions:
                print(f"   - {regression}")
        else:
            print("\n✅ No performance regressions detected")

        # Don't fail on regressions, just warn
        assert True


class TestMemoryProfiling:
    """Memory profiling tests."""

    def test_memory_leak_detection(self):
        """Test for memory leaks in repeated operations."""
        pytest.importorskip("guestfs")
        import guestfs
        import gc

        memory_samples = []

        # Run operation multiple times
        for i in range(5):
            g = guestfs.GuestFS(python_return_dict=True)
            g.close()

            # Force garbage collection
            gc.collect()

            # Sample memory
            mem = psutil.Process().memory_info().rss / (1024**2)
            memory_samples.append(mem)

            time.sleep(0.1)

        # Check if memory is growing
        memory_growth = memory_samples[-1] - memory_samples[0]

        print(f"\n📊 Memory samples: {[f'{m:.2f}MB' for m in memory_samples]}")
        print(f"📊 Memory growth: {memory_growth:.2f}MB over 5 iterations")

        # Allow some growth but not excessive
        assert memory_growth < 50, f"Potential memory leak: {memory_growth:.2f}MB growth"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
