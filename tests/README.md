# vmdk2kvm tests (drop-in)

Unzip this archive **inside your repo-root `tests/` directory**:

```bash
cd /path/to/repo
unzip vmdk2kvm_tests_fix2.zip -d tests
pytest -q
```

The included `tests/conftest.py` ensures the repo root is on `sys.path` when you run pytest from `./tests`.
