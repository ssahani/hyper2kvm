# SPDX-License-Identifier: LGPL-3.0-or-later
import os
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("PYTHONPATH", str(_REPO_ROOT))

# Import fixtures from the fixtures directory
pytest_plugins = ["tests.fixtures.test_images"]


# GuestFS backend selection fixtures

@pytest.fixture
def use_native_guestfs(monkeypatch):
    """
    Force tests to use native GuestFS implementation instead of libguestfs.

    Usage:
        def test_something(use_native_guestfs):
            # This test will use native backend
            pass
    """
    monkeypatch.setenv('HYPER2KVM_GUESTFS_BACKEND', 'native')


@pytest.fixture
def use_libguestfs(monkeypatch):
    """
    Force tests to use libguestfs implementation (if available).

    Usage:
        def test_something(use_libguestfs):
            # This test will use libguestfs backend
            pass
    """
    monkeypatch.setenv('HYPER2KVM_GUESTFS_BACKEND', 'libguestfs')


@pytest.fixture(params=['native'])
def guestfs_backend(request, monkeypatch):
    """
    Parametrized fixture to run tests with different GuestFS backends.

    Currently only tests 'native' backend since libguestfs is being removed.

    Usage:
        def test_something(guestfs_backend):
            # This test will run once with native backend
            # request.param will be 'native'
            pass
    """
    backend = request.param
    monkeypatch.setenv('HYPER2KVM_GUESTFS_BACKEND', backend)
    return backend


@pytest.fixture
def fake_guestfs():
    """
    Provide a FakeGuestFS instance for unit tests.

    Usage:
        def test_something(fake_guestfs):
            g = fake_guestfs
            g.fs["/etc/hostname"] = b"testhost"
            assert g.cat("/etc/hostname") == "testhost"
    """
    from tests.fixtures.fake_guestfs import FakeGuestFS
    return FakeGuestFS()
