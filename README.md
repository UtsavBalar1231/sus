# SUS - Simple Universal Scraper

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-139%20passing-green.svg)]()
[![Type Checked](https://img.shields.io/badge/mypy-strict-blue.svg)]()

Async documentation scraper for converting websites to Markdown. Built with Python 3.12+, httpx, and asyncio.

---

## What is SUS?

SUS is a **config-driven web scraper** for converting documentation websites to Markdown format. Built with Python 3.12+ using httpx and asyncio, it controls crawling through YAML configuration files with regex/glob/prefix pattern matching, token bucket rate limiting, and dual-level concurrency controls.

**Use Cases:**
- Offline documentation mirrors with relative links and preserved assets
- Documentation archival for compliance and auditing
- Legacy HTML documentation conversion to Markdown format
- Custom documentation processing pipelines with configurable output structure

---

## Features

- **Async HTTP crawling** - httpx client with asyncio for concurrent page fetching
- **YAML configuration** - Pydantic 2.9+ validated config files with type checking
- **Token bucket rate limiting** - Configurable requests/second with burst capacity (default: 2 req/s, burst=5)
- **Dual concurrency limits** - Separate global (default: 10) and per-domain (default: 2) connection limits
- **HTML → Markdown conversion** - markdownify-based conversion with customizable YAML frontmatter fields
- **Link rewriting** - Converts absolute URLs to relative paths calculated by directory depth
- **Asset downloading** - Concurrent downloads of images, CSS, JS with SHA-256 deduplication
- **Rich terminal UI** - Real-time crawl statistics, progress bars, and HTTP status tracking
- **URL pattern matching** - Three filter types: regex (re.match), glob (fnmatch), prefix (str.startswith)

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd sus

# Install dependencies (using uv)
uv sync

# Verify installation
uv run sus --version
```

**Requirements:** Python 3.12+ and [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Your First Scrape

```bash
# Scrape with example config (limit to 10 pages for testing)
uv run sus scrape --config examples/aptly.yaml --max-pages 10

# View the results
ls output/
```

### Create Your Own Config

```bash
# Interactive configuration wizard
uv run sus init my-config.yaml

# Validate the config
uv run sus validate my-config.yaml

# Run the scraper
uv run sus scrape --config my-config.yaml
```

### Minimal Configuration Example

```yaml
name: my-docs

site:
  start_urls:
    - https://example.com/docs/
  allowed_domains:
    - example.com

# All other settings have sensible defaults
```

---

## Documentation

**[Full Documentation](https://UtsavBalar1231.github.io/sus/)** - Complete guides and API reference

### Quick Links

- **[Configuration Guide](docs/api/config.md)** - YAML configuration reference
- **[CLI Reference](docs/api/cli.md)** - Command-line interface
- **[API Documentation](docs/api/overview.md)** - Python API reference
- **[Examples](examples/)** - Real-world configuration examples

---

## CLI Commands

### `sus scrape`

Run the scraper with a configuration file.

```bash
sus scrape --config FILE [OPTIONS]

Options:
  --output, -o DIR    Override output directory
  --max-pages N       Limit number of pages to crawl
  --verbose, -v       Enable verbose logging (DEBUG)
  --dry-run           Simulate without writing files
```

### `sus validate`

Validate configuration file syntax and schema.

```bash
sus validate CONFIG
```

### `sus init`

Create a new configuration file interactively.

```bash
sus init [OUTPUT] [--force]
```

### `sus list`

List available example configurations.

```bash
sus list
```

---

## Development

### Running Tests

```bash
# Run all tests (139+ passing)
uv run pytest

# Run with coverage
uv run pytest --cov=src/sus --cov-report=term-missing
```

### Type Checking

```bash
# Type check with mypy --strict
uv run mypy src/sus/ --strict
```

### Linting and Formatting

```bash
# Check for issues
uv run ruff check src/sus/

# Auto-fix issues
uv run ruff check src/sus/ --fix

# Format code
uv run ruff format src/sus/
```

For more details, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Architecture

SUS implements a six-phase pipeline architecture:

1. **Configuration System** (`config.py`) - Pydantic 2.9+ models with YAML loading and validation
2. **Crawler Engine** (`crawler.py`) - httpx async client with token bucket rate limiter and semaphore-based concurrency
3. **URL Filtering** (`rules.py`) - lxml-based link extraction with regex/glob/prefix pattern matching
4. **Content Conversion** (`converter.py`) - markdownify HTML parser with YAML frontmatter generation
5. **CLI Interface** (`cli.py`) - Typer commands with Rich progress bars and real-time statistics
6. **Testing** (`tests/`) - 139+ pytest tests with pytest-asyncio and pytest-httpx, mypy --strict type checking

See the [full documentation](https://UtsavBalar1231.github.io/sus/) for implementation details.

---

## Project Status

**Current Release: v0.1.0**

- Core functionality implemented
- 139 tests passing with pytest
- mypy --strict type checking (zero errors)
- Tested with Python 3.12 on Linux

**Planned Features:**
- JavaScript rendering with Playwright integration
- Sitemap.xml parsing for site discovery
- Checkpoint-based incremental scraping (resume interrupted crawls)
- Plugin system for custom content processors

---

## License

This project is currently unlicensed. Please contact the maintainer for licensing information.

---

## Dependencies

**Core Runtime:**
- [httpx](https://www.python-httpx.org/) 0.28+ - HTTP/2 async client for page fetching
- [Pydantic](https://docs.pydantic.dev/) 2.9+ - YAML config validation with type coercion
- [Typer](https://typer.tiangolo.com/) 0.15+ - CLI argument parsing and command routing
- [Rich](https://rich.readthedocs.io/) 14+ - Terminal progress bars and formatted output
- [markdownify](https://github.com/matthewwithanm/python-markdownify) 0.14+ - HTML to Markdown parser
- [lxml](https://lxml.de/) 5.3+ - Fast HTML parsing for link extraction
- [PyYAML](https://pyyaml.org/) 6.0+ - YAML file loading

**Development:**
- [pytest](https://pytest.org/) 8.3+ with pytest-asyncio 0.24+ and pytest-httpx 0.34+
- [mypy](https://mypy-lang.org/) 1.14+ with types-pyyaml and lxml-stubs
- [ruff](https://github.com/astral-sh/ruff) 0.9+ - Linting and code formatting

---

**SUS** - Simple Universal Scraper | Version 0.1.0
