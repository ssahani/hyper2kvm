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

## See Also

- [../examples/](../examples/) - Usage examples and demos
- [../docs/guides/](../docs/guides/) - User guides
- [../docs/development/](../docs/development/) - Developer documentation
