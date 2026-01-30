# hyper2kvm Improvement Roadmap

**Generated**: 2026-01-18
**Status**: Active Development
**Based on**: Comprehensive codebase analysis

## 📊 Current State Assessment

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| **Type Hint Coverage** | ~70% | 95% | 25% |
| **Test Pass Rate** | 96.6% (144/149) | 99%+ | 2.4% |
| **Docstring Coverage** | ~60% | 85% | 25% |
| **Code Quality** | Good | Excellent | Standardization needed |
| **Security Review** | Partial | Complete | Full audit |
| **Performance Baseline** | None | Established | Benchmarking needed |

## 🚨 Critical Issues (Fix Immediately)

### 1. Bare Exception Handlers ⚠️

**Files**: `hyper2kvm/daemon/daemon_watcher.py`
**Lines**: 408, 763
**Risk**: High - Can catch SystemExit, KeyboardInterrupt

```python
# CURRENT (DANGEROUS)
except:
    pass

# FIX TO
except Exception as e:
    logger.debug(f"Operation failed: {e}")
    # or handle specific exceptions
```

**Action Items**:
- [ ] Audit all bare `except:` statements (2 known locations)
- [ ] Replace with specific exception types
- [ ] Add logging for suppressed errors
- [ ] Test with deliberate SystemExit/KeyboardInterrupt

**Effort**: 30 minutes
**Impact**: High (stability, debuggability)

### 2. Assert Statements in Production Code ⚠️

**Files**: 20+ files
**Key Locations**:
- `converters/fetch.py:117` - `assert proc.stdout is not None`
- `converters/qemu/converter.py:259` - `assert last_error is not None`
- `converters/flatten.py:98` - `assert last_err is not None`
- `core/utils.py:117` - `assert proc.stdout is not None`
- `testers/libvirt_tester.py:284` - `assert ovmf is not None`

**Risk**: High - Asserts are removed with Python `-O` flag

```python
# CURRENT (UNSAFE)
assert proc.stdout is not None

# FIX TO
if proc.stdout is None:
    raise RuntimeError("Process stdout unexpectedly closed")
```

**Action Items**:
- [ ] Search codebase for all `assert` statements
- [ ] Replace with proper validation and exceptions
- [ ] Add to pre-commit hooks to prevent future usage
- [ ] Document in CONTRIBUTING.md

**Effort**: 3 hours
**Impact**: High (production reliability)

### 3. Silent Error Suppression (23+ instances)

**File**: `hyper2kvm/fixers/offline_fixer.py`
**Lines**: 209, 233, 244, 255, 260, 264, 273, 285, 294, 315, 413, 511, 559, 569, 574, 579, 584, 607, 612, 618, 636, 640, 645

**Risk**: Medium - Hidden errors make debugging difficult

```python
# CURRENT (SILENT)
try:
    operation()
except:
    pass

# FIX TO
try:
    operation()
except Exception as e:
    logger.debug(f"Expected failure in {context}: {e}")
    if critical_operation:
        raise
```

**Action Items**:
- [ ] Audit all `pass` statements in except blocks
- [ ] Add context-specific logging
- [ ] Determine which errors are truly expected
- [ ] Re-raise critical errors

**Effort**: 4 hours
**Impact**: Medium (debuggability)

### 4. Deleted Test Files 🧪

**Missing Tests** (from git status):
```
D tests/unit/test_cli/test_argparser/test_subcommands.py
D tests/unit/test_cli/test_config.py
D tests/unit/test_config/test_systemd_template.py
D tests/unit/test_converters/test_extractors/test_raw.py
D tests/unit/test_converters/test_fetch.py
D tests/unit/test_converters/test_qemu/test_converter.py
D tests/unit/test_core/test_recovery_manager.py
D tests/unit/test_core/test_utils.py
D tests/unit/test_core/test_validation_suite.py
D tests/unit/test_libvirt/test_linux_domain.py
D tests/unit/test_modes/test_inventory_mode.py
D tests/unit/test_testers/test_qemu_tester.py
```

**Risk**: High - Coverage regression, broken functionality

**Action Items**:
- [ ] Investigate why tests were deleted
- [ ] Restore or rewrite critical tests:
  - `test_core/test_utils.py` (Priority 1)
  - `test_core/test_validation_suite.py` (Priority 1)
  - `test_converters/test_fetch.py` (Priority 2)
  - `test_converters/test_qemu/test_converter.py` (Priority 2)
- [ ] Commit new untracked tests
- [ ] Verify 95%+ test coverage

**Effort**: 8-10 hours
**Impact**: High (regression protection)

## 🎯 High Priority (Next Sprint)

### 5. Type Hint Coverage (70% → 95%)

**Missing Type Hints**:
- Function return types: ~15-20% of public APIs
- Generator functions missing `-> Generator[...]`
- Optional import handling with `type: ignore` (18 files)

**Action Items**:
- [ ] Add return type hints to all public APIs
- [ ] Create `protocols.py` with standard type protocols
- [ ] Replace `type: ignore` with proper TYPE_CHECKING blocks
- [ ] Run mypy with `--strict` flag

**Example Fix**:
```python
# CURRENT
def parse_vmdk(path):
    # type: ignore for optional import
    ...

# FIX TO
from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from .models import VMDKDescriptor

def parse_vmdk(path: Path) -> Optional['VMDKDescriptor']:
    """Parse VMDK descriptor file.

    Args:
        path: Path to VMDK file

    Returns:
        Parsed descriptor or None if invalid

    Raises:
        VMDKError: If parsing fails
    """
    ...
```

**Effort**: 8 hours
**Impact**: High (IDE support, type safety)

### 6. Exception Handling Standardization

**Current State**: 265 exception handlers across 64 files with inconsistent patterns

**Create Exception Hierarchy**:
```python
# core/exceptions.py enhancement

class IOError(Hyper2KvmError):
    """File I/O operations failed."""
    default_code = 10

class NetworkError(Hyper2KvmError):
    """Network/SSH operations failed."""
    default_code = 20

class ParseError(Hyper2KvmError):
    """Parsing/format operations failed."""
    default_code = 30

class ConversionError(Hyper2KvmError):
    """Disk conversion failed."""
    default_code = 40

class ConfigurationError(Hyper2KvmError):
    """Configuration validation failed."""
    default_code = 15
```

**Create Error Wrappers**:
```python
def wrap_io(msg: str, exc: Optional[BaseException] = None, **ctx) -> IOError:
    """Wrap file I/O errors with context."""
    return IOError(msg, context=ctx, original=exc)

def wrap_network(msg: str, exc: Optional[BaseException] = None, **ctx) -> NetworkError:
    """Wrap network errors with context."""
    return NetworkError(msg, context=ctx, original=exc)
```

**Action Items**:
- [ ] Create comprehensive exception hierarchy
- [ ] Add wrapper functions for each category
- [ ] Audit all exception raising sites
- [ ] Document exception usage in CONTRIBUTING.md
- [ ] Add to pre-commit hooks

**Effort**: 5 hours
**Impact**: Medium (consistency, debuggability)

### 7. Logging Standardization

**Issues**:
- Inconsistent log levels
- Inconsistent emoji usage
- Missing progress logging in long operations

**Create Logging Standards**:
```python
# core/logger.py enhancement

class LogLevel:
    """Semantic log level usage guide.

    TRACE: Internal implementation details
    DEBUG: Developer troubleshooting information
    INFO: Major operations and state changes
    WARNING: Recoverable issues user should know
    ERROR: Unrecoverable component errors
    CRITICAL: System-wide failures
    """

def log_operation(logger: Logger, operation: str) -> ContextManager:
    """Context manager for operation logging with timing.

    Usage:
        with log_operation(logger, "Converting VMDK"):
            convert_vmdk(...)
    """
    import time
    start = time.time()
    logger.info(f"⏳ Starting: {operation}")
    try:
        yield
        duration = time.time() - start
        logger.info(f"✅ Completed: {operation} ({duration:.2f}s)")
    except Exception as e:
        duration = time.time() - start
        logger.error(f"❌ Failed: {operation} ({duration:.2f}s): {e}")
        raise
```

**Action Items**:
- [ ] Document log level conventions
- [ ] Create helper for operation logging
- [ ] Add progress callbacks to long operations
- [ ] Standardize emoji usage
- [ ] Add structured logging support (JSON mode)

**Effort**: 4 hours
**Impact**: Medium (debuggability, observability)

## 📚 Documentation Improvements

### 8. Module/Class Docstrings

**Missing Docstrings**:
- `hyper2kvm/fixers/base_fixer.py` - No module docstring
- `hyper2kvm/azure/models.py` - No module docstring
- Multiple `__init__.py` files
- `vmware/clients/client.py` - Minimal class docs
- `fixers/offline_fixer.py` - 650+ lines, many undocumented methods

**Standard Template**:
```python
"""
Module: hyper2kvm.module.submodule

Brief one-line description.

Longer description explaining the module's purpose, design decisions,
and key concepts. Include examples where helpful.

Key Classes:
    ClassName: Brief description

Key Functions:
    function_name: Brief description

Example:
    >>> from hyper2kvm.module import ClassName
    >>> obj = ClassName()
    >>> obj.method()

See Also:
    - Related module 1
    - Related module 2
"""
```

**Action Items**:
- [ ] Add module docstrings to all modules
- [ ] Add class docstrings with usage examples
- [ ] Add method docstrings with Args/Returns/Raises
- [ ] Run pydocstyle to validate
- [ ] Add to pre-commit hooks

**Effort**: 8 hours
**Impact**: Medium (onboarding, maintainability)

### 9. API Documentation Generation

**Missing**:
- No generated API documentation
- No parameter type documentation in docstrings
- No examples in docstrings

**Setup MkDocs Material**:
```bash
pip install mkdocs-material mkdocstrings[python] mkdocs-mermaid2-plugin
```

**Create `mkdocs.yml`**:
```yaml
site_name: hyper2kvm
site_description: Hypervisor to KVM Migration Toolkit
site_url: https://github.com/ssahani/hyper2kvm

theme:
  name: material
  palette:
    - scheme: default
      primary: indigo
      accent: indigo
  features:
    - navigation.tabs
    - navigation.sections
    - toc.integrate
    - search.suggest
    - content.code.annotate

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: true
            show_root_heading: true
  - mermaid2

nav:
  - Home: index.md
  - Getting Started:
      - Installation: getting-started/installation.md
      - Quick Start: getting-started/quickstart.md
  - User Guide:
      - CLI Reference: user-guide/cli.md
      - YAML Examples: user-guide/yaml.md
      - Cookbook: user-guide/cookbook.md
  - API Reference:
      - Core: api/core.md
      - VMware: api/vmware.md
      - Converters: api/converters.md
      - Fixers: api/fixers.md
  - Development:
      - Contributing: development/contributing.md
      - Architecture: development/architecture.md
```

**Action Items**:
- [ ] Install MkDocs Material
- [ ] Create mkdocs.yml configuration
- [ ] Write API documentation templates
- [ ] Add docstring examples to all public APIs
- [ ] Set up GitHub Pages deployment
- [ ] Add "Read the Docs" badge to README

**Effort**: 6 hours
**Impact**: High (discoverability, adoption)

### 10. Operations/Deployment Guide

**Missing Topics**:
- Exit code reference (0-255)
- Performance tuning recommendations
- Resource requirements
- Monitoring setup
- Failover/recovery procedures

**Create `docs/OPERATIONS.md`**:
```markdown
# Operations Guide

## Exit Codes

| Code | Category | Description |
|------|----------|-------------|
| 0 | Success | Operation completed successfully |
| 1-9 | CLI/Args | Command-line argument errors |
| 10-19 | I/O | File I/O errors |
| 20-29 | Network | Network/SSH errors |
| 30-39 | Parsing | Format/parsing errors |
| 40-49 | Conversion | Disk conversion errors |
| 50-59 | VMware | VMware/vSphere errors |
| 60-69 | Azure | Azure cloud errors |
| 70-79 | Hypervisor | KVM/libvirt errors |
| 80-99 | Guest OS | Guest OS manipulation errors |
| 100+ | System | System/environment errors |

## Resource Requirements

### Minimum
- CPU: 2 cores
- RAM: 4 GB
- Disk: 100 GB free (2x source VM size)

### Recommended
- CPU: 4+ cores
- RAM: 8+ GB
- Disk: 500 GB SSD (3x source VM size)

### Enterprise
- CPU: 8+ cores
- RAM: 16+ GB
- Disk: 1+ TB NVMe SSD

## Performance Tuning

### Parallel Conversions
```bash
# Use xargs for batch processing
find /vmdks -name "*.vmdk" | \
  xargs -P 4 -I {} hyper2kvm local --vmdk {} --to-output /output/
```

### Compression
```bash
# Disable compression for speed
hyper2kvm local --vmdk disk.vmdk --to-output out.qcow2 --no-compress

# Or use zstd for balance
hyper2kvm local --vmdk disk.vmdk --compress-type zstd
```

## Monitoring

### Prometheus Metrics (Future)
```yaml
# metrics.yml
- job_name: 'hyper2kvm'
  static_configs:
    - targets: ['localhost:9090']
```

### Log Aggregation
```bash
# Structured JSON logs
export HYPER2KVM_LOG_FORMAT=json
hyper2kvm ... | jq .
```

## Troubleshooting

### Common Issues

**Issue**: Migration takes too long
**Solution**: Check disk I/O, use faster storage, disable compression

**Issue**: Out of memory
**Solution**: Increase RAM, process smaller VMs first, use swap

**Issue**: Network timeout
**Solution**: Increase timeout, check firewall, verify credentials
```

**Action Items**:
- [ ] Create OPERATIONS.md
- [ ] Document exit codes
- [ ] Add performance tuning guide
- [ ] Create troubleshooting section
- [ ] Add monitoring/observability examples

**Effort**: 4 hours
**Impact**: High (production readiness)

## ⚡ Performance Optimizations

### 11. Async I/O for Batch Operations

**Current**: Sequential VMDK downloads
**Target**: Parallel async downloads

```python
# converters/fetch.py enhancement
import asyncio
from typing import List

async def download_many(
    sources: List[Path],
    destination: Path,
    max_concurrent: int = 4
) -> List[Path]:
    """Download multiple VMDKs concurrently.

    Args:
        sources: List of source VMDK paths
        destination: Destination directory
        max_concurrent: Maximum concurrent downloads

    Returns:
        List of downloaded file paths
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def download_with_limit(src: Path) -> Path:
        async with semaphore:
            return await download_async(src, destination)

    tasks = [download_with_limit(src) for src in sources]
    return await asyncio.gather(*tasks)
```

**Action Items**:
- [ ] Add async support to fetch module
- [ ] Implement producer-consumer pattern
- [ ] Add concurrency limits
- [ ] Benchmark performance improvements

**Effort**: 6 hours
**Impact**: High (performance)

### 12. GuestFS Operation Caching

**Current**: Repeated calls to `g.is_file()`, `g.is_dir()`
**Target**: Cache within transaction scope

```python
# fixers/offline_fixer.py enhancement
import functools
from typing import Any, Callable

def cache_guestfs_calls(func: Callable) -> Callable:
    """Decorator to cache guestfs query results."""
    cache = {}

    @functools.wraps(func)
    def wrapper(g, path: str, *args, **kwargs) -> Any:
        cache_key = f"{func.__name__}:{path}"
        if cache_key not in cache:
            cache[cache_key] = func(g, path, *args, **kwargs)
        return cache[cache_key]

    wrapper.cache_clear = cache.clear
    return wrapper

@cache_guestfs_calls
def is_file_cached(g, path: str) -> bool:
    """Cached version of g.is_file()."""
    return g.is_file(path)
```

**Action Items**:
- [ ] Implement caching decorator
- [ ] Apply to hot paths
- [ ] Add cache invalidation
- [ ] Measure performance gains

**Effort**: 3 hours
**Impact**: Medium (performance)

### 13. Performance Benchmarking

**Create `benchmarks/` Directory**:
```python
# benchmarks/bench_vmdk_parsing.py
import pytest
from pathlib import Path
from hyper2kvm.vmware.utils.vmdk_parser import parse_vmdk

@pytest.mark.benchmark(group="parsing")
def test_vmdk_parsing_small(benchmark):
    """Benchmark VMDK parsing for small files."""
    result = benchmark(parse_vmdk, Path("tests/test-data/test.vmdk"))
    assert result is not None

@pytest.mark.benchmark(group="parsing")
def test_vmdk_parsing_large(benchmark):
    """Benchmark VMDK parsing for large descriptors."""
    result = benchmark(parse_vmdk, Path("tests/test-data/large.vmdk"))
    assert result is not None
```

**Action Items**:
- [ ] Install pytest-benchmark
- [ ] Create benchmarks for critical paths
- [ ] Establish baseline metrics
- [ ] Add to CI for regression detection
- [ ] Publish results to GitHub Pages

**Effort**: 4 hours
**Impact**: Medium (visibility, regression detection)

## 🔒 Security Enhancements

### 14. Credential Management Improvements

**Current**: Environment variables (visible in `ps`)
**Target**: Secure credential storage

```python
# core/cred.py enhancement
import keyring
from pathlib import Path

def get_password_secure(service: str, username: str) -> Optional[str]:
    """Get password from secure storage.

    Priority order:
      1. Keyring (OS credential manager)
      2. Encrypted config file (~/.hyper2kvm/credentials.enc)
      3. Environment variable (fallback, not recommended)
      4. Prompt user
    """
    # Try OS keyring first
    try:
        pwd = keyring.get_password(service, username)
        if pwd:
            return pwd
    except Exception:
        pass

    # Try encrypted config file
    cred_file = Path.home() / ".hyper2kvm" / "credentials.enc"
    if cred_file.exists():
        return load_encrypted_credential(cred_file, service, username)

    # Fall back to environment variable
    env_var = f"{service.upper()}_PASSWORD"
    if env_var in os.environ:
        logger.warning(f"Using insecure env variable {env_var}")
        return os.environ[env_var]

    # Prompt user
    return prompt_password(service, username)
```

**Action Items**:
- [ ] Add keyring support
- [ ] Implement encrypted credential file
- [ ] Add credential rotation
- [ ] Document secure credential practices

**Effort**: 4 hours
**Impact**: Medium (security)

### 15. SSH Security Hardening

**Current**: Basic SSH configuration
**Target**: Hardened SSH with key validation

```python
# ssh/ssh_config.py enhancement
from pathlib import Path

def validate_ssh_config(config: Dict) -> None:
    """Validate SSH configuration for security.

    Raises:
        ConfigurationError: If config is insecure
    """
    # Require StrictHostKeyChecking
    if config.get("StrictHostKeyChecking") not in ["yes", "accept-new"]:
        raise ConfigurationError(
            "SSH StrictHostKeyChecking must be 'yes' or 'accept-new'"
        )

    # Validate key permissions
    key_file = Path(config.get("IdentityFile", ""))
    if key_file.exists():
        mode = key_file.stat().st_mode & 0o777
        if mode != 0o600:
            raise ConfigurationError(
                f"SSH key {key_file} must have permissions 0600, has {oct(mode)}"
            )

    # Require known_hosts file
    if "UserKnownHostsFile" not in config:
        config["UserKnownHostsFile"] = str(Path.home() / ".ssh" / "known_hosts")
```

**Action Items**:
- [ ] Implement SSH config validation
- [ ] Enforce StrictHostKeyChecking
- [ ] Validate key file permissions
- [ ] Add to documentation

**Effort**: 2 hours
**Impact**: Medium (security)

## 📦 Quick Wins (Do Today)

### Priority 0: Immediate Actions

1. **Add ruff pre-commit hook** (10 min)
   ```bash
   # Already done in .pre-commit-config.yaml
   pre-commit run --all-files
   ```

2. **Add coverage badge to README** (5 min)
   ```markdown
   [![codecov](https://codecov.io/gh/ssahani/hyper2kvm/branch/main/graph/badge.svg)](https://codecov.io/gh/ssahani/hyper2kvm)
   ```

3. **Enable GitHub Discussions** (2 min)
   - Settings → Features → Discussions → Enable

4. **Create issue labels** (5 min)
   ```bash
   # Use existing .github/create-labels.sh
   bash .github/create-labels.sh
   ```

5. **Document exit codes in code** (15 min)
   Add to `core/exceptions.py` docstring

## 🗓️ Implementation Timeline

### Week 1-2: Critical Fixes
- [ ] Fix bare except clauses
- [ ] Replace assert statements
- [ ] Audit deleted tests
- [ ] Quick wins

### Week 3-4: Type Safety
- [ ] Add return type hints
- [ ] Create type stubs
- [ ] Run mypy --strict
- [ ] Update pre-commit hooks

### Week 5-6: Error Handling
- [ ] Exception hierarchy
- [ ] Error wrappers
- [ ] Standardize logging
- [ ] Update documentation

### Week 7-10: Testing & Coverage
- [ ] Restore deleted tests
- [ ] Integrate new tests
- [ ] Achieve 95%+ coverage
- [ ] Add benchmarking

### Week 11-12: Documentation
- [ ] Module docstrings
- [ ] MkDocs setup
- [ ] Operations guide
- [ ] API documentation

## 📈 Success Metrics

| Metric | Baseline | Week 4 | Week 8 | Week 12 |
|--------|----------|--------|--------|---------|
| Test Pass Rate | 96.6% | 99% | 99%+ | 99.5%+ |
| Type Coverage | 70% | 80% | 90% | 95% |
| Docstring Coverage | 60% | 70% | 80% | 85% |
| Security Score | B+ | A- | A | A+ |
| Performance | Baseline | +10% | +20% | +30% |

## 🔧 Tools & Automation

### Pre-commit Hooks
```bash
# Install
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

### Type Checking
```bash
# Strict mode
mypy hyper2kvm --strict --ignore-missing-imports

# Generate report
mypy hyper2kvm --html-report mypy-report
```

### Coverage
```bash
# Generate coverage
make test-cov

# View report
open htmlcov/index.html
```

### Benchmarking
```bash
# Install
pip install pytest-benchmark

# Run benchmarks
pytest benchmarks/ --benchmark-only

# Compare
pytest-benchmark compare
```

## 📞 Resources

- **Project Board**: Create GitHub Project for tracking
- **Documentation**: All improvements documented in code
- **Communication**: GitHub Discussions for questions

---

**Next Review**: 2026-02-01
**Owner**: @ssahani
**Status**: 🟢 Active
