# hyper2kvm Examples

Comprehensive examples demonstrating all features of hyper2kvm.

## Quick Start

```bash
# Complete forensic analysis of VM (28 systemd methods)
python3 systemd_forensic_analysis.py /path/to/disk.vmdk

# Pre-migration readiness check
python3 migration_readiness_check.py /path/to/disk.vmdk

# Security audit with HTML report
python3 security_audit.py /path/to/disk.vmdk --format html

# Compare systemd configurations across VMs
python3 systemd_comparison.py vm1.vmdk vm2.vmdk vm3.vmdk

# Performance benchmarking
python3 benchmark_systemd_tools.py vm1.vmdk vm2.vmdk

# Advanced analytics dashboard
python3 analytics_report_generator.py --format html

# View all filesystem APIs (37+ methods)
python3 vmcraft_filesystem_apis.py /path/to/disk.qcow2

# Complete migration workflow
python3 complete_migration_workflow.py /vmware/vm.vmdk /output/kvm
```

## Production Tools

### 1. systemd Forensic Analysis (`systemd_forensic_analysis.py`)

Complete offline forensic analysis using all 28 systemd inspection methods.

**Categories analyzed:**
- Virtualization detection & identity
- Boot performance analysis
- Security compliance & hardening
- Anomaly detection (hidden units, suspicious sockets)
- Crash data (core dumps, pstore)
- Failed services analysis
- Network configuration
- Boot configuration (systemd-boot, UEFI)
- System users & sessions
- Migration readiness assessment
- Advanced configuration (OOM daemon, time sync, extensions)
- Journal analysis

**Usage:**
```bash
python3 systemd_forensic_analysis.py /path/to/disk.vmdk

# Generates:
# - Console output with formatted sections
# - /tmp/forensic_analysis_report.json (detailed JSON report)
# - /tmp/boot-plot.svg (boot timeline visualization)
# - /tmp/journal_export.bin (exported journal logs)
```

**Example output:**
```
Security Compliance Score: 60/100
Migration Ready: YES ✓
Anomalies Found: 0
Core Dumps: 0
Boot Time: 12.34s (kernel: 3.21s, userspace: 9.13s)
```

### 2. Migration Readiness Check (`migration_readiness_check.py`)

Pre-flight validation for VMware to KVM migrations.

**6 comprehensive checks:**
1. Virtualization detection
2. systemd migration readiness
3. Boot configuration compatibility
4. Network configuration portability
5. Security posture assessment
6. Service health validation

**Risk levels:**
- **Minimal**: Ready to migrate immediately
- **Low**: Minor issues, migration should proceed smoothly
- **Medium**: Some issues, recommend fixing before migration
- **High**: Critical blockers, MUST fix before migration

**Usage:**
```bash
python3 migration_readiness_check.py /path/to/vm.vmdk

# Exit codes:
# 0 = Ready with minimal risk
# 1 = Ready but risky (medium/high risk)
# 2 = Not ready (blockers present)

# Generates:
# - Formatted console report with recommendations
# - /tmp/migration_readiness_<vm-name>.json
```

**Example output:**
```
✅ READY FOR MIGRATION
Risk Level: LOW
  Minor issues detected, migration should proceed smoothly.

NEXT STEPS:
1. Perform backup of source VM
2. Test migration in non-production environment
3. Execute migration
4. Run post-migration validation
```

### 3. Security Audit (`security_audit.py`)

Comprehensive security compliance audit with multiple output formats.

**6 audit categories (weighted scoring):**
1. systemd service security (25%)
2. Security compliance checks (25%)
3. Anomaly detection (20%)
4. User & session security (15%)
5. Network security (10%)
6. Boot security (5%)

**Output formats:**
- **JSON**: Machine-readable detailed report
- **HTML**: Visual report with grades and CSS styling
- **Text**: Human-readable console output (default)

**Usage:**
```bash
# Console output (default)
python3 security_audit.py /path/to/vm.vmdk

# HTML report with visual grades
python3 security_audit.py /path/to/vm.vmdk --format html

# JSON for automation/CI
python3 security_audit.py /path/to/vm.vmdk --format json

# Generates:
# - /tmp/security_audit_<vm>_<timestamp>.{html,json,txt}
```

**Example output:**
```
Overall Security Score: 84/100 (Grade: B) 🟡
Risk Level: LOW

Category Scores:
  compliance               60/100
  anomalies               100/100
  user_security            90/100
  network_security        100/100
  boot_security           100/100
```

### 4. systemd Configuration Comparison (`systemd_comparison.py`)

Compare systemd configurations across multiple VMs to identify distribution-specific behaviors.

**Comparison metrics:**
- Virtualization types
- Boot performance
- Security scores
- Anomaly counts
- Failed services
- Network configurations
- Migration readiness
- System extensions

**Usage:**
```bash
python3 systemd_comparison.py vm1.vmdk vm2.vmdk vm3.vmdk

# Generates:
# - Side-by-side comparison table
# - Key differences analysis
# - Per-VM recommendations
# - /tmp/systemd_comparison_report.json
```

**Example output:**
```
Metric                              | Ubuntu          | openSUSE        | Fedora
------------------------------------------------------------------------------
Security Compliance Score           |              75 |              60 |              85
Boot Time (seconds)                 |           12.34 |           15.67 |           10.21
Migration Ready                     |             YES |             YES |             YES
systemd-networkd Files              |               3 |               0 |               5

KEY DIFFERENCES:
🔒 Security Compliance:
   Best:  Fedora (85/100)
   Worst: openSUSE (60/100)
   Gap:   25 points

⚡ Boot Performance:
   Fastest: Fedora (10.21s)
   Slowest: openSUSE (15.67s)
   Diff:    5.46s (53.5% slower)
```

### 5. Performance Benchmark (`benchmark_systemd_tools.py`)

Benchmark all production tools for performance testing and optimization.

**Features**:
- Benchmarks all 4 production tools
- Measures execution time, memory usage, throughput
- Multi-VM testing support
- Performance statistics and insights
- Identifies fastest/slowest tools

**Usage**:
```bash
python3 benchmark_systemd_tools.py vm1.vmdk vm2.vmdk vm3.vmdk

# Generates:
# - /tmp/systemd_tools_benchmark.json
```

**Example output**:
```
Tool Performance Statistics:
Tool                                Avg Time     Min/Max         Avg Mem
--------------------------------------------------------------------------------
systemd_forensic_analysis             5.22s       5.22/5.22 s       0.0 MB
migration_readiness_check             4.53s       4.53/4.53 s       0.0 MB
security_audit                        4.31s       4.31/4.31 s      15.2 MB
filesystem_api_demo                   7.89s       7.89/7.89 s       0.0 MB

Performance Insights:
  ⚡ Fastest tool:  security_audit (4.31s avg)
  🐌 Slowest tool:  filesystem_api_demo (7.89s avg)
  💾 Most memory:   security_audit (15.2 MB avg)
  🚀 Best throughput: security_audit (0.210 GB/s)
```

### 6. Advanced Analytics (`analytics_report_generator.py`)

Generate comprehensive analytics dashboards from aggregated tool outputs.

**Features**:
- Aggregates results from multiple tool runs
- Security compliance tracking over time
- Migration readiness dashboard
- Forensic issue aggregation
- Performance trend analysis
- Multiple output formats (HTML, JSON, Markdown)
- Executive summary with actionable recommendations

**Usage**:
```bash
# Run tools first
python3 systemd_forensic_analysis.py vm*.vmdk
python3 migration_readiness_check.py vm*.vmdk
python3 security_audit.py vm*.vmdk --format json

# Generate analytics
python3 analytics_report_generator.py --format html

# Generates:
# - /tmp/analytics_report.html (visual dashboard)
# - or /tmp/analytics_report.json (machine-readable)
# - or /tmp/analytics_report.md (markdown)
```

**Example output**:
```
## Executive Summary

| Metric | Value |
|--------|-------|
| VMs Audited (Security) | 15 |
| VMs Assessed (Migration) | 15 |
| VMs Analyzed (Forensics) | 12 |

## Security Compliance Dashboard

**Overall Statistics:**
- Average Security Score: **75.2/100**
- Score Range: 45-95
- Grade Distribution: {'A': 3, 'B': 7, 'C': 4, 'F': 1}

## Migration Readiness Dashboard

**Status Overview:**
- ✅ Ready for Migration: **12**
- ❌ Not Ready: **3**
- Risk Distribution: {'minimal': 5, 'low': 7, 'medium': 2, 'high': 1}

## Recommendations

### Security Improvements
**3 VMs** have security scores below 70
**Action**: Run security audit with `--format html` for detailed findings.

### Migration Readiness
**3 VMs** are not ready for migration
**Action**: Review blockers and fix before attempting migration.
```

## API Reference Examples

### 7. systemd API Reference (`systemd_api_reference.py`)

Complete reference for all 46 systemd APIs with code examples.

### 8. Interactive systemd Demo (`demo_systemd_apis.py`)

Interactive demonstration of systemd APIs with real VM analysis.

### 9. Filesystem APIs (`vmcraft_filesystem_apis.py`)

All 37+ filesystem detection and manipulation APIs.

## Migration Workflow Examples

### 10. Complete Migration Workflow (`complete_migration_workflow.py`)

End-to-end VMware to KVM migration with pre/post validation.

### 11. Multi-VM Comparison (`compare_vms.py`)

Compare multiple VMs for migration planning.

### 12. Migration Benchmark (`benchmark_migration.py`)

Performance benchmarking for migration operations.

## Usage Tips

**For production migrations:**
```bash
# 1. Pre-flight check
python3 migration_readiness_check.py vm.vmdk
# Exit code 0 = proceed, 1 = review warnings, 2 = fix blockers

# 2. Security audit
python3 security_audit.py vm.vmdk --format html
# Review HTML report before migration

# 3. Execute migration
python3 complete_migration_workflow.py vm.vmdk /output/kvm

# 4. Post-migration validation
python3 systemd_forensic_analysis.py /output/kvm/vm.qcow2
```

**For forensic investigation:**
```bash
# Full analysis
python3 systemd_forensic_analysis.py crashed-vm.vmdk

# Check for anomalies
python3 security_audit.py crashed-vm.vmdk

# Review journal logs
# Check /tmp/journal_export.bin
```

**For fleet management:**
```bash
# Compare all VMs
python3 systemd_comparison.py vm*.vmdk

# Audit all VMs
for vm in vm*.vmdk; do
    python3 security_audit.py "$vm" --format json
done

# Aggregate results
jq -s 'map({name: .vm_name, score: .overall_score})' /tmp/security_audit_*.json
```

## See Also

Individual script help:
```bash
python3 <script>.py --help
```
