# SPDX-License-Identifier: LGPL-3.0-or-later
# Makefile for hyper2kvm - Enterprise-friendly wrapper around Hatch
#
# This Makefile provides traditional make targets for enterprise users
# while leveraging Hatch for modern Python project management.
#
# Quick start:
#   make help        - Show available targets
#   make test        - Run unit tests
#   make install     - Install the package
#   make clean       - Clean build artifacts

.PHONY: help test test-unit test-integration test-all test-cov lint fmt security check ci install dev-install build publish clean clean-all docs rpm

# Default target
.DEFAULT_GOAL := help

# Check if hatch is installed
HATCH := $(shell command -v hatch 2> /dev/null)

help: ## Show this help message
	@echo "hyper2kvm - Hypervisor to KVM/QEMU Migration Toolkit"
	@echo ""
	@echo "Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Advanced Hatch commands:"
	@echo "  hatch run test-cov-all      - Test with coverage for all tests"
	@echo "  hatch run security-audit    - Generate security audit report"
	@echo "  hatch run docs-build        - Build documentation"
	@echo "  hatch env show              - Show all environments"
	@echo ""
	@echo "For more information, see: https://github.com/ssahani/hyper2kvm"

# Testing targets
test: ## Run unit tests
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run test

test-unit: ## Run unit tests only
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run test-unit

test-integration: ## Run integration tests
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run test-integration

test-all: ## Run all tests (unit + integration)
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run test-all

test-cov: ## Run tests with coverage report
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run test-cov
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

# Code quality targets
lint: ## Run code linting (ruff + mypy)
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run lint

fmt: ## Format code with ruff
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run fmt

fmt-check: ## Check code formatting without modifying
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run fmt-check

# Security targets
security: ## Run security scans (bandit + safety)
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run security

# Combined targets
check: ## Run tests + lint + security
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run check

ci: ## Run full CI pipeline (test-cov + lint + security)
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run ci

# Installation targets
install: ## Install the package
	pip install .

install-full: ## Install with all optional dependencies
	pip install .[full]

dev-install: ## Install in development mode with all dependencies
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	pip install -e .[dev,full]
	@echo ""
	@echo "Development environment ready!"
	@echo "Run 'make test' to verify installation."

# Build targets
build: ## Build source and wheel distributions
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch build
	@echo ""
	@echo "Built packages:"
	@ls -lh dist/

publish: ## Publish to PyPI (requires PYPI_TOKEN)
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch publish

publish-test: ## Publish to TestPyPI
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch publish -r test

# Documentation targets
docs: ## Build documentation
	$(MAKE) -C man html
	@echo ""
	@echo "Documentation built in man/build/html/"
	@echo "Open man/build/html/index.html in your browser"

docs-serve: ## Serve documentation locally
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run docs-serve

# RPM packaging (Fedora/RHEL)
rpm: ## Build RPM package
	python3 -m build --sdist
	@echo ""
	@echo "To build RPM, run:"
	@echo "  rpmbuild -ba hyper2kvm.spec"

# Cleanup targets
clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info .eggs/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	find . -type d -name '*.egg' -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage .pytest_cache/
	rm -rf .ruff_cache/ .mypy_cache/
	@echo "Build artifacts cleaned"

clean-all: clean ## Clean everything including test data
	rm -rf tests/test-data/*.vmdk tests/test-data/*.img tests/test-data/*.qcow2
	rm -rf man/build/
	@echo "All artifacts and test data cleaned"

# Matrix testing across Python versions
test-matrix: ## Test across all Python versions (3.10, 3.11, 3.12)
ifndef HATCH
	@echo "Hatch not found. Installing hatch..."
	pip install hatch
endif
	hatch run test:run

# Version information
version: ## Show version information
	@python3 -c "import sys; sys.path.insert(0, '.'); from hyper2kvm import __version__; print(f'hyper2kvm version: {__version__}')"
	@echo "Python: $(shell python3 --version)"
ifdef HATCH
	@echo "Hatch: $(shell hatch --version)"
else
	@echo "Hatch: not installed (pip install hatch)"
endif

# Show environment information
env-info: ## Show development environment information
	@echo "Development Environment Information"
	@echo "===================================="
	@echo "Python: $(shell python3 --version)"
	@echo "Pip: $(shell pip --version)"
ifdef HATCH
	@echo "Hatch: $(shell hatch --version)"
	@hatch env show
else
	@echo "Hatch: not installed"
	@echo ""
	@echo "To install hatch: pip install hatch"
endif

# Quick start for new developers
quickstart: ## Quick start for new developers
	@echo "Setting up hyper2kvm development environment..."
	@echo ""
	pip install hatch
	$(MAKE) dev-install
	@echo ""
	@echo "Running initial tests..."
	$(MAKE) test
	@echo ""
	@echo "=========================================="
	@echo "Development environment ready!"
	@echo "=========================================="
	@echo ""
	@echo "Next steps:"
	@echo "  make test        - Run tests"
	@echo "  make lint        - Check code quality"
	@echo "  make help        - Show all commands"
