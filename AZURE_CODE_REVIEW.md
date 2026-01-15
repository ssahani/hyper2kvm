# Azure Module Code Review

**Review Date**: 2026-01-15
**Reviewer**: Claude Code
**Scope**: Azure VM migration integration (hyper2kvm/azure/)

---

## Executive Summary

**Overall Assessment**: ✅ **GOOD** with minor issues to address

The Azure integration is well-structured and follows the existing project patterns. However, there are several bugs and inconsistencies that should be fixed before production use.

**Critical Issues**: 2
**High Priority**: 4
**Medium Priority**: 6
**Low Priority**: 3

---

## Critical Issues

### 1. ❌ Import Name Mismatch in azure_exporter.py

**File**: `hyper2kvm/orchestrator/azure_exporter.py:24-28`

```python
from ..azure.models import (
    SelectConfig,           # ❌ WRONG
    ShutdownConfig,         # ❌ WRONG
    ExportConfig,           # ❌ WRONG
    DownloadConfig,         # ❌ WRONG
)
```

**Issue**: The config classes are named `Azure*Config` in models.py:
- `AzureSelectConfig` (not `SelectConfig`)
- `AzureShutdownConfig` (not `ShutdownConfig`)
- `AzureExportConfig` (not `ExportConfig`)
- `AzureDownloadConfig` (not `DownloadConfig`)

**Impact**: This will cause `ImportError` at runtime when Azure mode is used.

**Fix**:
```python
from ..azure.models import (
    AzureSelectConfig,
    AzureShutdownConfig,
    AzureExportConfig,
    AzureDownloadConfig,
)
```

And update all references:
```python
select = AzureSelectConfig(...)
shutdown = AzureShutdownConfig(...)
export = AzureExportConfig(...)
download = AzureDownloadConfig(...)
```

---

### 2. ❌ Inconsistent Consistency String Values

**Files**:
- `hyper2kvm/azure/models.py:136` - Default is `"crash"`
- `hyper2kvm/orchestrator/azure_exporter.py:106` - Uses `"crash_consistent"`
- `hyper2kvm/azure/source.py:293` - Checks for `"best_effort_quiesce"`
- `test-confs/60-azure-basic.yaml:38` - Documents as `"crash_consistent"`

**Issue**: Inconsistent string values for consistency mode:
- models.py default: `"crash"`
- source.py checks: `"best_effort_quiesce"`
- CLI/YAML examples: `"crash_consistent"`, `"best_effort_quiesce"`

**Impact**: Configuration will not work as expected. The check on line 293 will never match if using default.

**Fix**: Standardize on `"crash_consistent"` and `"best_effort_quiesce"`:
```python
# models.py:136
consistency: str = "crash_consistent"  # crash_consistent|best_effort_quiesce
```

---

## High Priority Issues

### 3. ⚠️ Empty String Defaults May Cause Azure CLI Errors

**File**: `hyper2kvm/orchestrator/azure_exporter.py:88, 129-130`

```python
resource_group=getattr(self.args, "azure_resource_group", None) or "",
# ...
subscription=getattr(self.args, "azure_subscription", None) or "",
tenant=getattr(self.args, "azure_tenant", None) or "",
```

**Issue**: Converting `None` to empty string `""` may not be the right default. Azure CLI might prefer `None` to skip the parameter entirely.

**Impact**: Potential unexpected behavior when trying to use default subscription.

**Recommendation**: Keep as `None` instead of empty string, or handle in the CLI wrapper:
```python
resource_group=getattr(self.args, "azure_resource_group", None),
subscription=getattr(self.args, "azure_subscription", None),
tenant=getattr(self.args, "azure_tenant", None),
```

---

### 4. ⚠️ Race Condition in Progress Update (source.py:415-420)

**File**: `hyper2kvm/azure/source.py:415-420`

```python
try:
    if item.expected_bytes is not None:
        prog.update(task, completed=item.bytes_downloaded or 0, total=item.expected_bytes)
    prog.update(task, description=f"{vm.name}: {local_vhd.name} ({'ok' if item.ok else 'failed'})")
except Exception:
    pass
```

**Issue**: The `finally` block updates progress from worker threads, which might race with Rich's internal state if multiple threads complete simultaneously.

**Impact**: Potential progress bar corruption or crashes.

**Recommendation**: While Rich Progress is thread-safe, the broad `except Exception: pass` masks real errors. At minimum, log the exception:
```python
except Exception as e:
    logger.debug(f"Failed to update progress for {vm.name}: {e}")
```

---

### 5. ⚠️ No Validation of VM Selection Results

**File**: `hyper2kvm/azure/source.py:216-217`

```python
if not selected:
    raise AzureCLIError("No VMs matched selection criteria.")
```

**Issue**: Good error, but happens after potentially expensive operations (listing all VMs, querying power states). Should validate earlier if possible.

**Also**: No check if `list_only=True` but `resource_group` is missing and `allow_all_rgs=False`.

**Recommendation**: Move validation earlier or add more specific error messages.

---

### 6. ⚠️ Default stage_disk_from_snapshot=True May Be Too Conservative

**File**: `hyper2kvm/azure/models.py:130`

```python
stage_disk_from_snapshot: bool = True
```

**Issue**: Default is `True`, which creates a temporary disk from every snapshot. This is safer but:
- Much slower (creates disk, waits for provisioning, grants access, deletes disk)
- More expensive (temporary disk charges)
- Usually unnecessary for most use cases

**Impact**: Poor default user experience (slow, expensive).

**Recommendation**: Change default to `False`:
```python
stage_disk_from_snapshot: bool = False
```

Document when staging is needed (very large VMs, network issues, etc.) in YAML examples.

---

## Medium Priority Issues

### 7. 🔶 Missing Input Validation for Chunk Size

**File**: `hyper2kvm/azure/source.py:346`

```python
chunk = max(1, int(cfg.download.chunk_mb)) * 1024 * 1024
```

**Issue**: No upper bound validation. User could specify `--azure-chunk-mb 999999` and cause memory issues.

**Recommendation**: Add reasonable bounds:
```python
chunk_mb = max(1, min(cfg.download.chunk_mb, 128))  # 1-128 MB
chunk = chunk_mb * 1024 * 1024
```

---

### 8. 🔶 Inconsistent Error Handling Between Snapshot and Disk Export

**File**: `hyper2kvm/azure/source.py:332-334`

```python
else:
    export_id = d.id
    export_target_kind = "disk"
```

**Issue**: When exporting directly from disk (no snapshots), there's no error handling if the VM is running and the disk is in use.

**Recommendation**: Add validation:
```python
else:
    if vm.power_state == "running" and not cfg.shutdown.mode != "none":
        raise AzureCLIError(
            f"Cannot export running VM {vm.name} without snapshots. "
            f"Enable snapshots or configure shutdown."
        )
    export_id = d.id
    export_target_kind = "disk"
```

---

### 9. 🔶 SAS Token Truncation in Reporting May Not Be Secure Enough

**File**: `hyper2kvm/azure/models.py:103-104`

```python
def sas_hash10(self, sas_url: str) -> str:
    return hashlib.sha256(sas_url.encode("utf-8")).hexdigest()[:10]
```

**Issue**: Only 10 hex chars (40 bits) of SHA256 hash. This is probably fine for audit logs, but the name `sas_hash10` doesn't clearly indicate it's truncated.

**Recommendation**: Rename to make truncation explicit:
```python
def sas_hash10_preview(self, sas_url: str) -> str:
    """Return first 10 chars of SHA256 hash for audit preview (not cryptographically secure)."""
    return hashlib.sha256(sas_url.encode("utf-8")).hexdigest()[:10]
```

---

### 10. 🔶 Missing Validation for Parallel Download Count

**File**: `hyper2kvm/azure/source.py:263`

```python
max_workers = min(max(1, int(cfg.download.parallel)), 16)
```

**Issue**: Hard-coded max of 16. Good, but doesn't account for the number of actual disks to download.

**Recommendation**: Also limit by actual work:
```python
max_workers = min(max(1, int(cfg.download.parallel)), 16, len(jobs))
```

---

### 11. 🔶 No Cleanup on Early Exit from list_only Mode

**File**: `hyper2kvm/azure/source.py:245-246`

```python
if cfg.select.list_only:
    return rep, []
```

**Issue**: If VMs were shut down before discovering `list_only=True`, they won't be restarted.

**Impact**: Probably not a real issue since shutdown happens after the list_only check, but the code flow is confusing.

**Recommendation**: Check `list_only` earlier before any destructive operations.

---

### 12. 🔶 Potential Disk Space Issues Not Checked

**Issue**: No check for available disk space before downloading potentially hundreds of GB of VHD files.

**Recommendation**: Add disk space check before starting downloads:
```python
import shutil
total_size = sum(d.size_gb * 1024**3 for vm in selected for d in vm.disks)
free_space = shutil.disk_usage(cfg.output_dir).free
if total_size > free_space * 0.9:  # Leave 10% margin
    logger.warning(f"Low disk space: need ~{total_size//1024**3}GB, have {free_space//1024**3}GB")
```

---

## Low Priority / Style Issues

### 13. 💡 Inconsistent Naming: SelectConfig vs AzureSelectConfig

**Issue**: The classes are named `Azure*Config` but sometimes referenced without the `Azure` prefix in variable names.

**Recommendation**: Use full names consistently for clarity.

---

### 14. 💡 Missing Type Hints in _export_one Return

**File**: `hyper2kvm/azure/source.py:265`

```python
def _export_one(vm: AzureVMRef, d: AzureDiskRef) -> Tuple[AzureExportItem, Optional[DiskArtifact], List[str], List[str]]:
```

**Recommendation**: Add docstring explaining the 4-tuple return:
```python
def _export_one(vm: AzureVMRef, d: AzureDiskRef) -> Tuple[AzureExportItem, Optional[DiskArtifact], List[str], List[str]]:
    """
    Export a single disk.

    Returns:
        (export_item, disk_artifact, created_resource_ids, deleted_resource_ids)
    """
```

---

### 15. 💡 Hardcoded String "hyper2kvm" in Tag Generation

**File**: `hyper2kvm/azure/cleanup.py:26-29`

```python
return {
    "hyper2kvm": "true",
    "hyper2kvm-run": run_tag,
    "hyper2kvm-vm": vm_name,
    "hyper2kvm-managed": "true",
}
```

**Recommendation**: Could use package name constant, but this is fine for now.

---

## Security Considerations

### ✅ Good: SAS Token Not Logged

The code properly avoids logging full SAS URLs (which contain secrets). Only hashed previews are stored in reports.

### ✅ Good: Azure CLI Authentication

Uses Azure CLI for authentication, which is the recommended approach. No credentials stored in code.

### ✅ Good: Resource Cleanup

Proper cleanup of SAS tokens (revoke) and temporary resources (delete).

### ⚠️ Moderate: Error Messages May Leak Info

Some error messages include Azure resource IDs and names. This is generally fine but be aware in multi-tenant environments.

---

## Performance Considerations

### ✅ Good: Parallel Downloads

Thread-based parallel downloads with configurable concurrency.

### ✅ Good: Resume Support

HTTP Range requests for resuming interrupted downloads.

### ✅ Good: Chunked Downloads

Streaming downloads with configurable chunk size to manage memory.

### 🔶 Concern: Snapshot Creation is Serial

**File**: `hyper2kvm/azure/source.py:302-308`

Snapshots are created serially within `_export_one`, but `_export_one` itself runs in parallel. This is actually fine - snapshots are created in parallel across VMs/disks.

### 🔶 Concern: No Rate Limiting

No explicit rate limiting for Azure API calls. Relies on Azure CLI's built-in retry logic, which should be sufficient.

---

## Testing Gaps

### Missing Tests

1. **Unit tests**: No unit tests for any Azure module
2. **Integration tests**: No integration tests with mock Azure CLI
3. **Error path tests**: No tests for failure scenarios

### Recommended Test Coverage

```python
# tests/azure/test_models.py
- Test AzureConfig serialization/deserialization
- Test consistency value validation

# tests/azure/test_cli.py
- Test retry logic with mocked transient failures
- Test backoff timing
- Test timeout handling

# tests/azure/test_download.py
- Test resume from partial download
- Test size verification (strict and non-strict)
- Test retry logic

# tests/azure/test_source.py
- Test VM selection filtering
- Test snapshot workflow
- Test direct disk export workflow
- Test cleanup on success and failure
```

---

## Documentation Quality

### ✅ Good:
- Clear module docstrings
- YAML examples with comments
- Function-level documentation

### 🔶 Could Improve:
- Add architecture diagram showing workflow
- Add troubleshooting section for common errors
- Document Azure permissions required
- Add examples for different Azure subscription types

---

## Integration Quality

### ✅ Excellent:
- Follows existing Source Provider pattern
- Integrates cleanly with orchestrator
- CLI argument structure matches vSphere pattern
- Proper error types (inherits from AzureError)

### ✅ Good:
- Returns DiskArtifact objects for pipeline
- Generates JSON reports like vSphere
- Supports same post-processing options

---

## Recommended Fixes Priority

### Must Fix Before Production:
1. ❌ Fix import names in azure_exporter.py (Critical)
2. ❌ Fix consistency string value inconsistency (Critical)
3. ⚠️ Change stage_disk_from_snapshot default to False
4. ⚠️ Add VM running validation for non-snapshot exports

### Should Fix Soon:
5. 🔶 Add chunk size bounds validation
6. 🔶 Add disk space check before download
7. 🔶 Improve error handling in progress updates
8. 🔶 Handle empty string vs None for Azure parameters

### Nice to Have:
9. 💡 Add comprehensive unit tests
10. 💡 Add architecture documentation
11. 💡 Add function docstrings with return value explanations

---

## Code Quality Metrics

| Metric | Score | Notes |
|--------|-------|-------|
| **Correctness** | 7/10 | Has critical import bug, consistency bug |
| **Safety** | 8/10 | Good error handling, but some gaps |
| **Security** | 9/10 | Proper credential handling, no secrets in logs |
| **Performance** | 8/10 | Good parallelism, resume support |
| **Maintainability** | 8/10 | Clean structure, follows patterns |
| **Documentation** | 7/10 | Good examples, missing architecture docs |
| **Testing** | 2/10 | No automated tests |
| **Overall** | 7/10 | **Good foundation, needs bug fixes** |

---

## Conclusion

The Azure integration is well-architected and follows good patterns from the existing vSphere integration. The code structure is clean and maintainable. However, there are **2 critical bugs** that will cause runtime failures:

1. **Import name mismatch** - Will cause ImportError
2. **Consistency value mismatch** - Will cause config to not work

These must be fixed before the code can work in production.

After fixing these bugs and addressing the high-priority issues, the Azure module will be production-ready. The foundation is solid and the integration is clean.

**Recommendation**: Fix critical bugs immediately, then add basic integration tests before considering this production-ready.
