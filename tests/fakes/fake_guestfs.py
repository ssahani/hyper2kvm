from __future__ import annotations

class FakeGuestFS:
    '''
    Tiny libguestfs-ish fake for unit tests.
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

    def set_trace(self, *_a, **_k): return None
    def add_drive_opts(self, *_a, **_k): return None
    def launch(self): return None
    def close(self): return None

    def inspect_os(self): return list(self.inspect_roots)
    def inspect_get_mountpoints(self, _root): return dict(self.inspect_mp)
    def inspect_get_type(self, _root): return "linux"
    def inspect_get_product_name(self, _root): return "FakeOS"
    def inspect_get_distro(self, _root): return "fake"
    def inspect_get_major_version(self, _root): return 1
    def inspect_get_minor_version(self, _root): return 0

    def list_partitions(self): return list(self.parts)
    def list_filesystems(self): return dict(self.listfs)
    def lvs(self): return []

    def is_file(self, p): return p in self.fs
    def is_dir(self, p): return p in self.dirs

    def read_file(self, p): return self.fs[p]
    def write(self, p, data): self.fs[p] = bytes(data)
    def cp(self, src, dst): self.fs[dst] = self.fs[src]
    def rm_f(self, p): self.fs.pop(p, None)

    def mkdir_p(self, p): self.dirs.add(p)
    def chmod(self, *_a, **_k): return None

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
