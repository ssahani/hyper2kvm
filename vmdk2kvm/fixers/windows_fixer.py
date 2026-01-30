# vmdk2kvm/fixers/windows_fixer.py
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import guestfs  # type: ignore

from ..core.utils import U


# ---------------------------
# Windows Helpers / Policy
# ---------------------------

@dataclass(frozen=True)
class WindowsVirtioPlan:
    arch_dir: str          # "amd64" | "x86"
    os_bucket: str         # "w10" | "w8" | "w7" | "xp"
    storage_service: str   # "vioscsi" | "viostor"


def _norm_arch_to_dir(arch: str) -> str:
    a = (arch or "").lower()
    if a in ("x86_64", "amd64"):
        return "amd64"
    if a in ("i386", "i686", "x86"):
        return "x86"
    return "amd64"


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


# ---------------------------
# Windows Detection
# ---------------------------

def is_windows(self, g: guestfs.GuestFS) -> bool:
    """
    IMPORTANT:
      - This is a module-level helper that takes (self, g).
      - Do NOT call self.is_windows() unless OfflineFSFix explicitly defines it.
      - Other helpers in this module call *this function* directly.
    """
    if not getattr(self, "inspect_root", None):
        return False
    try:
        t = U.to_text(g.inspect_get_type(self.inspect_root))
        return t.lower() == "windows"
    except Exception:
        return False


def _find_windows_root(self, g: guestfs.GuestFS) -> Optional[str]:
    for p in ("/Windows", "/WINDOWS", "/winnt", "/WINNT"):
        try:
            if g.is_dir(p):
                return p
        except Exception:
            continue
    return None


def _windows_version_info(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    info: Dict[str, Any] = {"windows": True}
    if not getattr(self, "inspect_root", None):
        return info

    try:
        info["arch"] = U.to_text(g.inspect_get_arch(self.inspect_root))
    except Exception:
        info["arch"] = None

    for k, fn in (
        ("major", g.inspect_get_major_version),
        ("minor", g.inspect_get_minor_version),
        ("product_name", g.inspect_get_product_name),
    ):
        try:
            info[k] = fn(self.inspect_root)
        except Exception:
            info[k] = None

    return info


def _choose_driver_bucket(self, win_info: Dict[str, Any]) -> WindowsVirtioPlan:
    arch_dir = _norm_arch_to_dir(str(win_info.get("arch") or "amd64"))
    major = _to_int(win_info.get("major"), 0)
    minor = _to_int(win_info.get("minor"), 0)
    product = str(win_info.get("product_name") or "").lower()

    if "server 2022" in product or "server 2019" in product or "server 2016" in product:
        os_bucket = "w10"
    elif "server 2012" in product:
        os_bucket = "w8"
    elif "server 2008" in product:
        os_bucket = "w7"
    elif major >= 10:
        os_bucket = "w10"
    elif major == 6 and minor >= 2:
        os_bucket = "w8"
    elif major == 6:
        os_bucket = "w7"
    elif major == 5:
        os_bucket = "xp"
    else:
        os_bucket = "w10"

    storage_service = "vioscsi" if os_bucket in ("w10", "w8", "w7") else "viostor"
    return WindowsVirtioPlan(arch_dir=arch_dir, os_bucket=os_bucket, storage_service=storage_service)


# ---------------------------
# Windows BCD Actual Implementation (offline-safe)
# ---------------------------

def windows_bcd_actual_fix(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    """
    Offline-safe:
      - detect Windows
      - locate likely BCD stores
      - backup stores (unless dry_run)
      - do NOT attempt deep BCD edits offline (no bcdedit)
    """
    if not is_windows(self, g):
        return {"windows": False}

    self.logger.info("Windows detected - attempting BCD checks/fixes (offline-safe)")

    windows_root = _find_windows_root(self, g)
    if not windows_root:
        return {"windows": True, "bcd": "no_windows_directory"}

    bios_bcd = f"{windows_root}/Boot/BCD"
    uefi_candidates = [
        "/boot/efi/EFI/Microsoft/Boot/BCD",
        "/boot/EFI/Microsoft/Boot/BCD",
        "/efi/EFI/Microsoft/Boot/BCD",
        "/EFI/Microsoft/Boot/BCD",
    ]

    found: Dict[str, str] = {}
    try:
        if g.is_file(bios_bcd):
            found["bios"] = bios_bcd
    except Exception:
        pass

    for p in uefi_candidates:
        try:
            if g.is_file(p):
                found["uefi"] = p
                break
        except Exception:
            continue

    if not found:
        self.logger.warning("No BCD store found (BIOS or UEFI)")
        return {"windows": True, "bcd": "no_bcd_store"}

    details: Dict[str, Any] = {"windows": True, "bcd": "found", "stores": found}

    for kind, bcd_path in found.items():
        try:
            bcd_size = g.filesize(bcd_path)
            self.logger.info(f"BCD ({kind}) store: {bcd_path} size={bcd_size} bytes")
            details[f"{kind}_size"] = bcd_size

            if not getattr(self, "dry_run", False):
                backup_path = f"{bcd_path}.backup.vmdk2kvm.{U.now_ts()}"
                g.cp(bcd_path, backup_path)
                self.logger.info(f"BCD ({kind}) backup created: {backup_path}")
                details[f"{kind}_backup"] = backup_path
        except Exception as e:
            self.logger.warning(f"BCD ({kind}) inspection failed: {e}")
            details[f"{kind}_error"] = str(e)

    details["note"] = "Offline-safe: backed up + validated presence. Deep BCD editing requires bcdedit/bootrec inside Windows."
    return details


# ---------------------------
# Virtio + KVM enablement for Windows (offline best-effort)
# ---------------------------

def inject_virtio_drivers(self, g: guestfs.GuestFS) -> Dict[str, Any]:
    if not getattr(self, "virtio_drivers_dir", None) or not Path(self.virtio_drivers_dir).exists():
        return {"injected": False, "reason": "no_dir"}
    if not is_windows(self, g):
        return {"injected": False, "reason": "not_windows"}
    if not getattr(self, "inspect_root", None):
        return {"injected": False, "reason": "no_inspect"}

    windows_root = _find_windows_root(self, g)
    if not windows_root:
        return {"injected": False, "reason": "no_windows_root"}

    win_info = _windows_version_info(self, g)
    plan = _choose_driver_bucket(self, win_info)

    base = Path(self.virtio_drivers_dir)
    arch = plan.arch_dir
    bkt = plan.os_bucket

    def find_sys(driver: str) -> Optional[Path]:
        candidates = [
            base / f"{driver}/{bkt}/{arch}/{driver.lower()}.sys",
            base / f"{driver}/{bkt}/{arch}/{driver}.sys",
            base / f"{driver}/{arch}/{driver.lower()}.sys",
            base / f"{driver}/{arch}/{driver}.sys",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    viostor_sys = find_sys("viostor")
    vioscsi_sys = find_sys("vioscsi")
    netkvm_sys = find_sys("NetKVM") or find_sys("netkvm")
    balloon_sys = find_sys("Balloon") or find_sys("balloon")

    drivers_dir = f"{windows_root}/System32/drivers"
    try:
        if not g.is_dir(drivers_dir):
            return {"injected": False, "reason": "no_drivers_dir"}
    except Exception:
        return {"injected": False, "reason": "no_drivers_dir"}

    injected: Dict[str, Any] = {"injected": True, "windows": win_info, "plan": plan.__dict__, "files": {}}

    def upload_sys(srcp: Optional[Path], dst_name: str) -> bool:
        if not srcp or not srcp.exists():
            return False
        dst = f"{drivers_dir}/{dst_name}"
        if not getattr(self, "dry_run", False):
            g.upload(str(srcp), dst)
        self.logger.info(f"Injected {srcp} -> {dst}")
        injected["files"][dst_name] = str(srcp)
        return True

    have_viostor = upload_sys(viostor_sys, "viostor.sys")
    have_vioscsi = upload_sys(vioscsi_sys, "vioscsi.sys")
    have_netkvm = upload_sys(netkvm_sys, "netkvm.sys")
    have_balloon = upload_sys(balloon_sys, "balloon.sys")

    hive_guest = f"{windows_root}/System32/config/SYSTEM"
    try:
        if not g.is_file(hive_guest):
            injected["registry"] = False
            injected["registry_reason"] = "no_hive"
            return injected
    except Exception:
        injected["registry"] = False
        injected["registry_reason"] = "no_hive"
        return injected

    with tempfile.TemporaryDirectory() as td:
        local_hive = Path(td) / "SYSTEM"
        g.download(hive_guest, str(local_hive))

        write = 0 if getattr(self, "dry_run", False) else 1
        try:
            h = g.hivex_open(str(local_hive), write=write)
            root = h.root()

            select = h.node_get_child(root, "Select")
            if select is None:
                raise RuntimeError("No Select node")

            val = h.node_get_value(select, "Current")
            if val is None:
                raise RuntimeError("No Current value")

            current = int.from_bytes(val["value"], "little")
            cs_name = f"ControlSet{current:03d}"
            cs = h.node_get_child(root, cs_name)
            if cs is None:
                raise RuntimeError(f"No {cs_name}")

            services = h.node_get_child(cs, "Services") or h.node_add_child(cs, "Services")

            def ensure_service(name: str, image_path: str, start: int) -> None:
                node = h.node_get_child(services, name) or h.node_add_child(services, name)
                h.node_set_value(node, dict(key="Type", t=4, value=(1).to_bytes(4, "little")))
                h.node_set_value(node, dict(key="Start", t=4, value=(start).to_bytes(4, "little")))
                h.node_set_value(node, dict(key="ErrorControl", t=4, value=(1).to_bytes(4, "little")))
                h.node_set_value(node, dict(key="ImagePath", t=1, value=image_path.encode("utf-8") + b"\0"))
                h.node_set_value(node, dict(key="Group", t=1, value=b"Boot Bus Extender\0"))

            # storage: boot-start (0)
            if have_viostor:
                ensure_service("viostor", r"system32\drivers\viostor.sys", start=0)
            if have_vioscsi:
                ensure_service("vioscsi", r"system32\drivers\vioscsi.sys", start=0)

            # net/balloon: auto (2)
            if have_netkvm:
                ensure_service("netkvm", r"system32\drivers\netkvm.sys", start=2)
            if have_balloon:
                ensure_service("balloon", r"system32\drivers\balloon.sys", start=2)

            control = h.node_get_child(cs, "Control") or h.node_add_child(cs, "Control")
            cdd = h.node_get_child(control, "CriticalDeviceDatabase") or h.node_add_child(control, "CriticalDeviceDatabase")

            class_guid_disk = "{4D36E967-E325-11CE-BFC1-08002BE10318}"

            def add_cdd(pci_id: str, service: str) -> None:
                node = h.node_get_child(cdd, pci_id) or h.node_add_child(cdd, pci_id)
                h.node_set_value(node, dict(key="Service", t=1, value=service.encode("utf-8") + b"\0"))
                h.node_set_value(node, dict(key="ClassGUID", t=1, value=class_guid_disk.encode("utf-8") + b"\0"))

            if have_viostor:
                add_cdd("pci#ven_1af4&dev_1001&subsys_00081af4", "viostor")
                add_cdd("pci#ven_1af4&dev_1042&subsys_00081af4", "viostor")
            if have_vioscsi:
                add_cdd("pci#ven_1af4&dev_1004&subsys_00081af4", "vioscsi")
                add_cdd("pci#ven_1af4&dev_1048&subsys_00081af4", "vioscsi")

            h.hivex_commit(None)
            h.hivex_close()

            if not getattr(self, "dry_run", False):
                g.upload(str(local_hive), hive_guest)

            self.logger.info("Virtio registry entries added/updated")
            injected["registry"] = True
            injected["enabled"] = {
                "viostor": bool(have_viostor),
                "vioscsi": bool(have_vioscsi),
                "netkvm": bool(have_netkvm),
                "balloon": bool(have_balloon),
            }
            injected["notes"] = [
                "Storage drivers set to boot-start when injected.",
                "CriticalDeviceDatabase updated for common virtio PCI IDs.",
                "Network/balloon set to auto-start when injected.",
                "Deep INF installation is not performed offline; Windows may still run PnP on first boot.",
            ]
            return injected

        except Exception as e:
            self.logger.warning(f"Registry edit failed: {e}")
            injected["registry"] = False
            injected["error"] = str(e)
            return injected
