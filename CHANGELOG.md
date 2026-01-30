# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Modern build system with Hatch integration
- Enterprise-friendly Makefile wrapper
- Pre-commit hooks for automated code quality
- Comprehensive SECURITY.md policy
- BUILDING.md development guide
- GitHub Actions workflows using Hatch
- Ruff configuration for modern linting
- Matrix testing across Python 3.10, 3.11, 3.12

### Changed
- Updated GitHub Actions to use Hatch commands
- Modernized development workflow documentation
- Enhanced pyproject.toml with Hatch environments

### Fixed
- GitHub Actions workflow optimization

## [0.0.3] - 2024-XX-XX

### Added
- Feature additions from 0.0.3

### Changed
- Changes from 0.0.3

### Fixed
- Bug fixes from 0.0.3

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
3. Create git tag: `git tag -a v0.0.3 -m "Release 0.0.3"`
4. Push tag: `git push origin v0.0.3`
5. GitHub Actions automatically builds and publishes to PyPI

## Links

- [PyPI Releases](https://pypi.org/project/hyper2kvm/#history)
- [GitHub Releases](https://github.com/ssahani/hyper2kvm/releases)
- [Unreleased Changes](https://github.com/ssahani/hyper2kvm/compare/v0.0.2...HEAD)

[Unreleased]: https://github.com/ssahani/hyper2kvm/compare/v0.0.2...HEAD
[0.0.3]: https://github.com/ssahani/hyper2kvm/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/ssahani/hyper2kvm/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/ssahani/hyper2kvm/releases/tag/v0.0.1
