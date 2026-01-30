# SPDX-License-Identifier: LGPL-3.0-or-later
from __future__ import annotations


class FakeGuestFS:
    '''
    Tiny VMCraft-like fake for unit tests.
    Only implements methods these tests need.
    '''
    def __init__(self):
        self.fs = {}          # path -> bytes
        self.dirs = set()     # dir paths
        self.inspect_roots = ["/dev/sda2"]
        self.inspect_mp = {"/": "/dev/sda2"}
        self.listfs = {"/dev/sda2": "ext4"}
        self.parts = ["/dev/sda2"]

        self._mounted = False
        self._mounted_dev = None
        self._mount_local_started = False

        # Add common systemd paths by default (for testing)
        self.fs["/usr/lib/systemd/systemd"] = b""
        self.fs["/usr/bin/systemctl"] = b""
        self.dirs.add("/etc/systemd/system")
        self.dirs.add("/usr/lib/systemd/system")

    def set_trace(self, *_a, **_k): return None
    def add_drive_opts(self, *_a, **_k): return None
    def launch(self): return None
    def shutdown(self): return None
    def close(self): return None

    def inspect_os(self): return list(self.inspect_roots)
    def inspect_get_mountpoints(self, _root): return dict(self.inspect_mp)
    def inspect_get_type(self, _root): return "linux"
    def inspect_get_product_name(self, _root): return "FakeOS"
    def inspect_get_distro(self, _root): return "fake"
    def inspect_get_major_version(self, _root): return 1
    def inspect_get_minor_version(self, _root): return 0
    def inspect_get_arch(self, _root): return "x86_64"

    def list_partitions(self): return list(self.parts)
    def list_filesystems(self): return dict(self.listfs)
    def lvs(self): return []

    def is_file(self, p): return p in self.fs
    def is_dir(self, p): return p in self.dirs
    def exists(self, p): return p in self.fs or p in self.dirs

    def read_file(self, p): return self.fs.get(p, b"")
    def cat(self, p): return self.fs.get(p, b"").decode('utf-8', errors='replace')
    def write(self, p, data): self.fs[p] = bytes(data) if isinstance(data, bytes) else data.encode('utf-8')
    def cp(self, src, dst): self.fs[dst] = self.fs[src]
    def rm_f(self, p): self.fs.pop(p, None)
    def touch(self, p): self.fs.setdefault(p, b"")

    def mkdir_p(self, p): self.dirs.add(p)
    def chmod(self, *_a, **_k): return None
    def ln_sf(self, target, link_name):
        """Create a symlink (force overwrite)"""
        self.fs[link_name] = f"link->{target}".encode() if isinstance(target, str) else b"link->" + target

    def mount(self, dev, mp):
        if mp != "/":
            raise RuntimeError("FakeGuestFS supports only / mount")
        self._mounted = True
        self._mounted_dev = dev

    def mount_ro(self, dev, mp): return self.mount(dev, mp)
    def mount_options(self, _opts, dev, mp): return self.mount(dev, mp)

    def umount_all(self):
        self._mounted = False
        self._mounted_dev = None

    def vfs_type(self, dev):
        return self.listfs.get(dev, "")

    def vfs_uuid(self, dev):
        return f"uuid-{dev.replace('/', '-')}"

    def vfs_label(self, dev):
        return f"label-{dev.replace('/', '-')}"

    def blockdev_getsize64(self, dev):
        return 10 * 1024 * 1024 * 1024  # 10GB

    def list_devices(self):
        return ["/dev/sda"]

    def mountpoints(self):
        return ["/"] if self._mounted else []

    def mounts(self):
        return [self._mounted_dev] if self._mounted and self._mounted_dev else []

    def realpath(self, path):
        # Simple implementation - just return the path
        # In real guestfs, this resolves symlinks
        return path

    def readlink(self, path):
        # Simple implementation for symlinks
        content = self.fs.get(path, b"")
        if content.startswith(b"link->"):
            return content[6:].decode('utf-8')
        raise RuntimeError(f"{path} is not a symlink")

    def ls(self, d):
        out = []
        dp = d.rstrip("/") + "/"
        for p in set(self.fs.keys()).union(self.dirs):
            if p.startswith(dp):
                rest = p[len(dp):]
                if rest and "/" not in rest:
                    out.append(rest)
        return sorted(out)

    def find(self, d):
        out = []
        dp = d.rstrip("/") + "/"
        for p in set(self.fs.keys()).union(self.dirs):
            if p.startswith(dp):
                out.append(p)
        return sorted(out)

    def command(self, cmd):
        return ""

    def statvfs(self, _p):
        return {"bsize": 4096, "blocks": 1000, "bfree": 500}

    def sync(self): return None

    def mount_local(self, _mountpoint): self._mount_local_started = True
    def mount_local_run(self): return None
    def umount_local(self): self._mount_local_started = False

    # Storage stack methods
    def vgscan(self): return None
    def vgchange_activate_all(self, _enable): return None
    def cryptsetup_open(self, _device, _name, _key): raise NotImplementedError("cryptsetup_open not supported in FakeGuestFS")
