# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib
import pytest

from fakes.fake_guestfs import FakeGuestFS
from fakes.fake_logger import FakeLogger

class FX:
    def __init__(self):
        self.logger = FakeLogger()
        self.dry_run = False
        self.update_grub = True
        self.root_dev = "/dev/sda2"
    def backup_file(self, g, p): return None

def test_update_default_grub_rewrites_root(monkeypatch):
    try:
        grub_fixer = importlib.import_module("hyper2kvm.fixers.grub_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import grub_fixer: {e}")

    monkeypatch.setattr(grub_fixer, "_stable_root_id", lambda self, g: "UUID=abc")

    g = FakeGuestFS()
    g.dirs |= {"/etc", "/boot", "/boot/grub2"}
    g.fs["/etc/default/grub"] = b'GRUB_CMDLINE_LINUX="quiet root=/dev/sda2"\n'

    fx = FX()
    changed = grub_fixer.update_grub_root(fx, g)
    assert changed >= 1
    assert b"root=UUID=abc" in g.fs["/etc/default/grub"]

def test_update_bls_rewrites_root(monkeypatch):
    try:
        grub_fixer = importlib.import_module("hyper2kvm.fixers.grub_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import grub_fixer: {e}")

    monkeypatch.setattr(grub_fixer, "_stable_root_id", lambda self, g: "UUID=abc")

    g = FakeGuestFS()
    g.dirs |= {"/boot", "/boot/loader", "/boot/loader/entries", "/etc"}
    g.fs["/boot/loader/entries/x.conf"] = b"options root=/dev/sda2 quiet\n"

    fx = FX()
    changed = grub_fixer.update_grub_root(fx, g)
    assert changed >= 1
    assert b"root=UUID=abc" in g.fs["/boot/loader/entries/x.conf"]
