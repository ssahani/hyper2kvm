# SPDX-License-Identifier: GPL-2.0-or-later
import importlib
import pytest

from fakes.fake_guestfs import FakeGuestFS
from fakes.fake_logger import FakeLogger

def _pick_fstab_mode(offline_fixer):
    FM = offline_fixer.FstabMode
    values = [m.value for m in FM]
    for want in ("bypath_only", "BYPATH_ONLY", "by_path_only", "bypath", "by-path-only"):
        if want in values:
            return want
    return values[0]

def test_offline_fixer_runs_and_builds_report(monkeypatch, tmp_path):
    try:
        offline_fixer = importlib.import_module("vmdk2kvm.fixers.offline_fixer")
    except Exception as e:
        pytest.skip(f"Cannot import offline_fixer: {e}")

    fake = FakeGuestFS()
    fake.dirs |= {"/etc", "/boot", "/boot/grub2", "/tmp"}
    fake.fs["/etc/fstab"] = b"UUID=111 / ext4 defaults 0 1\n"
    fake.fs["/etc/os-release"] = b'NAME="Photon"\n'
    fake.inspect_mp = {"/": "/dev/sda2"}
    fake.listfs = {"/dev/sda2": "ext4"}
    fake.parts = ["/dev/sda2"]

    monkeypatch.setattr(offline_fixer.guestfs, "GuestFS", lambda *a, **k: fake)

    monkeypatch.setattr(offline_fixer.network_fixer, "fix_network_config", lambda self, g: {"enabled": True, "changed": 0})
    monkeypatch.setattr(offline_fixer.grub_fixer, "remove_stale_device_map", lambda self, g: 0)
    monkeypatch.setattr(offline_fixer.grub_fixer, "update_grub_root", lambda self, g: 0)
    monkeypatch.setattr(offline_fixer.grub_fixer, "regen", lambda self, g: {"enabled": True, "dry_run": bool(self.dry_run)})
    monkeypatch.setattr(offline_fixer.windows_fixer, "is_windows", lambda self, g: False)
    monkeypatch.setattr(offline_fixer.windows_fixer, "windows_bcd_actual_fix", lambda self, g: {"enabled": False})
    monkeypatch.setattr(offline_fixer.windows_fixer, "inject_virtio_drivers", lambda self, g: {"enabled": False})
    monkeypatch.setattr(offline_fixer, "write_report", lambda self: None)

    image = tmp_path / "disk.qcow2"
    image.write_bytes(b"fake")

    fx = offline_fixer.OfflineFSFix(
        logger=FakeLogger(),
        image=image,
        dry_run=True,
        no_backup=True,
        print_fstab=False,
        update_grub=False,
        regen_initramfs=True,
        fstab_mode=_pick_fstab_mode(offline_fixer),
        report_path=None,
        remove_vmware_tools=False,
        inject_cloud_init=None,
        recovery_manager=None,
        resize=None,
        virtio_drivers_dir=None,
        luks_enable=False,
    )
    fx.run()
    assert isinstance(fx.report, dict)
    assert "validation" in fx.report
