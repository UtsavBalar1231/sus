# Contributing to SUS

Thank you for your interest in contributing to SUS! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

- Be respectful and professional
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Assume good intentions

## Getting Started

### Development Setup

```bash
# Clone the repository
git clone https://github.com/UtsavBalar1231/sus.git
cd sus

# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev --group docs

# Verify installation
uv run sus --version
uv run pytest
```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/my-feature
```

### 2. Make Your Changes

Follow the coding standards below and write tests for new functionality.

### 3. Run Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/sus --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_config.py

# Verbose output
uv run pytest -v
```

### 4. Type Check

```bash
# Type check entire codebase
uv run mypy src/sus/ --strict

# Check specific file
uv run mypy src/sus/config.py
```

### 5. Lint and Format

```bash
# Check for linting issues
uv run ruff check src/sus/

# Auto-fix issues
uv run ruff check src/sus/ --fix

# Format code
uv run ruff format src/sus/
```

### 6. Commit Changes

```bash
# Stage changes
git add .

# Commit with clear message
git commit -m "Add feature: description of changes"
```

### 7. Push and Create PR

```bash
# Push to your fork
git push origin feature/my-feature

# Open a pull request on GitHub
```

## Coding Standards

### Type Hints

All functions must have complete type annotations:

```python
def my_function(url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Build a response dictionary containing URL and timeout values."""
    return {"url": url, "timeout": timeout}
```

### Docstrings

Use Google-style docstrings for all public functions and classes:

```python
def fetch_page(url: str, timeout: float = 5.0) -> str:
    """Fetch HTML content from a URL.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds

    Returns:
        HTML content as string

    Raises:
        HTTPError: If request fails

    Examples:
        >>> html = fetch_page("https://example.com")
        >>> print(len(html))
        1234
    """
    ...
```

### Code Style

- **Line length**: Maximum 100 characters
- **Imports**: Sorted and grouped (stdlib, third-party, local)
- **Naming**:
  - Functions/variables: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_CASE`
- **Async**: Use `async`/`await` patterns, not callbacks

### Error Handling

```python
# Correct: Specific exception types with contextual error messages
try:
    config = load_config(path)
except FileNotFoundError:
    raise ConfigError(f"Config file not found: {path}") from None
except ValidationError as e:
    raise ConfigError(f"Invalid config: {e}") from e

# Incorrect: Bare except clause silently catches all exceptions
try:
    config = load_config(path)
except:
    pass
```

## Testing Requirements

### Test Coverage

- Maintain test coverage above **80%**
- Write tests for all new features
- Add tests when fixing bugs

### Test Structure

```python
def test_feature_name():
    """Verify config loads correctly with valid YAML."""
    # Arrange
    config = SusConfig(name="test", site=...)

    # Act
    result = some_function(config)

    # Assert
    assert result.status == "success"
```

### Async Tests

```python
async def test_async_feature():
    """Verify crawler returns 200 status for valid URLs."""
    async with Crawler(config) as crawler:
        result = await crawler.fetch("https://example.com")
        assert result.status_code == 200
```

### Using Fixtures

```python
def test_with_fixture(mock_config):
    """Verify mock config has expected test name."""
    assert mock_config.name == "test"
```

## Documentation

### Module Docstrings

Provide comprehensive module-level documentation:

```python
"""Module Name

Brief description of module purpose.

# Overview

Detailed overview of what the module does.

# Quick Start

## Basic Usage

```python
from sus import Crawler

async with Crawler(config) as crawler:
    result = await crawler.fetch(url)
```

# Key Concepts

Explanation of important concepts.
"""
```

### Updating Documentation

```bash
# Build documentation locally
uv run mkdocs serve

# View at http://127.0.0.1:8000

# Build static site
uv run mkdocs build
```

## Pull Request Process

### Before Submitting

- [ ] Tests pass (`uv run pytest`)
- [ ] Type checking passes (`uv run mypy src/sus/ --strict`)
- [ ] Linting passes (`uv run ruff check src/sus/`)
- [ ] Code is formatted (`uv run ruff format src/sus/`)
- [ ] Documentation is updated
- [ ] CHANGELOG is updated (if applicable)

### PR Description

Include in your PR description:

1. **What** - What changes does this PR make?
2. **Why** - Why are these changes needed?
3. **How** - How do the changes work?
4. **Testing** - How were the changes tested?

### Review Process

1. Automated checks must pass (tests, linting, type checking)
2. Code review by maintainer(s)
3. Address review feedback
4. Maintainer merges when approved

## Release Process

(For maintainers)

1. Update version in `src/sus/__init__.py`
2. Update CHANGELOG.md
3. Create git tag: `git tag v0.1.1`
4. Push tag: `git push --tags`
5. GitHub Actions will build and publish

## Questions or Problems?

- **Bug reports**: Open an issue with reproduction steps
- **Feature requests**: Open an issue describing the feature
- **Questions**: Open a discussion on GitHub

## License

By contributing to SUS, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for contributing to SUS!
