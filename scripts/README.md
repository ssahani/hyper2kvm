# Scripts

Utility scripts and tools for hyper2kvm development and operation.

## Directory Structure

```
scripts/
├── README.md                 # This file
├── demos/                    # Demo and showcase scripts
├── inspect_guest.py          # Guest OS inspection utility
├── run_tui.py                # TUI launcher script
├── bump-version.sh           # Version bumping utility
└── publish.sh                # Publishing/release script
```

## Utility Scripts

### inspect_guest.py
Guest OS inspection and analysis utility.

```bash
python scripts/inspect_guest.py /path/to/vm.qcow2
```

**Features:**
- Inspect VM disk images
- Detect guest OS type and version
- Analyze partition layout
- Check bootloader configuration
- Identify installed software

### run_tui.py
TUI (Text User Interface) launcher script.

```bash
python scripts/run_tui.py
```

**Features:**
- Launch interactive TUI dashboard
- Monitor VM migration progress
- Manage batch operations
- Orange-themed interface

## Development Scripts

### bump-version.sh
Automated version bumping for releases.

```bash
./scripts/bump-version.sh <major|minor|patch>
```

### publish.sh
Package publishing and release automation.

```bash
./scripts/publish.sh
```

## Demo Scripts

See [demos/README.md](demos/README.md) for demonstration scripts that showcase hyper2kvm features.

## Usage

Most scripts can be run directly:

```bash
# Utility scripts
python scripts/inspect_guest.py <image>
python scripts/run_tui.py

# Shell scripts
./scripts/bump-version.sh patch
./scripts/publish.sh
```

## Requirements

- Python 3.8+
- For TUI scripts: `pip install 'hyper2kvm[tui]'`
- For guest inspection: libguestfs-tools

## Helm Chart Management

### package-charts.sh
Package Helm charts and generate repository index.

```bash
# Package all charts
./scripts/package-charts.sh

# Package and update existing index
./scripts/package-charts.sh --update-index

# Package to custom directory
./scripts/package-charts.sh --output-dir /tmp/charts
```

**Features:**
- Lints charts before packaging
- Generates repository index.yaml
- Verifies packaged charts
- Supports index merging for updates

### bump-chart-version.sh
Bump Helm chart versions following semantic versioning.

```bash
# Bump patch version (1.6.0 -> 1.6.1)
./scripts/bump-chart-version.sh --type patch

# Bump minor version of operator chart (1.6.0 -> 1.7.0)
./scripts/bump-chart-version.sh --chart hyper2kvm-operator --type minor

# Set specific version
./scripts/bump-chart-version.sh --chart hyper2kvm-operator --version 2.0.0

# Dry run to preview changes
./scripts/bump-chart-version.sh --type minor --dry-run
```

**Features:**
- Semantic versioning (major.minor.patch)
- Updates both version and appVersion
- Dry run mode for preview
- Validates version format

### generate-webhook-certs.sh
Generate TLS certificates for Kubernetes admission webhooks.

```bash
# Generate certificates
./scripts/generate-webhook-certs.sh hyper2kvm-system hyper2kvm-webhook
```

**Features:**
- Generates CA certificate
- Generates server certificate with SANs
- Creates Kubernetes Secret
- Patches webhook configurations

## OpenShift & Kubernetes Deployment

### build-operator-images.sh
Build multi-arch container images for operator, worker, CLI, and daemon.

```bash
# Build all images
./scripts/build-operator-images.sh 2.1.0

# Build and push to custom registry
./scripts/build-operator-images.sh 2.1.0 ghcr.io/myorg
```

**Features:**
- Multi-arch builds (amd64, arm64)
- Builds operator, worker, CLI, daemon images
- Interactive push confirmation
- Version tagging (semver + latest)

### build-olm-bundle.sh
Build OLM bundle for OpenShift OperatorHub deployment.

```bash
# Build bundle image
./scripts/build-olm-bundle.sh 2.1.0

# Build and push to custom registry
./scripts/build-olm-bundle.sh 2.1.0 ghcr.io/myorg
```

**Features:**
- Validates bundle structure
- Updates CSV version
- Runs operator-sdk validation (if installed)
- Interactive push confirmation

### deploy-to-openshift.sh
Deploy operator to OpenShift cluster using Helm, OLM, or manual method.

```bash
# Deploy via Helm (recommended)
./scripts/deploy-to-openshift.sh 2.1.0 helm

# Deploy via OLM bundle
./scripts/deploy-to-openshift.sh 2.1.0 olm

# Deploy manually with manifests
./scripts/deploy-to-openshift.sh 2.1.0 manual hyper2kvm-system
```

**Features:**
- Three deployment methods
- Automatic namespace creation
- OpenShift-specific configuration
- Post-deployment verification

### test-openshift-deployment.sh
Comprehensive test suite for OpenShift deployment validation.

```bash
# Run test suite
./scripts/test-openshift-deployment.sh hyper2kvm-system
```

**Tests:**
- CRD installation
- Operator pod health
- Webhook pod health (if enabled)
- Routes and services
- SecurityContextConstraints
- RBAC permissions
- MigrationJob CRD functionality
- Operator logs validation
- Resource usage

## Release Workflow

Complete Helm chart release process:

```bash
# 1. Bump chart versions
./scripts/bump-chart-version.sh --type minor

# 2. Package charts
./scripts/package-charts.sh --update-index

# 3. Commit and tag
git add helm/ charts/
git commit -m "chore: release v1.7.0"
git tag v1.7.0
git push origin main --tags

# 4. GitHub Actions automatically publishes to GitHub Pages
```

## OpenShift Release Workflow

Complete OpenShift operator release:

```bash
# 1. Build operator images
./scripts/build-operator-images.sh 2.1.0
# Answer 'y' to push images

# 2. Build OLM bundle
./scripts/build-olm-bundle.sh 2.1.0
# Answer 'y' to push bundle

# 3. Test on OpenShift cluster
./scripts/deploy-to-openshift.sh 2.1.0 helm
./scripts/test-openshift-deployment.sh hyper2kvm-system

# 4. Submit to OperatorHub (optional)
# - Fork https://github.com/k8s-operatorhub/community-operators
# - Add bundle to operators/hyper2kvm-operator/
# - Create pull request
```

## See Also

- [../examples/](../examples/) - Usage examples and demos
- [../docs/guides/](../docs/guides/) - User guides
- [../docs/development/](../docs/development/) - Developer documentation
- [../docs/helm-repository.md](../docs/helm-repository.md) - Helm repository guide
- [../docs/deployment/openshift-deployment-guide.md](../docs/deployment/openshift-deployment-guide.md) - OpenShift deployment
- [../olm/README.md](../olm/README.md) - OLM bundle guide
- [../OPENSHIFT_QUICKSTART.md](../OPENSHIFT_QUICKSTART.md) - 5-minute OpenShift quickstart
