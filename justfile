# SUS - Simple Universal Scraper
# Essential development commands

# List all available recipes
default:
    @just --list

# Run tests
test *ARGS:
    uv run pytest {{ARGS}}

# Run tests with coverage report
test-cov:
    uv run pytest --cov=src/sus --cov-report=term-missing --cov-report=html

# Run linter
lint:
    uv run ruff check src/sus/ tests/

# Run linter with auto-fix
lint-fix:
    uv run ruff check src/sus/ tests/ --fix

# Format code
format:
    uv run ruff format src/sus/ tests/

# Run type checker
type-check:
    uv run mypy src/sus/ --strict

# Run all quality checks (lint, type-check, test)
check: lint type-check test

# Install core dependencies
install:
    uv sync

# Install with development tools
install-dev:
    uv sync --group dev

# Install all dependency groups (dev + docs)
install-all:
    uv sync --group dev --group docs

# Serve documentation locally with live reload
docs-serve:
    uv run mkdocs serve

# Build static documentation
docs-build:
    uv run mkdocs build

# Clean temporary files and caches
clean:
    rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov/
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete
