# Modernization Roadmap for hyper2kvm

This document tracks modern Python tooling and best practices implemented in hyper2kvm, plus future improvements.

## ✅ Completed Modernizations

### 1. Build System (2026-01-18)

**Status**: ✅ Complete

- ✅ Hatch integration in `pyproject.toml`
- ✅ Enterprise-friendly Makefile wrapper
- ✅ GitHub Actions updated to use Hatch
- ✅ Comprehensive `BUILDING.md` documentation
- ✅ Ruff configuration for linting and formatting
- ✅ Matrix testing across Python 3.10, 3.11, 3.12

**Commands**:
```bash
make test           # Traditional
hatch run test      # Modern
```

### 2. Pre-commit Hooks (2026-01-18)

**Status**: ✅ Complete

- ✅ `.pre-commit-config.yaml` with 8 hook categories
- ✅ Automated formatting (ruff)
- ✅ Security scanning (bandit)
- ✅ Type checking (mypy)
- ✅ Markdown linting
- ✅ Secret detection
- ✅ YAML formatting

**Setup**:
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

### 3. Security Policy (2026-01-18)

**Status**: ✅ Complete

- ✅ `SECURITY.md` with reporting procedures
- ✅ Known security considerations documented
- ✅ Security testing guidelines
- ✅ `.secrets.baseline` for secret scanning

### 4. Changelog (2026-01-18)

**Status**: ✅ Complete

- ✅ `CHANGELOG.md` following Keep a Changelog format
- ✅ Semantic versioning strategy documented
- ✅ Release process defined

### 5. Container Support (2026-01-18)

**Status**: ✅ Complete

- ✅ Multi-stage `Dockerfile` (dev, prod, testing)
- ✅ `docker-compose.yml` for local development
- ✅ `.dockerignore` for optimized builds
- ✅ Non-root user in production image
- ✅ Health checks

**Usage**:
```bash
# Development
docker-compose up dev

# Testing
docker-compose up test

# Documentation
docker-compose up docs
```

### 6. Existing Good Practices

Already implemented before modernization:

- ✅ Dependabot for dependency updates
- ✅ GitHub Actions CI/CD
- ✅ Codecov integration
- ✅ Issue templates
- ✅ RPM packaging workflow
- ✅ Security scanning (bandit, safety)
- ✅ Type hints (partial)

## 🚧 In Progress / High Priority

### 1. Automated Releases ⭐

**Priority**: High
**Status**: Planned

Add semantic release automation:

```yaml
# .github/workflows/release.yml enhancement
- uses: python-semantic-release/python-semantic-release@v9
```

**Benefits**:
- Automatic version bumping
- Changelog generation from commits
- GitHub releases
- PyPI publishing

**Implementation**:
```bash
pip install python-semantic-release
```

### 2. Code Coverage Badges

**Priority**: Medium
**Status**: Planned

Add coverage badges to README:

```markdown
[![codecov](https://codecov.io/gh/ssahani/hyper2kvm/branch/main/graph/badge.svg)](https://codecov.io/gh/ssahani/hyper2kvm)
[![Code Coverage](https://img.shields.io/codecov/c/github/ssahani/hyper2kvm)](https://codecov.io/gh/ssahani/hyper2kvm)
```

### 3. Modern Type Hints

**Priority**: Medium
**Status**: 25% complete

Update to Python 3.10+ type hints:

```python
# Old style
from typing import List, Dict, Optional

def process(items: List[str]) -> Dict[str, str]:
    ...

# New style (Python 3.10+)
def process(items: list[str]) -> dict[str, str]:
    ...
```

**Action**: Add `from __future__ import annotations` to all files

### 4. Structured Logging

**Priority**: Medium
**Status**: Planned

Replace standard logging with structured logging:

```bash
pip install structlog
```

```python
import structlog

logger = structlog.get_logger()
logger.info("vm_migration_started", vm_name="prod-web-01", source="vcenter")
```

**Benefits**:
- JSON output for log aggregation
- Contextual logging
- Better observability

## 🔮 Future Improvements

### 1. Modern Documentation (High Value)

**Tool**: MkDocs Material

Replace Sphinx with modern docs:

```bash
pip install mkdocs-material
pip install mkdocs-mermaid2-plugin
pip install mkdocstrings[python]
```

**Features**:
- Beautiful, responsive design
- Built-in search
- Automatic API docs from docstrings
- Mermaid diagram support
- Dark mode

**Structure**:
```
docs/
├── mkdocs.yml
├── index.md
├── getting-started/
│   ├── installation.md
│   └── quickstart.md
├── user-guide/
│   ├── cli-reference.md
│   └── yaml-examples.md
└── api/
    └── reference.md (auto-generated)
```

### 2. Performance Profiling

**Tools**: py-spy, memray

Add profiling targets:

```toml
# pyproject.toml
[tool.hatch.envs.default.scripts]
profile = "py-spy record -o profile.svg -- python -m hyper2kvm ..."
memory = "memray run --output memray.bin hyper2kvm ..."
```

### 3. Benchmarking

**Tool**: pytest-benchmark

```python
def test_vmdk_parsing_performance(benchmark):
    result = benchmark(parse_vmdk, "test.vmdk")
    assert result.valid
```

**CI Integration**:
- Store benchmarks in GitHub Pages
- Compare PR performance vs main branch

### 4. Property-Based Testing

**Tool**: Hypothesis

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=255))
def test_vmdk_path_validation(path):
    # Test with random valid inputs
    result = validate_vmdk_path(path)
    assert isinstance(result, bool)
```

### 5. Mutation Testing

**Tool**: mutmut

Verify test quality:

```bash
pip install mutmut
mutmut run
mutmut results
```

### 6. API Documentation

**Tool**: pdoc or mkdocstrings

Auto-generate API docs:

```bash
hatch run docs-api
```

### 7. GitHub Enhancements

#### GitHub Discussions

Enable for:
- Q&A
- Feature requests
- Community support

#### Issue Forms (YAML)

Replace markdown templates:

```yaml
# .github/ISSUE_TEMPLATE/bug_report.yml
name: Bug Report
description: File a bug report
body:
  - type: input
    id: version
    attributes:
      label: Version
      description: hyper2kvm version
    validations:
      required: true
```

#### Dependabot Groups

```yaml
# .github/dependabot.yml
groups:
  production:
    patterns:
      - "click"
      - "pyyaml"
  development:
    patterns:
      - "pytest*"
      - "ruff"
```

### 8. Code Quality Metrics

**Tool**: SonarCloud

Add code quality badges:

```markdown
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=hyper2kvm&metric=alert_status)](https://sonarcloud.io/dashboard?id=hyper2kvm)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=hyper2kvm&metric=sqale_rating)](https://sonarcloud.io/dashboard?id=hyper2kvm)
```

### 9. CLI Enhancements

**Tool**: Rich (already optional dependency)

Enhance CLI with:
- Progress bars
- Syntax highlighting
- Tables
- Better error messages

**Tool**: Typer (alternative to click)

Modern CLI framework:

```python
import typer

app = typer.Typer()

@app.command()
def migrate(
    vmdk: Path = typer.Argument(..., help="Path to VMDK file"),
    output: Path = typer.Option(..., help="Output path"),
):
    """Migrate a VM to KVM."""
    ...
```

### 10. Observability

**Tools**:
- OpenTelemetry for tracing
- Prometheus metrics export
- Grafana dashboards

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("migrate_vm"):
    # Migration code
    ...
```

### 11. SBOM Generation

**Tool**: CycloneDX

Generate Software Bill of Materials:

```bash
pip install cyclonedx-bom
cyclonedx-py -o sbom.json
```

### 12. REUSE Compliance

**Tool**: REUSE Software

Standardize licensing:

```bash
pip install reuse
reuse lint
```

### 13. Code Complexity Analysis

**Tool**: radon, wily

```bash
pip install radon wily
radon cc hyper2kvm/ -a
wily build hyper2kvm/
wily report hyper2kvm/
```

## 📊 Modernization Progress

| Category | Status | Priority | Effort |
|----------|--------|----------|--------|
| Build System | ✅ Complete | High | Medium |
| Pre-commit | ✅ Complete | High | Low |
| Security Policy | ✅ Complete | High | Low |
| Changelog | ✅ Complete | Medium | Low |
| Containers | ✅ Complete | Medium | Medium |
| Automated Releases | 🚧 Planned | High | Medium |
| Coverage Badges | 🚧 Planned | Medium | Low |
| Modern Type Hints | 🚧 25% | Medium | High |
| Structured Logging | 🔮 Future | Medium | Medium |
| MkDocs Material | 🔮 Future | High | Medium |
| Performance Tools | 🔮 Future | Low | Low |
| Benchmarking | 🔮 Future | Medium | Medium |
| Hypothesis | 🔮 Future | Low | High |
| Mutation Testing | 🔮 Future | Low | Medium |
| API Docs | 🔮 Future | Medium | Low |
| GitHub Features | 🔮 Future | Medium | Low |
| SonarCloud | 🔮 Future | Low | Low |
| Typer CLI | 🔮 Future | Low | High |
| Observability | 🔮 Future | Low | High |
| SBOM | 🔮 Future | Medium | Low |
| REUSE | 🔮 Future | Low | Low |

## 🎯 Quick Wins (Next Sprint)

Prioritized by value/effort ratio:

1. **Coverage badges** (5 min) - Add to README
2. **Automated releases** (2 hours) - python-semantic-release
3. **Issue forms** (1 hour) - Convert to YAML
4. **GitHub Discussions** (5 min) - Enable in settings
5. **Dependabot groups** (30 min) - Group updates
6. **API docs** (2 hours) - mkdocstrings setup

## 📚 Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [Hatch Documentation](https://hatch.pypa.io/)
- [pre-commit hooks](https://pre-commit.com/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Semantic Versioning](https://semver.org/)
- [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)
- [GitHub Actions Best Practices](https://docs.github.com/en/actions/learn-github-actions/best-practices-for-github-actions)

## 🤝 Contributing to Modernization

To contribute to modernization efforts:

1. Pick an item from "Future Improvements"
2. Create an issue: "Modernization: <feature>"
3. Open a PR with implementation
4. Update this document with status

---

**Last Updated**: 2026-01-18
**Status**: Active development
**Maintainer**: @ssahani
