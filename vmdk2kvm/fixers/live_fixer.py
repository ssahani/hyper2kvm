from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..core.utils import U
from ..ssh.ssh_client import SSHClient
from .live_grub_fixer import LiveGrubFixer


@dataclass(frozen=True)
class LiveFixerOptions:
    dry_run: bool
    no_backup: bool
    print_fstab: bool
    update_grub: bool
    regen_initramfs: bool
    remove_vmware_tools: bool = False


@dataclass(frozen=True)
class OSInfo:
    id: str
    id_like: List[str]
    version_id: str
    major: int

    @property
    def family(self) -> str:
        """
        Coarse distro family buckets for tool choice.
        Prefer ID_LIKE, fall back to ID.
        """
        d = (self.id or "").lower()
        like = {x.lower() for x in (self.id_like or [])}

        # Debian-ish
        if d in {"debian", "ubuntu", "linuxmint", "pop", "kali"}:
            return "debian"
        if {"debian", "ubuntu"} & like:
            return "debian"

        # RHEL-ish
        if d in {"rhel", "centos", "fedora", "rocky", "almalinux", "oraclelinux", "ol", "redhat"}:
            return "rhel"
        if {"rhel", "fedora", "centos", "redhat"} & like:
            return "rhel"

        # SUSE-ish
        if d in {"sles", "sled", "opensuse", "opensuse-leap", "opensuse-tumbleweed", "suse"}:
            return "suse"
        if "suse" in like:
            return "suse"

        # Arch-ish
        if d in {"arch", "manjaro", "endeavouros", "garuda"}:
            return "arch"
        if "arch" in like:
            return "arch"

        # Alpine
        if d == "alpine" or "alpine" in like:
            return "alpine"

        # Gentoo
        if d == "gentoo" or "gentoo" in like:
            return "gentoo"

        # Void
        if d == "void" or "void" in like:
            return "void"

        # NixOS
        if d == "nixos" or "nixos" in like:
            return "nixos"

        return "unknown"


class LiveFixer:
    """
    Live fix via SSH:

      - Rewrite /etc/fstab: /dev/disk/by-path/* -> UUID=/PARTUUID=/LABEL=/PARTLABEL= (best-effort)
      - Optionally run LiveGrubFixer (preferred) to stabilize root= and cmdline sources
      - Optionally regenerate initramfs + bootloader configs (best-effort across distros)
      - Optionally remove VMware tools (best-effort across distros)

    Design goals:
      - Safe defaults + best-effort behavior
      - Minimal assumptions about distro/tooling
      - Deterministic edits: atomic writes + timestamped backups (unless disabled)
    """

    def __init__(
        self,
        logger: logging.Logger,
        sshc: SSHClient,
        *,
        dry_run: bool,
        no_backup: bool,
        print_fstab: bool,
        update_grub: bool,
        regen_initramfs: bool,
        remove_vmware_tools: bool = False,
    ):
        self.logger = logger
        self.sshc = sshc
        self.opts = LiveFixerOptions(
            dry_run=dry_run,
            no_backup=no_backup,
            print_fstab=print_fstab,
            update_grub=update_grub,
            regen_initramfs=regen_initramfs,
            remove_vmware_tools=remove_vmware_tools,
        )

    # ---------------------------------------------------------------------
    # SSH helpers
    # ---------------------------------------------------------------------
    def _ssh(self, cmd: str) -> str:
        self.logger.debug("SSH: %s", cmd)
        return self.sshc.ssh(cmd) or ""

    def _has(self, cmd: str) -> bool:
        return (
            self._ssh(f"command -v {shlex.quote(cmd)} >/dev/null 2>&1 && echo YES || echo NO").strip()
            == "YES"
        )

    def _remote_exists(self, path: str) -> bool:
        out = self._ssh(f"test -e {shlex.quote(path)} && echo OK || echo NO").strip()
        return out == "OK"

    def _read_remote_file(self, path: str) -> str:
        return self._ssh(f"cat {shlex.quote(path)} 2>/dev/null || true")

    def _write_remote_file_atomic(self, path: str, content: str, mode: str = "0644") -> None:
        """
        Atomic-ish update:
          - mktemp in /tmp
          - write content
          - chmod
          - mv over target
        """
        tmp = self._ssh("mktemp /tmp/vmdk2kvm.livefix.XXXXXX").strip()
        if not tmp:
            raise RuntimeError("mktemp failed on remote host")

        payload = (
            f"cat > {shlex.quote(tmp)} <<'EOF'\n"
            f"{content}\n"
            "EOF\n"
            f"chmod {shlex.quote(mode)} {shlex.quote(tmp)} || true\n"
        )
        self._ssh("sh -lc " + shlex.quote(payload))
        self._ssh(f"mv -f {shlex.quote(tmp)} {shlex.quote(path)}")

    def _readlink_f(self, path: str) -> Optional[str]:
        out = self._ssh(f"readlink -f -- {shlex.quote(path)} 2>/dev/null || true").strip()
        return out or None

    def _is_remote_blockdev(self, dev: str) -> bool:
        return self._ssh(f"test -b {shlex.quote(dev)} && echo OK || echo NO").strip() == "OK"

    def _blkid(self, dev: str, key: str) -> Optional[str]:
        out = self._ssh(
            f"blkid -s {shlex.quote(key)} -o value -- {shlex.quote(dev)} 2>/dev/null || true"
        ).strip()
        return out or None

    def _run_best_effort(self, cmds: List[str]) -> None:
        """
        Run a list of commands. No exceptions; each command is best-effort.
        """
        for c in cmds:
            if not c.strip():
                continue
            self._ssh(c)

    # ---------------------------------------------------------------------
    # OS detection (/etc/os-release)
    # ---------------------------------------------------------------------
    def _os_release(self) -> Dict[str, str]:
        """
        Parse /etc/os-release remotely into a dict.
        Output values are de-quoted.
        """
        out = self._ssh(
            r"""sh -lc 'test -r /etc/os-release || exit 0; \
awk -F= "
/^[A-Z0-9_]+=/ {
  k=\$1; v=\$2;
  sub(/^\"/,\"\",v); sub(/\"$/,\"\",v);
  sub(/^'\''/,\"\",v); sub(/'\''$/,\"\",v);
  print k \"=\" v
}" /etc/os-release'"""
        )
        d: Dict[str, str] = {}
        for line in (out or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
        return d

    def _detect_os(self) -> OSInfo:
        d = self._os_release()
        os_id = (d.get("ID") or "").strip().lower() or "unknown"
        id_like_raw = (d.get("ID_LIKE") or "").strip().lower()
        id_like = [x for x in re.split(r"[\s,]+", id_like_raw) if x] if id_like_raw else []
        ver = (d.get("VERSION_ID") or "").strip()
        major = 0
        m = re.match(r"^(\d+)", ver)
        if m:
            try:
                major = int(m.group(1))
            except Exception:
                major = 0
        return OSInfo(id=os_id, id_like=id_like, version_id=ver, major=major)

    # ---------------------------------------------------------------------
    # fstab rewrite
    # ---------------------------------------------------------------------
    def _convert_spec_to_stable(self, spec: str) -> str:
        """
        Convert /dev/disk/by-path/* to a stable spec, preferring:
          UUID=, PARTUUID=, LABEL=, PARTLABEL=
        """
        resolved = self._readlink_f(spec)
        if not resolved:
            self.logger.debug("fstab: readlink -f failed for %s", spec)
            return spec

        if not self._is_remote_blockdev(resolved):
            self.logger.debug("fstab: resolved path is not a block dev: %s -> %s", spec, resolved)
            return spec

        for key, prefix in (
            ("UUID", "UUID="),
            ("PARTUUID", "PARTUUID="),
            ("LABEL", "LABEL="),
            ("PARTLABEL", "PARTLABEL="),
        ):
            v = self._blkid(resolved, key)
            if v:
                return prefix + v

        return spec

    @staticmethod
    def _split_comment(line: str) -> Tuple[str, str]:
        """
        Split a line into (data, comment) where comment begins at whitespace + '#'.
        Full-line comments are returned as (line, "").
        """
        s = line.rstrip("\n")
        if not s.strip():
            return s, ""
        if s.lstrip().startswith("#"):
            return s, ""
        m = re.search(r"\s#", s)
        if not m:
            return s, ""
        i = m.start()
        return s[:i].rstrip(), s[i:].lstrip()

    def _rewrite_fstab(self, content: str) -> Tuple[str, int]:
        changed = 0
        out_lines: List[str] = []

        for line in content.splitlines(keepends=False):
            if not line.strip() or line.lstrip().startswith("#"):
                out_lines.append(line + "\n")
                continue

            data, comment = self._split_comment(line)
            parts = data.split()
            if len(parts) < 2:
                out_lines.append(line + "\n")
                continue

            spec = parts[0]
            if spec.startswith("/dev/disk/by-path/"):
                new_spec = self._convert_spec_to_stable(spec)
                if new_spec != spec:
                    parts[0] = new_spec
                    changed += 1

            rebuilt = "\t".join(parts)
            if comment:
                if not comment.startswith("#"):
                    comment = "# " + comment
                rebuilt = rebuilt + "\t" + comment

            out_lines.append(rebuilt.rstrip() + "\n")

        return "".join(out_lines), changed

    # ---------------------------------------------------------------------
    # VMware tools removal (multi-distro best-effort)
    # ---------------------------------------------------------------------
    def _remove_vmware_tools(self) -> None:
        self.logger.info("Removing VMware tools (live)...")

        pkgs = [
            "open-vm-tools",
            "open-vm-tools-desktop",
            "vmware-tools",
            "vmware-tools-desktop",
            "vmtoolsd",
        ]

        if self._has("apt-get"):
            self._run_best_effort(
                [
                    "DEBIAN_FRONTEND=noninteractive apt-get remove -y "
                    + " ".join(map(shlex.quote, pkgs))
                    + " 2>/dev/null || true",
                    "DEBIAN_FRONTEND=noninteractive apt-get autoremove -y 2>/dev/null || true",
                ]
            )
        elif self._has("dnf"):
            self._run_best_effort(
                ["dnf remove -y " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("yum"):
            self._run_best_effort(
                ["yum remove -y " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("zypper"):
            self._run_best_effort(
                ["zypper -n rm " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("pacman"):
            self._run_best_effort(
                ["pacman -Rns --noconfirm " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("apk"):
            self._run_best_effort(["apk del " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"])
        elif self._has("xbps-remove"):
            self._run_best_effort(
                ["xbps-remove -Ry " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"]
            )
        elif self._has("emerge"):
            # Gentoo atoms may differ; still try the obvious.
            self._run_best_effort(["emerge -C " + " ".join(map(shlex.quote, pkgs)) + " 2>/dev/null || true"])
        else:
            self.logger.warning("No known package manager found; skipping package removal.")

        # Service cleanup (systemd/OpenRC best-effort)
        self._run_best_effort(
            [
                "systemctl disable --now vmware-tools 2>/dev/null || true",
                "systemctl disable --now vmtoolsd 2>/dev/null || true",
                "rc-service vmware-tools stop 2>/dev/null || true",
                "rc-service vmtoolsd stop 2>/dev/null || true",
                "rc-update del vmware-tools default 2>/dev/null || true",
                "rc-update del vmtoolsd default 2>/dev/null || true",
                "rm -f /etc/init.d/vmware-tools /etc/init.d/vmtoolsd 2>/dev/null || true",
                "rm -f /etc/systemd/system/vmware-tools.service /etc/systemd/system/vmtoolsd.service 2>/dev/null || true",
            ]
        )

        # Tarball uninstaller (if present)
        uninstaller = "/usr/bin/vmware-uninstall-tools.pl"
        if self._remote_exists(uninstaller):
            self._run_best_effort([f"{shlex.quote(uninstaller)} 2>/dev/null || true"])

        self.logger.info("VMware tools removal attempted.")

    # ---------------------------------------------------------------------
    # initramfs + bootloader regeneration (multi-distro)
    # ---------------------------------------------------------------------
    def _regen_initramfs_and_boot(self) -> None:
        osinfo = self._detect_os()
        self.logger.info("Regen: distro=%s family=%s version_id=%s", osinfo.id, osinfo.family, osinfo.version_id)

        # ---------------------------
        # initramfs rebuild
        # ---------------------------
        if osinfo.family == "debian":
            self._run_best_effort(
                [
                    "update-initramfs -u -k all 2>/dev/null || true",
                    "update-initramfs -u 2>/dev/null || true",
                ]
            )

        elif osinfo.family == "arch":
            self._run_best_effort(
                [
                    "mkinitcpio -P 2>/dev/null || true",
                    "dracut -f 2>/dev/null || true",
                ]
            )

        elif osinfo.family == "alpine":
            # Alpine often uses mkinitfs; diskless setups may skip.
            self._run_best_effort(
                [
                    "mkinitfs 2>/dev/null || true",
                    "mkinitfs -c /etc/mkinitfs/mkinitfs.conf 2>/dev/null || true",
                ]
            )

        elif osinfo.family == "gentoo":
            self._run_best_effort(
                [
                    "genkernel --install initramfs 2>/dev/null || true",
                    "dracut -f 2>/dev/null || true",
                ]
            )

        elif osinfo.family == "void":
            self._run_best_effort(
                [
                    "dracut -f 2>/dev/null || dracut -f --regenerate-all 2>/dev/null || true",
                    "mkinitcpio -P 2>/dev/null || true",
                ]
            )

        elif osinfo.family == "nixos":
            # Declarative. Without knowing the channel/flakes, don't poke it.
            self.logger.warning("NixOS detected: initrd rebuild is declarative; skipping initramfs regeneration.")
        else:
            # rhel / suse / unknown: dracut first, mkinitrd fallback.
            self._run_best_effort(
                [
                    "dracut -f 2>/dev/null || dracut -f --regenerate-all 2>/dev/null || true",
                    "mkinitrd 2>/dev/null || true",
                ]
            )

        # ---------------------------
        # bootloader config rebuild (best-effort)
        # ---------------------------
        cmds: List[str] = []

        # Debian helper
        if self._has("update-grub"):
            cmds.append("update-grub 2>/dev/null || true")

        # systemd BLS based distros often still want grub2-mkconfig for legacy paths
        cmds.extend(
            [
                # BIOS-ish common paths
                "grub2-mkconfig -o /boot/grub2/grub.cfg 2>/dev/null || true",
                "grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true",
                "grub-mkconfig -o /boot/grub2/grub.cfg 2>/dev/null || true",
                # UEFI common paths (best-effort guesses; harmless if absent)
                "grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg 2>/dev/null || true",
                "grub2-mkconfig -o /boot/efi/EFI/centos/grub.cfg 2>/dev/null || true",
                "grub2-mkconfig -o /boot/efi/EFI/fedora/grub.cfg 2>/dev/null || true",
                "grub2-mkconfig -o /boot/efi/EFI/opensuse/grub.cfg 2>/dev/null || true",
                "grub2-mkconfig -o /boot/efi/EFI/ubuntu/grub.cfg 2>/dev/null || true",
            ]
        )

        # extlinux/syslinux fallback (often Alpine, sometimes minimal installs)
        cmds.extend(
            [
                "extlinux --install /boot 2>/dev/null || true",
                "syslinux -i /dev/sda 2>/dev/null || true",  # harmless if syslinux missing; still best-effort
            ]
        )

        self._run_best_effort(cmds)
        self.logger.info("Regen completed (best-effort).")

    # ---------------------------------------------------------------------
    # Entrypoint
    # ---------------------------------------------------------------------
    def run(self) -> None:
        U.banner(self.logger, "Live fix (SSH)")
        self.sshc.check()

        # ---- fstab rewrite
        fstab = self._read_remote_file("/etc/fstab")
        if self.opts.print_fstab:
            print("\n--- /etc/fstab (live before) ---\n" + (fstab or ""))

        new_fstab, changed = self._rewrite_fstab(fstab or "")
        self.logger.info("fstab (live): changed_entries=%d", changed)

        if self.opts.print_fstab:
            print("\n--- /etc/fstab (live after) ---\n" + (new_fstab or ""))

        if changed > 0:
            if self.opts.dry_run:
                self.logger.info("DRY-RUN: would update /etc/fstab (live).")
            else:
                if not self.opts.no_backup:
                    b = f"/etc/fstab.bak.vmdk2kvm.{U.now_ts()}"
                    self._ssh(f"cp -a /etc/fstab {shlex.quote(b)} 2>/dev/null || true")
                    self.logger.info("Backup: /etc/fstab -> %s", b)
                self._write_remote_file_atomic("/etc/fstab", new_fstab, mode="0644")
                self.logger.info("/etc/fstab updated (live).")

        # ---- optional VMware tools removal
        if self.opts.remove_vmware_tools:
            if self.opts.dry_run:
                self.logger.info("DRY-RUN: would remove VMware tools (live).")
            else:
                self._remove_vmware_tools()

        # ---- preferred GRUB fixer
        if self.opts.update_grub:
            self.logger.info("Running LiveGrubFixer...")
            if self.opts.dry_run:
                self.logger.info("DRY-RUN: skipping LiveGrubFixer execution.")
            else:
                LiveGrubFixer(logger=self.logger, ssh_client=self.sshc).run()

        # ---- optional regen
        if self.opts.regen_initramfs:
            if self.opts.dry_run:
                self.logger.info("DRY-RUN: would regenerate initramfs + bootloader config.")
            else:
                self._regen_initramfs_and_boot()

        self.logger.info("Live fix completed.")
