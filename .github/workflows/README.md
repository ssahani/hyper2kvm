# GitHub Actions Workflows

This directory contains automated CI/CD workflows for the hyper2kvm project.

## Workflows

### 🧪 tests.yml - Automated Testing
**Triggers:** Push to main/develop, Pull Requests

**Jobs:**
- **test**: Runs unit tests on Python 3.10, 3.11, and 3.12
  - Installs system dependencies (libguestfs, QEMU, libvirt)
  - Runs pytest with coverage on Python 3.12
  - Uploads coverage to Codecov

- **lint**: Code quality checks
  - Runs ruff for linting
  - Runs mypy for type checking

- **integration**: Integration tests (main branch only)

### 🔒 security.yml - Security Scanning
**Triggers:** Push to main, Pull Requests, Weekly schedule (Mondays)

**Jobs:**
- **security**: Scans for security vulnerabilities
  - Runs Bandit for Python security issues
  - Runs pip-audit for known CVEs in dependencies
  - Uploads results as artifacts

- **dependency-review**: Reviews dependency changes in PRs

### 📦 release.yml - Release Automation
**Triggers:** Tags matching `v*.*.*`

**Jobs:**
- **release**: Creates GitHub releases and publishes to PyPI
  - Builds Python packages
  - Generates changelog from commits
  - Creates GitHub release with assets
  - Publishes to PyPI (if token configured)

### 📚 docs.yml - Documentation
**Triggers:** Push/PR to docs or markdown files

**Jobs:**
- **build-docs**: Validates documentation
  - Checks markdown links
  - Builds Sphinx documentation
  - Validates README sections

- **deploy-docs**: Deploys to GitHub Pages (main branch only)

## Configuration Files

### dependabot.yml
Automatically creates PRs to update:
- GitHub Actions versions (weekly)
- Python dependencies (weekly)

### Issue Templates
- **bug_report.md**: Structured bug reports
- **feature_request.md**: Feature suggestions

### Pull Request Template
Standardized PR checklist ensuring:
- Tests pass
- Documentation updated
- Security considered
- Code reviewed

## Badges

Add these to your README.md:

```markdown
[![Tests](https://github.com/ssahani/hyper2kvm/workflows/Tests/badge.svg)](https://github.com/ssahani/hyper2kvm/actions/workflows/tests.yml)
[![Security](https://github.com/ssahani/hyper2kvm/workflows/Security%20Checks/badge.svg)](https://github.com/ssahani/hyper2kvm/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/ssahani/hyper2kvm/branch/main/graph/badge.svg)](https://codecov.io/gh/ssahani/hyper2kvm)
```

## Secrets Required

For full functionality, configure these GitHub secrets:

- `PYPI_API_TOKEN`: For publishing to PyPI (releases)
- `CODECOV_TOKEN`: For uploading coverage (optional, public repos work without)

## Local Testing

Run the same checks locally before pushing:

```bash
# Run tests
python -m pytest tests/unit/ -v --cov=hyper2kvm

# Run linting
ruff check hyper2kvm/

# Run type checking
mypy hyper2kvm/ --ignore-missing-imports

# Run security scan
bandit -r hyper2kvm/
```
