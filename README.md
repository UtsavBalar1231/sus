# SUS - Simple Universal (Docs) Scraper

Modern async documentation scraper for converting websites to Markdown.

**Version:** 0.1.0 | **Python:** 3.12+

---

## Overview

SUS is a config-driven web scraper designed for converting documentation websites into clean Markdown format with preserved assets. Built with modern async Python, it provides fine-grained control over crawling behavior through YAML configuration files.

**What SUS does:**
- Crawls documentation sites starting from configured URLs
- Converts HTML pages to clean Markdown with YAML frontmatter
- Downloads and organizes assets (images, CSS, JavaScript)
- Rewrites internal links to relative paths for offline browsing
- Respects rate limits and robots.txt

**Use cases:**
- Creating offline documentation mirrors
- Archiving documentation for compliance
- Converting legacy docs to Markdown format
- Building custom documentation processing pipelines

---

## Features

- ✅ **Async crawling** with httpx and asyncio for high performance
- ✅ **YAML configuration** with Pydantic validation and helpful error messages
- ✅ **Token bucket rate limiting** supporting burst traffic patterns
- ✅ **Dual concurrency limits** (global + per-domain) for respectful crawling
- ✅ **Exponential backoff** retry logic for transient failures
- ✅ **HTML → Markdown conversion** with configurable frontmatter
- ✅ **Automatic link rewriting** to relative paths for offline use
- ✅ **Asset downloading** with deduplication and parallel downloads
- ✅ **Rich progress bars** and real-time statistics
- ✅ **Dry-run mode** for previewing scraper behavior
- ✅ **Pattern matching** with regex, glob, and prefix filters
- ✅ **Depth limiting** and max page controls
- ✅ **URL normalization** with fragment and query parameter handling

---

## Installation

### Using uv (recommended)

```bash
# Clone the repository
git clone <repo-url>
cd sus

# Install dependencies with uv
uv sync

# Verify installation
uv run sus --version
```

### Using pip

```bash
# Clone the repository
git clone <repo-url>
cd sus

# Install in development mode
pip install -e .

# Verify installation
sus --version
```

**Requirements:**
- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

---

## Quick Start

### 1. Scrape with example config

```bash
# Scrape Aptly documentation (limit to 10 pages for testing)
uv run sus scrape --config examples/aptly.yaml --max-pages 10

# Full scrape (no page limit)
uv run sus scrape --config examples/aptly.yaml
```

### 2. Create your own config

```bash
# Interactive configuration wizard
uv run sus init my-config.yaml

# Follow the prompts to set up your scraper
```

### 3. Validate config

```bash
# Check configuration syntax and schema
uv run sus validate my-config.yaml
```

### 4. List example configs

```bash
# See all available example configurations
uv run sus list
```

---

## CLI Commands

### `sus scrape`

Run the scraper with a configuration file.

```bash
sus scrape --config FILE [OPTIONS]
```

**Options:**
- `--config, -c FILE` (required) - Path to YAML configuration file
- `--output, -o DIR` - Override output directory from config
- `--max-pages N` - Limit number of pages to crawl
- `--verbose, -v` - Enable verbose logging (DEBUG level)
- `--dry-run` - Simulate scraping without writing files
- `--preview` - Export dry-run JSON report

**Examples:**

```bash
# Basic scrape
sus scrape --config my-config.yaml

# Limit pages and use verbose logging
sus scrape --config my-config.yaml --max-pages 50 --verbose

# Preview what would be scraped
sus scrape --config my-config.yaml --dry-run --max-pages 10

# Override output directory
sus scrape --config my-config.yaml --output /tmp/docs
```

### `sus validate`

Validate configuration file syntax and schema.

```bash
sus validate CONFIG
```

Checks for:
- Valid YAML syntax
- Required fields present
- Correct data types
- Pattern syntax errors
- URL format validation

**Example:**

```bash
sus validate my-config.yaml
```

### `sus init`

Create a new configuration file interactively.

```bash
sus init [OUTPUT] [--force]
```

**Arguments:**
- `OUTPUT` - Output path (default: `config.yaml`)

**Options:**
- `--force, -f` - Overwrite existing file

**Example:**

```bash
# Create config with wizard prompts
sus init my-project.yaml

# Overwrite existing config
sus init my-project.yaml --force
```

### `sus list`

List all example configurations.

```bash
sus list
```

Shows available example configs with descriptions and start URLs.

### `sus --version`

Display SUS version.

```bash
sus --version
```

---

## Configuration Guide

SUS uses YAML configuration files validated by Pydantic models. Here's a complete example:

```yaml
# Project metadata
name: my-docs
description: Documentation scraper for MyProject

# Site configuration
site:
  # Starting URLs for crawler (required)
  start_urls:
    - https://example.com/docs/

  # Restrict crawling to these domains (required)
  allowed_domains:
    - example.com

# Crawling rules and behavior
crawling:
  # URL patterns to include (whitelist)
  include_patterns:
    - pattern: "^/docs/"
      type: regex

  # URL patterns to exclude (blacklist)
  exclude_patterns:
    - pattern: "*.pdf"
      type: glob

  # Crawl depth limit (0 = start URLs only, null = unlimited)
  depth_limit: null

  # Maximum pages to crawl (null = unlimited)
  max_pages: null

  # Rate limiting: seconds between requests
  delay_between_requests: 0.5

  # Maximum concurrent requests across all domains
  global_concurrent_requests: 10

  # Maximum concurrent requests per domain
  per_domain_concurrent_requests: 2

  # Retry configuration
  max_retries: 3
  retry_backoff: 2.0  # Exponential backoff multiplier

  # Respect robots.txt
  respect_robots_txt: true

# Output configuration
output:
  # Base output directory
  base_dir: output

  # Directory structure
  structure:
    docs_dir: docs
    assets_dir: assets

  # URL to file path mapping
  path_mapping:
    mode: auto  # auto | flat | hierarchical
    strip_prefix: /docs  # Remove this prefix from URLs
    index_file: index.md  # Name for directory index files

  # Markdown generation
  markdown:
    add_frontmatter: true
    frontmatter_fields:
      - title
      - url
      - scraped_at

# Asset handling
assets:
  # Download assets referenced in pages
  download: true

  # Asset types to download
  types:
    - images  # img, picture, source[srcset]
    - css     # link[rel=stylesheet]
    - js      # script[src]

  # Rewrite asset paths to relative URLs
  rewrite_paths: true
```

### Configuration Sections

#### `site` (required)

Defines the website to scrape.

- **`start_urls`** (list[str], required) - Entry points for crawling
- **`allowed_domains`** (list[str], required) - Restrict crawling to these domains

#### `crawling` (optional)

Controls crawling behavior.

- **`include_patterns`** (list) - URL patterns to crawl (whitelist)
  - `pattern` (str) - Pattern string
  - `type` (enum) - Pattern type: `regex`, `glob`, or `prefix`
- **`exclude_patterns`** (list) - URL patterns to skip (blacklist, takes precedence)
- **`depth_limit`** (int | null) - Maximum crawl depth from start URLs
- **`max_pages`** (int | null) - Maximum number of pages to crawl
- **`delay_between_requests`** (float) - Seconds between requests (default: 0.5)
- **`global_concurrent_requests`** (int) - Max concurrent requests total (default: 10)
- **`per_domain_concurrent_requests`** (int) - Max concurrent requests per domain (default: 2)
- **`max_retries`** (int) - Number of retry attempts (default: 3)
- **`retry_backoff`** (float) - Exponential backoff multiplier (default: 2.0)
- **`respect_robots_txt`** (bool) - Obey robots.txt (default: true)

#### `output` (optional)

Configures output file generation.

- **`base_dir`** (str) - Root output directory (default: "output")
- **`structure.docs_dir`** (str) - Subdirectory for markdown files (default: "docs")
- **`structure.assets_dir`** (str) - Subdirectory for assets (default: "assets")
- **`path_mapping.mode`** (enum) - Path generation mode: `auto`, `flat`, `hierarchical`
- **`path_mapping.strip_prefix`** (str) - Remove this prefix from URL paths
- **`path_mapping.index_file`** (str) - Filename for index pages (default: "index.md")
- **`markdown.add_frontmatter`** (bool) - Add YAML frontmatter to files
- **`markdown.frontmatter_fields`** (list[str]) - Fields to include in frontmatter

#### `assets` (optional)

Controls asset downloading.

- **`download`** (bool) - Enable asset downloads (default: true)
- **`types`** (list[str]) - Asset types: `images`, `css`, `js`
- **`rewrite_paths`** (bool) - Convert asset URLs to relative paths (default: true)

### Pattern Matching

SUS supports three pattern types for URL filtering:

**1. Regex** - Full regular expression support

```yaml
- pattern: "^/docs/(api|guide)/"
  type: regex
```

**2. Glob** - Shell-style wildcards

```yaml
- pattern: "*.html"
  type: glob
```

**3. Prefix** - Simple string prefix

```yaml
- pattern: "/docs/"
  type: prefix
```

**Pattern precedence:** `exclude_patterns` takes precedence over `include_patterns`. If a URL matches both, it will be excluded.

---

## Examples

The `examples/` directory contains ready-to-use configurations:

### `examples/aptly.yaml`

Production scraper for Aptly documentation (~85 pages).

- Multiple include/exclude patterns
- Binary file exclusions (PDF, ZIP)
- Rate limiting and concurrency settings
- Complete asset downloading

```bash
uv run sus scrape --config examples/aptly.yaml
```

### `examples/simple-docs.yaml`

Minimal configuration showing only essential fields.

- Single start URL
- Basic prefix pattern matching
- Default rate limiting
- Suitable as a template for new projects

```bash
uv run sus scrape --config examples/simple-docs.yaml
```

### `examples/advanced-docs.yaml`

Comprehensive example showcasing all features.

- Multiple start URLs
- Complex regex/glob/prefix patterns
- Custom retry and rate limit settings
- Multi-domain crawling
- Demonstrates all configuration options

```bash
uv run sus scrape --config examples/advanced-docs.yaml
```

---

## Development

### Running Tests

SUS has comprehensive test coverage with 70+ tests.

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/sus --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_config.py

# Run with verbose output
uv run pytest -v
```

### Type Checking

SUS uses strict mypy type checking.

```bash
# Type check the entire codebase
uv run mypy src/sus/ --strict

# Check specific file
uv run mypy src/sus/config.py
```

### Linting and Formatting

Code quality is maintained with Ruff.

```bash
# Check for linting issues
uv run ruff check src/sus/

# Auto-fix linting issues
uv run ruff check src/sus/ --fix

# Format code
uv run ruff format src/sus/
```

### Project Structure

```
sus/
├── src/sus/
│   ├── __init__.py        # Package version
│   ├── __main__.py        # Entry point for python -m sus
│   ├── cli.py             # Typer CLI interface
│   ├── config.py          # Pydantic configuration models
│   ├── crawler.py         # Async web crawler engine
│   ├── rules.py           # URL filtering and rules engine
│   ├── converter.py       # HTML to Markdown conversion
│   ├── outputs.py         # File output management
│   ├── assets.py          # Asset downloading and rewriting
│   ├── scraper.py         # Main orchestration pipeline
│   ├── utils.py           # Utility functions
│   └── exceptions.py      # Custom exception classes
├── tests/
│   ├── test_config.py           # Configuration tests
│   ├── test_crawler.py          # Crawler engine tests
│   ├── test_url_normalizer.py  # URL normalization tests
│   └── test_integration.py     # End-to-end integration tests
├── examples/
│   ├── aptly.yaml          # Production Aptly scraper
│   ├── simple-docs.yaml    # Minimal example
│   └── advanced-docs.yaml  # All features example
├── pyproject.toml          # Project dependencies and config
├── README.md               # This file
└── CLAUDE.md               # Development notes for Claude Code
```

---

## Architecture

SUS is built in six phases, each implementing a distinct layer of functionality:

### Phase 1: Configuration System

Pydantic-based configuration with YAML loading, validation, and helpful error messages. Supports regex, glob, and prefix patterns for URL filtering.

**Key files:** `config.py`, `exceptions.py`

### Phase 2: Crawler Engine

Async HTTP client built on httpx with:
- Token bucket rate limiting for burst-friendly throttling
- Per-domain and global concurrency limits
- Exponential backoff retry logic
- robots.txt compliance
- URL normalization and deduplication

**Key files:** `crawler.py`, `rules.py`

### Phase 3: URL Filtering and Rules

Pattern matching engine supporting:
- Include patterns (whitelist)
- Exclude patterns (blacklist with precedence)
- Depth limiting
- Domain restrictions
- URL normalization (fragment/query handling)

**Key files:** `rules.py`

### Phase 4: Content Conversion

HTML to Markdown conversion with:
- markdownify library integration
- YAML frontmatter generation
- Link rewriting to relative paths
- Asset URL detection and rewriting

**Key files:** `converter.py`, `outputs.py`

### Phase 5: CLI Interface

Rich CLI built with Typer providing:
- Interactive config generation (`init`)
- Config validation (`validate`)
- Scraping with progress bars (`scrape`)
- Example listing (`list`)
- Dry-run and preview modes

**Key files:** `cli.py`, `scraper.py`

### Phase 6: Comprehensive Testing

139 passing tests covering:
- Configuration validation
- URL normalization
- Pattern matching
- Crawler behavior
- Integration workflows

**Key files:** `tests/test_*.py`

---

## Comparison to Scrapy

SUS is a purpose-built documentation scraper, not a general-purpose web scraping framework. Here's why we chose a custom solution:

| Feature | SUS | Scrapy |
|---------|-----|--------|
| **Async model** | Native async/await | Twisted (callback-based) |
| **Configuration** | YAML files | Python code |
| **Dependencies** | Minimal (httpx, pydantic) | Heavy (Twisted, many extensions) |
| **Learning curve** | Low (config-driven) | High (framework concepts) |
| **Type safety** | Full mypy --strict | Limited |
| **Use case** | Documentation scraping | General web scraping |

**When to use SUS:**
- Scraping documentation sites to Markdown
- Config-driven scraping workflows
- Modern Python 3.12+ async patterns
- Type-safe, maintainable code

**When to use Scrapy:**
- Complex scraping with JavaScript rendering
- Large-scale data extraction projects
- Need for middleware and pipelines
- Existing Scrapy infrastructure

---

## Project Status

- ✅ Core functionality complete
- ✅ 139 tests passing (100% green)
- ✅ mypy --strict compliance (full type safety)
- ✅ Comprehensive CLI with progress bars
- ✅ Example configurations
- ✅ Production-ready for documentation scraping

**Future enhancements:**
- JavaScript rendering support (Playwright integration)
- Sitemap.xml parsing
- Incremental scraping (resume interrupted scrapes)
- Plugin system for custom processors
- HTTP caching for development

---

## Contributing

Contributions are welcome! Please follow these guidelines:

### Code Style

- **Type hints:** All functions must have type annotations
- **Linting:** Pass `ruff check` without errors
- **Formatting:** Use `ruff format` before committing
- **Type checking:** Pass `mypy --strict` without errors

### Testing

- Write tests for all new features
- Maintain test coverage above 80%
- Follow existing test patterns in `tests/`
- Run full test suite before submitting PR

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make changes with tests
4. Run tests, type check, and linting
5. Commit with clear messages
6. Push to your fork
7. Open a PR with description of changes

---

## License

This project is currently unlicensed. Please contact the maintainer for licensing information.

---

## Acknowledgments

Built with:
- [httpx](https://www.python-httpx.org/) - Modern async HTTP client
- [Pydantic](https://docs.pydantic.dev/) - Data validation with type hints
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting and progress bars
- [markdownify](https://github.com/matthewwithanm/python-markdownify) - HTML to Markdown conversion

---

**SUS** - Simple Universal Scraper | Version 0.1.0
