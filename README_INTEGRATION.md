# HyperSDK Integration - File Location Guide

## Integration Files

### Go Code (HyperSDK Repository)

**Location:** `/home/ssahani/go/github/hypersdk/`

#### TUI Commands
- `cmd/hyperctl/workflow.go` (391 lines) - Workflow management commands
- `cmd/hyperctl/manifest.go` (509 lines) - Manifest builder and operations

#### API Handlers
- `daemon/api/workflow_handlers.go` (399 lines) - REST API endpoints
- `daemon/api/server.go` (updated) - Route registration
- `daemon/api/enhanced_server.go` (updated) - Enhanced server routes

#### Web Dashboard
- `web/dashboard-react/src/components/WorkflowDashboard.tsx` (376 lines)
- `web/dashboard-react/src/components/ManifestBuilder.tsx` (528 lines)
- `web/dashboard-react/src/types/metrics.ts` (updated)

### Documentation (hyper2kvm Repository)

**Location:** `/home/ssahani/tt/hyper2kvm/`

1. **HYPERSDK_INTEGRATION.md** (44 KB, 1,557 lines)
   - Complete integration guide
   - Code examples for TUI, API, and Web
   - Architecture diagrams
   - Configuration examples

2. **WORKFLOW_INTEGRATION_COMPLETE.md** (11 KB, 288 lines)
   - Implementation completion summary
   - File listing with line counts
   - Build status

3. **INTEGRATION_TEST_REPORT.md** (13 KB, 450 lines)
   - Detailed test results
   - Test methodology
   - Performance metrics

4. **HYPERSDK_INTEGRATION_SUCCESS.md** (16 KB, 400 lines)
   - Success summary
   - Feature overview
   - Statistics

5. **QUICKSTART.md** (7.6 KB, 200 lines)
   - 5-minute setup guide
   - Quick commands reference
   - Troubleshooting

6. **PHOTON_TEST_RESULTS.md** (350 lines)
   - Real VM test results
   - Pipeline execution details
   - Performance analysis

### Test Scripts

**Location:** `/home/ssahani/tt/hyper2kvm/`

1. **test_hypersdk_integration.sh**
   - Comprehensive integration tests
   - Validates all components
   - Compilation tests

2. **demo_hypersdk_integration.sh**
   - Interactive demo
   - Shows all features
   - Example usage

3. **test_photon_workflow.sh**
   - Real VM workflow test
   - Complete end-to-end test
   - Progress monitoring

4. **test_photon_sudo.sh**
   - Quick test with sudo
   - Real processing demo

## Quick Access Commands

### Build HyperCTL
```bash
cd /home/ssahani/go/github/hypersdk/cmd/hyperctl
go build -o hyperctl .
```

### Run Tests
```bash
cd /home/ssahani/tt/hyper2kvm
./test_hypersdk_integration.sh    # Integration tests
./demo_hypersdk_integration.sh    # Demo
./test_photon_workflow.sh          # Real VM test
```

### Use HyperCTL
```bash
HYPERCTL=/home/ssahani/go/github/hypersdk/cmd/hyperctl/hyperctl

$HYPERCTL workflow -op status     # Check status
$HYPERCTL workflow -op queue      # Queue stats
$HYPERCTL manifest create         # Create manifest
```

### Start Daemon
```bash
# Workflow daemon
sudo hyper2kvm --config /path/to/daemon.yaml

# HyperSDK daemon (for API/Web)
cd /home/ssahani/go/github/hypersdk
go run ./cmd/daemon --config config.yaml
```

## Documentation Overview

| Document | Purpose | Use When |
|----------|---------|----------|
| QUICKSTART.md | Get started quickly | First time setup |
| HYPERSDK_INTEGRATION.md | Complete reference | Detailed integration |
| WORKFLOW_INTEGRATION_COMPLETE.md | Implementation details | Development reference |
| INTEGRATION_TEST_REPORT.md | Test results | Verify functionality |
| HYPERSDK_INTEGRATION_SUCCESS.md | Success summary | Overview |
| PHOTON_TEST_RESULTS.md | Real VM test | Performance analysis |

## Integration Status

✅ **PRODUCTION READY**

- All code compiles
- All tests pass
- Real VM tested (Photon OS, 951MB, 35.1s)
- Documentation complete
- Error handling working
- Performance acceptable

## Support

- Integration Guide: `HYPERSDK_INTEGRATION.md`
- Quick Start: `QUICKSTART.md`
- Test Results: `PHOTON_TEST_RESULTS.md`
- Example Manifests: `examples/manifest-workflow/`

---

**Last Updated:** 2026-01-24
**Integration Version:** 1.0
**Status:** Production Ready ✅
