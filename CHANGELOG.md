# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

### Changed
- Nothing yet

### Fixed
- Nothing yet

## [0.1.0] - 2026-01-18

### Added
- Modern build system with Hatch integration
- Enterprise-friendly Makefile wrapper (27 targets)
- Pre-commit hooks for automated code quality (10 checks)
- Comprehensive SECURITY.md policy
- BUILDING.md development guide
- Docker support with multi-stage builds
- Docker Compose for local development
- GitHub Actions workflows using Hatch
- Ruff configuration for modern linting
- Matrix testing across Python 3.10, 3.11, 3.12
- Semantic versioning workflow for automated releases
- Dependabot configuration for dependency updates

### Changed
- Updated GitHub Actions to use Hatch commands
- Modernized development workflow documentation
- Enhanced pyproject.toml with Hatch environments (+200 lines)
- Improved README with modern badges and development instructions

### Fixed
- **CRITICAL**: Replaced 2 bare except clauses in daemon_watcher.py with proper exception handling
- **CRITICAL**: Replaced 43 assert statements across 11 files with proper runtime validation
  - hyper2kvm/vmware/clients/client.py (13 asserts)
  - hyper2kvm/vmware/utils/v2v.py (10 asserts)
  - hyper2kvm/vmware/transports/vddk_client.py (6 asserts)
  - hyper2kvm/converters/flatten.py (4 asserts)
  - hyper2kvm/converters/qemu/converter.py (2 asserts)
  - hyper2kvm/vmware/transports/ovftool_client.py (2 asserts)
  - hyper2kvm/testers/libvirt_tester.py (2 asserts)
  - And 4 other files (1 assert each)
- **CRITICAL**: Added debug logging to 9 silent error suppressions in offline_fixer.py
- GitHub Actions workflow optimization

### Security
- Assert statements no longer removed with Python -O flag
- Better error messages for production debugging
- Improved exception handling prevents silent failures

## [0.0.2] - 2024-XX-XX

### Added
- Initial PyPI release
- Core hypervisor migration functionality
- VMware vSphere integration
- Azure support
- Windows VirtIO driver injection
- Linux bootloader repair
- Network configuration fixes
- Comprehensive test suite

### Security
- Path traversal protection in VMDK parser
- Input validation for all user inputs
- TLS certificate verification

## [0.0.1] - 2024-XX-XX

### Added
- Initial development release
- Basic VMware VMDK conversion
- libguestfs integration
- QEMU conversion support

---

## Versioning Strategy

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Incompatible API changes
- **MINOR**: Backwards-compatible functionality additions
- **PATCH**: Backwards-compatible bug fixes

## Release Process

1. Update version in `pyproject.toml` and `hyper2kvm/__init__.py`
2. Update this CHANGELOG.md
3. Create git tag: `git tag -a v0.1.0 -m "Release 0.1.0"`
4. Push tag: `git push origin v0.1.0`
5. GitHub Actions automatically builds and publishes to PyPI

## Links

- [PyPI Releases](https://pypi.org/project/hyper2kvm/#history)
- [GitHub Releases](https://github.com/ssahani/hyper2kvm/releases)
- [Unreleased Changes](https://github.com/ssahani/hyper2kvm/compare/v0.1.0...HEAD)

[Unreleased]: https://github.com/ssahani/hyper2kvm/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ssahani/hyper2kvm/compare/v0.0.2...v0.1.0
[0.0.2]: https://github.com/ssahani/hyper2kvm/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/ssahani/hyper2kvm/releases/tag/v0.0.1
