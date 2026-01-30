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

## See Also

- [../examples/](../examples/) - Usage examples and demos
- [../docs/guides/](../docs/guides/) - User guides
- [../docs/development/](../docs/development/) - Developer documentation
- [../docs/helm-repository.md](../docs/helm-repository.md) - Helm repository guide
