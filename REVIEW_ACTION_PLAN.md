# Code Review Action Plan

**Created**: 2026-01-15
**Priority**: Immediate to Long-term

Based on comprehensive code review, this action plan prioritizes fixes and improvements.

---

## 🔴 CRITICAL - Fix Immediately (This Week)

### 1. Password File Race Condition (CWE-377)
**Files**:
- `hyper2kvm/vmware/utils/v2v.py:87-101`
- `hyper2kvm/vmware/clients/extensions.py:197`

**Issue**: Password file created with default umask, then chmod'd (race condition)

**Fix**:
```python
# Replace pwfile.write_text() + os.chmod() with:
fd = os.open(str(pwfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
try:
    os.write(fd, (pw + "\n").encode('utf-8'))
finally:
    os.close(fd)
```

**Estimate**: 30 minutes
**Assignee**: Security team / Senior dev
**Verification**: Manual test + code review

---

## 🟠 HIGH - Before Production (This Month)

### 2. Archive Permission Extraction
**File**: `hyper2kvm/converters/extractors/ami.py:997`

**Issue**: Extracts tar archives with original permissions (could be world-writable)

**Fix**:
```python
# Replace:
os.chmod(target_path, member.mode or 0o644)

# With:
safe_mode = (member.mode or 0o644) & 0o755
os.chmod(target_path, safe_mode)
```

**Estimate**: 15 minutes
**Priority**: HIGH
**Verification**: Unit test with various tar permission modes

---

### 3. Add Azure Module Tests
**Coverage Target**: 60% minimum

**Required Tests**:
- Unit tests for `AzureSourceProvider.fetch()`
- Unit tests for `download_with_resume()`
- Unit tests for Azure CLI wrapper with retry logic
- Integration test for full VM export workflow (mocked)

**Files to Create**:
- `tests/unit/test_azure_source.py`
- `tests/unit/test_azure_download.py`
- `tests/unit/test_azure_cli.py`
- `tests/integration/test_azure_workflow.py`

**Estimate**: 8-16 hours
**Priority**: HIGH
**Verification**: pytest coverage report

---

### 4. Create SECURITY.md
**Content Required**:
- Password handling best practices
- Root/sudo requirements
- Environment variable security
- Multi-user system considerations
- Deployment security checklist
- Credential management guidelines

**Estimate**: 2-4 hours
**Priority**: HIGH
**Verification**: Security team review

---

### 5. Optimize Azure CLI Batching
**File**: `hyper2kvm/azure/source.py:209-214`

**Current**: 2 separate `az` calls per VM (power state + show)
**Target**: Batch or use Azure Python SDK

**Options**:
A. Use `az vm list --show-details` to get power state in one call
B. Switch to Azure Python SDK (`azure-mgmt-compute`)

**Estimate**: 4-8 hours
**Priority**: HIGH
**Verification**: Performance benchmark (measure time for 100 VMs)

---

## 🟡 MEDIUM - Improvements (This Quarter)

### 6. Add HTTP Connection Pooling
**File**: `hyper2kvm/azure/download.py`

**Fix**:
```python
# Create session for connection reuse
import requests
session = requests.Session()

# Use session.get() instead of requests.get()
resp = session.get(url, headers=headers, stream=True, ...)
```

**Estimate**: 1 hour
**Priority**: MEDIUM
**Verification**: Benchmark download speed for 10 small disks

---

### 7. Standardize Error Raising
**Pattern**: Replace all `U.die(logger, msg, code)` with `raise Fatal(code, msg)`

**Files to Update**: ~30 occurrences across codebase

**Estimate**: 2-4 hours
**Priority**: MEDIUM
**Verification**: grep for "U.die" returns 0 results

---

### 8. Add Type Hints
**Target**: 70% coverage

**Priority Files**:
- `hyper2kvm/orchestrator/*.py` (all files)
- `hyper2kvm/azure/*.py` (all files)
- `hyper2kvm/core/*.py` (key utilities)

**Estimate**: 16-24 hours
**Priority**: MEDIUM
**Verification**: mypy passes with --strict flag

---

### 9. Refactor Large Classes

#### A. OfflineFSFix (1,305 LOC)
**Split into**:
- `offline_fixer.py` - Main orchestrator (300 LOC)
- `mount_manager.py` - Mount/unmount operations (200 LOC)
- `luks_handler.py` - LUKS operations (150 LOC)
- `filesystem_inspector.py` - Detection logic (200 LOC)

**Estimate**: 8-12 hours

#### B. Mode.py (1,450 LOC)
**Split into**:
- `mode.py` - Main orchestrator (300 LOC)
- `command_handlers.py` - Individual commands (600 LOC)
- `vm_operations.py` - VM management (300 LOC)

**Estimate**: 8-12 hours

**Priority**: MEDIUM
**Verification**: All tests pass, no functionality change

---

### 10. Remove Commented Code
**Pattern**: Delete all commented-out code blocks

**Estimate**: 1-2 hours
**Priority**: MEDIUM
**Verification**: grep for "# OLD_BEHAVIOR" and similar patterns

---

### 11. Convert TODO Comments to Issues
**Process**:
1. Find all TODO comments (grep -r "# TODO")
2. Create GitHub issue for each
3. Link issue number in code or remove TODO

**Estimate**: 2 hours
**Priority**: MEDIUM
**Verification**: grep for "# TODO" returns 0 results

---

## 🟢 LOW - Nice to Have (This Year)

### 12. Add Architecture Diagrams
**Required Diagrams**:
- High-level component diagram
- Data flow diagram (input → output)
- Sequence diagram for offline fixing workflow
- Deployment architecture options

**Tools**: PlantUML, Mermaid, or draw.io

**Estimate**: 4-6 hours
**Priority**: LOW
**Deliverable**: diagrams/ folder in docs/

---

### 13. Generate API Documentation
**Tool**: Sphinx or mkdocs

**Setup**:
1. Install sphinx/mkdocs
2. Configure autodoc
3. Generate documentation site
4. Host on GitHub Pages

**Estimate**: 4-8 hours
**Priority**: LOW
**Verification**: Browse generated docs

---

### 14. Add Performance Regression Tests
**Benchmarks**:
- OVA extraction time (500MB file)
- Offline fixing time (10GB disk)
- Parallel processing speedup (4 disks)
- Azure VHD download speed

**Track**: Store results in git, compare on each commit

**Estimate**: 8-12 hours
**Priority**: LOW
**Verification**: CI runs benchmarks automatically

---

### 15. Memory-Based Worker Limit
**Feature**: Auto-limit workers based on available RAM

**Logic**:
```python
import psutil
available_ram_gb = psutil.virtual_memory().available / (1024**3)
max_workers_by_ram = int(available_ram_gb / 2)  # 2GB per worker
max_workers = min(configured_workers, max_workers_by_ram)
```

**Estimate**: 2-3 hours
**Priority**: LOW
**Verification**: Test on 4GB RAM system

---

## Timeline Summary

### Week 1 (Critical)
- [ ] Fix password file race condition
- [ ] Fix archive permission extraction
- [ ] Create SECURITY.md

### Month 1 (High Priority)
- [ ] Add Azure module tests (60% coverage)
- [ ] Optimize Azure CLI batching
- [ ] Add HTTP connection pooling
- [ ] Create TROUBLESHOOTING.md

### Quarter 1 (Medium Priority)
- [ ] Standardize error raising
- [ ] Add type hints (70% coverage)
- [ ] Refactor OfflineFSFix
- [ ] Refactor Mode.py
- [ ] Remove commented code
- [ ] Convert TODOs to issues

### Year 1 (Low Priority)
- [ ] Add architecture diagrams
- [ ] Generate API documentation
- [ ] Performance regression tests
- [ ] Memory-based worker limits
- [ ] Expand test coverage to 80%+

---

## Success Metrics

### After Week 1
- ✅ 0 critical security issues
- ✅ Security documentation available

### After Month 1
- ✅ Azure module: 60%+ test coverage
- ✅ 0 high-priority security issues
- ✅ Performance improved 2x for Azure (batching)

### After Quarter 1
- ✅ Overall test coverage: 50%+
- ✅ Type hints: 70%+
- ✅ No files > 800 LOC
- ✅ 0 commented code blocks

### After Year 1
- ✅ Overall test coverage: 80%+
- ✅ Type hints: 100% in core modules
- ✅ Complete documentation (API, architecture, guides)
- ✅ Performance benchmarks in CI

---

## Resource Requirements

| Phase | Developer Time | Review Time | Testing Time | Total |
|-------|---------------|-------------|--------------|-------|
| Week 1 (Critical) | 4 hours | 2 hours | 2 hours | 8 hours |
| Month 1 (High) | 24-36 hours | 8 hours | 8 hours | 40-52 hours |
| Quarter 1 (Medium) | 40-60 hours | 16 hours | 16 hours | 72-92 hours |
| Year 1 (Low) | 24-36 hours | 8 hours | 8 hours | 40-52 hours |
| **Total** | **92-136 hours** | **34 hours** | **34 hours** | **160-204 hours** |

**Equivalent**: ~4-5 weeks of full-time development

---

## Risk Mitigation

### If Critical Fixes Delayed
**Impact**: Production deployment blocked
**Mitigation**: Assign to senior developer immediately

### If Test Coverage Not Improved
**Impact**: Bugs in production, regression issues
**Mitigation**: Block new features until coverage > 60%

### If Performance Issues Persist
**Impact**: Slow migrations, user complaints
**Mitigation**: Profile and optimize hot paths first

### If Documentation Gaps Remain
**Impact**: Support burden, user errors
**Mitigation**: Community contributions, wiki pages

---

## Sign-off

**Security Team**: [ ] Approved after critical fixes
**Engineering Lead**: [ ] Approved after high-priority fixes
**QA Team**: [ ] Approved after test coverage improvements
**Product Owner**: [ ] Approved for production deployment

---

*This action plan should be reviewed and updated quarterly based on project priorities and resource availability.*
