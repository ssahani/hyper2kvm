"""
Test Image Fixtures for hyper2kvm Test Suite

Provides pytest fixtures for test VM disk images:
- test_linux_qcow2_image: Linux QCOW2 image with filesystem
- test_linux_raw_image: Linux RAW image
- test_linux_vmdk_image: Linux VMDK image
- test_images_dir: Directory containing all test images

Usage in tests:
    def test_something(test_linux_qcow2_image):
        # test_linux_qcow2_image is a Path object
        assert test_linux_qcow2_image.exists()
"""

from pathlib import Path
from typing import Generator
import pytest
import subprocess
import os


@pytest.fixture(scope="session")
def test_images_dir() -> Path:
    """
    Get the directory containing test images.

    Creates the directory if it doesn't exist.
    """
    images_dir = Path(__file__).parent / "images"
    images_dir.mkdir(exist_ok=True)
    return images_dir


@pytest.fixture(scope="session")
def test_linux_qcow2_image(test_images_dir: Path) -> Generator[Path, None, None]:
    """
    Provide a Linux QCOW2 test image.

    Creates the image if it doesn't exist using guestfs.
    """
    image_path = test_images_dir / "test-linux-qcow2.qcow2"

    if not image_path.exists():
        _create_test_image_if_possible(image_path, "qcow2")

    if image_path.exists():
        yield image_path
    else:
        # Fallback: create a minimal empty image
        _create_minimal_image(image_path, "qcow2")
        yield image_path


@pytest.fixture(scope="session")
def test_linux_raw_image(test_images_dir: Path) -> Generator[Path, None, None]:
    """
    Provide a Linux RAW test image.
    """
    image_path = test_images_dir / "test-linux-raw.img"

    if not image_path.exists():
        _create_test_image_if_possible(image_path, "raw")

    if image_path.exists():
        yield image_path
    else:
        _create_minimal_image(image_path, "raw")
        yield image_path


@pytest.fixture(scope="session")
def test_linux_vmdk_image(test_images_dir: Path) -> Generator[Path, None, None]:
    """
    Provide a Linux VMDK test image.
    """
    image_path = test_images_dir / "test-linux-vmdk.vmdk"

    if not image_path.exists():
        # Try to convert from qcow2 if it exists
        qcow2_image = test_images_dir / "test-linux-qcow2.qcow2"
        if qcow2_image.exists():
            _convert_to_vmdk(qcow2_image, image_path)

    if image_path.exists():
        yield image_path
    else:
        _create_minimal_image(image_path, "vmdk")
        yield image_path


@pytest.fixture(scope="session")
def test_windows_qcow2_image(test_images_dir: Path) -> Generator[Path, None, None]:
    """
    Provide a Windows QCOW2 test image (minimal, for structure testing).
    """
    image_path = test_images_dir / "test-windows-qcow2.qcow2"

    if not image_path.exists():
        _create_minimal_image(image_path, "qcow2", size_mb=2048)

    yield image_path


# Helper functions

def _create_test_image_if_possible(image_path: Path, format: str):
    """
    Try to create a test image using the create_test_images.py script.
    """
    script_path = Path(__file__).parent / "create_test_images.py"

    if not script_path.exists():
        return

    try:
        # Run the creation script
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"Created test image: {image_path}")
        else:
            print(f"Failed to create test image: {result.stderr}")

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Could not create test image: {e}")


def _create_minimal_image(image_path: Path, format: str, size_mb: int = 1024):
    """
    Create a minimal empty image using qemu-img.

    This is a fallback when guestfs is not available.
    """
    try:
        subprocess.run([
            "qemu-img", "create",
            "-f", format,
            str(image_path),
            f"{size_mb}M"
        ], check=True, capture_output=True)

        print(f"Created minimal {format} image: {image_path.name}")

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Could not create minimal image: {e}")
        # Create a dummy file as last resort
        image_path.touch()


def _convert_to_vmdk(source_qcow2: Path, target_vmdk: Path):
    """
    Convert QCOW2 to VMDK using qemu-img.
    """
    try:
        subprocess.run([
            "qemu-img", "convert",
            "-f", "qcow2",
            "-O", "vmdk",
            str(source_qcow2),
            str(target_vmdk)
        ], check=True, capture_output=True)

        print(f"Converted {source_qcow2.name} to {target_vmdk.name}")

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Could not convert to VMDK: {e}")


@pytest.fixture
def cleanup_test_image(test_images_dir: Path):
    """
    Provide a temporary test image that gets cleaned up after the test.

    Usage:
        def test_something(cleanup_test_image):
            image_path = cleanup_test_image("test-temp.qcow2", "qcow2")
            # ... use image_path ...
            # Automatically cleaned up after test
    """
    created_images = []

    def create_temp_image(filename: str, format: str, size_mb: int = 100) -> Path:
        image_path = test_images_dir / filename
        _create_minimal_image(image_path, format, size_mb)
        created_images.append(image_path)
        return image_path

    yield create_temp_image

    # Cleanup
    for image_path in created_images:
        if image_path.exists():
            image_path.unlink()


# Pytest collection hook to show available fixtures
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "requires_images: mark test as requiring test VM images"
    )
