## [2.0.0] - 2026-02-03

### 🎉 Major Release: Live Migration Support

Transforms hyper2kvm into a full-featured VM migration platform with both cold and live migration.

### Added

#### MigrationPolicy CRD
- Cluster-scoped CRD for migration behavior control
- Bandwidth limits, auto-convergence, post-copy support
- Parallelism controls (cluster-wide and per-node)
- VM label selectors for policy targeting

#### Live Migration Controllers (8 new modules)
- `live_migration_controller.py` - VMIM tracking and progress monitoring
- `vm_lifecycle_controller.py` - Automatic migrations on node eviction  
- `migration_policy_controller.py` - Policy validation and enforcement
- `storage_migration_controller.py` - Volume updates and hot-plug
- `migration_control.py` - Migration abort/cancel and status
- `bandwidth_manager.py` - Bandwidth allocation and fair sharing
- `migration_orchestrator.py` - High-level workflow coordination
- `vm_factory.py` - Centralized VM creation with advanced features

#### MigrationJob CRD Extensions
- `evictionStrategy` - LiveMigrate, None, LiveMigrateIfPossible, External
- `migrationPolicyRef` - Reference to MigrationPolicy
- `firmware` - BIOS, UEFI, UEFI Secure Boot support
- `cpuConfig` - CPU topology (cores, sockets, threads) and features
- `resources` - CPU/memory requests and limits
- `disks` - Multi-disk VM support with boot order
- `interfaces` - Multiple network interfaces with MAC control
- `liveMigration` status - Progress tracking (bandwidth, dirty rate)

#### Metrics (11 new)
- `hyper2kvm_live_migrations_*` - Total, succeeded, failed migrations
- `hyper2kvm_live_migration_duration_seconds` - Duration histogram
- `hyper2kvm_live_migration_data_transferred_bytes` - Data histogram
- `hyper2kvm_live_migration_downtime_ms` - Downtime histogram
- `hyper2kvm_migration_policy_violations_total` - Policy violations
- `hyper2kvm_*_activations_total` - Post-copy, auto-converge
- `hyper2kvm_live_migrations_active` - Active by phase
- `hyper2kvm_migration_bandwidth_bytes_per_second` - Current bandwidth
- `hyper2kvm_migration_dirty_rate_bytes_per_second` - Memory dirty rate

#### Validation
- Eviction strategy validation
- CPU topology validation (cores × sockets × threads)
- Firmware validation (secure boot requires UEFI)
- Multi-disk validation (duplicates, boot orders)
- Network interface validation (MAC addresses)

#### Documentation
- `docs/LIVE_MIGRATION.md` - Complete feature guide (600+ lines)
- `docs/UPGRADE_GUIDE.md` - Migration from v1.x (450+ lines)
- `docs/QUICK_REFERENCE.md` - Quick reference card (330+ lines)

#### Examples
- `migrationpolicy-default.yaml` - Default cluster policy
- `migrationpolicy-high-priority.yaml` - Priority-based policy
- `migrationjob-with-eviction.yaml` - VM with eviction strategy
- `migrationjob-uefi.yaml` - UEFI firmware example
- Updated `migrationjob-multi-disk.yaml` - Multi-disk with topology

#### Tests
- `tests/e2e/test_live_migration.py` - Comprehensive E2E suite (450+ lines)
- 10 test classes covering all new features

### Changed
- Refactored VM creation in `migrationjob_controller.py` to use `VMFactory`
- Updated operator version to 2.0.0
- Enhanced RBAC with KubeVirt resource permissions

### Backward Compatibility
✅ **100% Backward Compatible**
- Existing MigrationJob resources work unchanged
- All new fields optional with sensible defaults  
- `evictionStrategy` defaults to `LiveMigrate`
- No API version changes (still v1alpha1)

### Statistics
- **New Files**: 16 (10 Python modules, 4 examples, 1 CRD, 1 test)
- **Modified Files**: 6 (CRD, controllers, metrics, validation, RBAC)
- **Lines Added**: ~4,000+ production code + 2,400+ documentation
- **Commits**: 11 (all dated 2026-02-03)

### Migration Notes
See `docs/UPGRADE_GUIDE.md` for detailed instructions.

Quick upgrade:
```bash
kubectl apply -f k8s/operator/crds/migrationpolicy.yaml
kubectl apply -f k8s/operator/migrationjob-crd.yaml
kubectl apply -f k8s/operator/deployment.yaml
```

### Contributors
- Claude Sonnet 4.5 <noreply@anthropic.com>

---

