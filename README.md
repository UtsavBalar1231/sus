# SUS - Simple Universal Scraper

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Type Checked](https://img.shields.io/badge/mypy-strict-blue.svg)]()

**High-performance async web scraper for converting documentation sites to Markdown.**

Built with Python 3.12+, httpx, and asyncio. Designed for scraping documentation websites with 25-50 pages/sec throughput, HTTP/2 support, and intelligent checkpoint/resume.

---

## Quick Install

```bash
# Using uv (recommended)
uv pip install sus

# Or using pip
pip install sus

# Verify installation
sus --version
```

**Requirements:** Python 3.12+

---

## 30-Second Example

Create a config file `docs.yaml`:

```yaml
name: my-docs

site:
  start_urls:
    - https://docs.python.org/3/
  allowed_domains:
    - docs.python.org

output:
  base_dir: ./output

crawling:
  max_pages: 50
```

Run the scraper:

```bash
sus scrape --config docs.yaml
```

Output:

```
output/
├── docs/           # Markdown files with frontmatter
├── assets/         # Downloaded images, CSS, JS
└── checkpoint.json # Resume state (if enabled)
```

---

## Key Features

**Core Capabilities:**
- **Config-driven YAML** - Define scraping behavior declaratively
- **Async architecture** - Built on httpx and asyncio for maximum performance
- **HTTP/2 support** - Connection pooling, multiplexing, 60-80% overhead reduction
- **Type-safe** - Full mypy --strict compliance with Pydantic 2.9+ validation

**Scraping Features:**
- **Checkpoint/Resume** - Incremental scraping with crash recovery (JSON or SQLite backends)
- **JavaScript rendering** - Playwright integration for SPA sites
- **Sitemap parsing** - Fast URL discovery via sitemap.xml
- **Authentication** - Built-in support for Basic, Cookie, Header, and OAuth2 auth
- **Content filtering** - Regex/glob/prefix URL patterns, CSS selectors
- **Asset handling** - Download and rewrite image/CSS/JS references with deduplication

**Performance & Reliability:**
- **Rate limiting** - Token bucket algorithm with burst support
- **HTTP caching** - RFC 9111 compliant caching for development
- **Pipeline mode** - Multi-stage processing with memory-aware queues (3-10x speedup)
- **Error handling** - Retry logic with exponential backoff, graceful degradation

**Extensibility:**
- **Plugin system** - 5 lifecycle hooks with built-in plugins (code highlighting, image optimization, link validation)
- **Custom backends** - Pluggable checkpoint storage (JSON for <10K pages, SQLite for larger)

---

## Documentation

**[Full Documentation →](https://UtsavBalar1231.github.io/sus/)**

### Quick Links

- **[Getting Started](https://UtsavBalar1231.github.io/sus/getting-started/)** - Installation and first scrape tutorial
- **[Configuration Reference](https://UtsavBalar1231.github.io/sus/configuration/)** - Complete YAML schema documentation
- **[Examples](https://UtsavBalar1231.github.io/sus/examples/)** - Real-world configuration examples
- **[API Reference](https://UtsavBalar1231.github.io/sus/api/overview/)** - Python API documentation

---

## CLI Overview

```bash
# Run scraper with config
sus scrape --config FILE

# Validate config syntax
sus validate FILE

# Interactive config wizard
sus init [OUTPUT]

# List example configs
sus list

# Common options
sus scrape --config FILE \
  --output DIR \           # Override output directory
  --max-pages N \          # Limit page count
  --resume \               # Resume from checkpoint
  --reset-checkpoint \     # Start fresh
  --clear-cache            # Clear HTTP cache
```

See the [Getting Started guide](https://UtsavBalar1231.github.io/sus/getting-started/) for detailed usage.

---

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/UtsavBalar1231/sus.git
cd sus

# Install with dev dependencies
uv sync --group dev

# Optional: Install JavaScript rendering support
uv sync --group js

# Optional: Install plugin dependencies
uv sync --group plugins
```

### Quality Checks

```bash
# Run all checks (lint + type-check + test)
just check

# Individual commands
just lint          # ruff check
just lint-fix      # ruff check --fix
just format        # ruff format
just type-check    # mypy --strict
just test          # pytest
just test-cov      # pytest with coverage
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and coding standards.

---

## Architecture

SUS implements a six-stage pipeline:

1. **Configuration** - Pydantic 2.9+ models with YAML validation and type coercion
2. **Crawler** - httpx async client with token bucket rate limiting and robots.txt compliance
3. **URL Filtering** - lxml link extraction with regex/glob/prefix pattern matching
4. **Content Conversion** - markdownify HTML parser with YAML frontmatter generation
5. **CLI Interface** - Typer commands with Rich progress bars and real-time statistics
6. **Testing** - Comprehensive pytest suite with pytest-asyncio and pytest-httpx

**Advanced features:**
- **Backend system** - Pluggable checkpoint storage (JSON/SQLite) via `StateBackend` protocol
- **Plugin architecture** - 5 lifecycle hooks (PRE_CRAWL, POST_FETCH, POST_CONVERT, POST_SAVE, POST_CRAWL)
- **Pipeline mode** - Producer-consumer architecture with memory-aware queues

See [CLAUDE.md](CLAUDE.md) for comprehensive technical documentation.

---

## Project Status

**Production-ready features:**
- Checkpoint/resume with JSON and SQLite backends
- JavaScript rendering via Playwright
- Authentication (Basic, Cookie, Header, OAuth2)
- Plugin system with 3 built-in plugins
- Sitemap parsing and HTTP caching
- Memory monitoring and graceful degradation

**Quality:**
- mypy --strict type checking (zero errors)
- Comprehensive test coverage with pytest
- Tested on Python 3.12+ (Linux)

---

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Coding standards and conventions
- Testing requirements
- Pull request process

**Report issues:** [GitHub Issues](https://github.com/UtsavBalar1231/sus/issues)

---

## License

This project is currently unlicensed. Please contact the maintainer for licensing information.

---

**SUS** - Simple Universal Scraper
