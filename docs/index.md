# SUS - Simple Universal Scraper

Async documentation scraper for converting websites to Markdown format. Built with Python 3.12+, httpx, and asyncio.

## What is SUS?

SUS (Simple Universal Scraper) is a config-driven web scraper for converting documentation websites to Markdown format with preserved assets. Built with Python 3.12+ using httpx and asyncio, it controls crawling through YAML configuration files with regex/glob/prefix pattern matching, token bucket rate limiting, and dual-level concurrency controls.

**Key features:**

- httpx async HTTP client with asyncio for concurrent page fetching
- Pydantic 2.9+ validated YAML configuration files
- Token bucket rate limiting (configurable req/s with burst capacity)
- Dual concurrency: global (10) + per-domain (2) connection limits
- markdownify-based HTML → Markdown with YAML frontmatter
- Link rewriting to relative paths calculated by directory depth
- Concurrent asset downloads (images, CSS, JS) with SHA-256 deduplication
- Rich terminal UI with real-time crawl statistics and progress tracking

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd sus

# Install dependencies with uv
uv sync

# Verify installation
uv run sus --version
```

### Your First Scrape

```bash
# Scrape with example config (limit to 10 pages for testing)
uv run sus scrape --config examples/aptly.yaml --max-pages 10

# Full scrape (no page limit)
uv run sus scrape --config examples/aptly.yaml
```

### Create Your Own Config

```bash
# Interactive configuration wizard
uv run sus init my-config.yaml

# Validate your config
uv run sus validate my-config.yaml

# Run the scraper
uv run sus scrape --config my-config.yaml
```

## Documentation Structure

This documentation is organized into three main sections:

### User Guide

- **[Configuration Guide](api/config.md)** - Learn how to configure scrapers with YAML files
- **[CLI Reference](api/cli.md)** - Command-line interface documentation
- **[Crawler Guide](api/crawler.md)** - Understanding the crawling engine

### API Reference

Complete API documentation auto-generated from source code docstrings. See the **[API Overview](api/overview.md)** for a full module listing.

### Development

For contributors and developers:

- **Architecture** - System design and implementation
- **Contributing** - How to contribute to the project
- **Testing** - Running tests and type checking

## Use Cases

- Offline documentation mirrors with relative links and preserved assets
- Documentation archival for compliance and auditing
- Legacy HTML documentation conversion to Markdown format
- Custom documentation processing pipelines with configurable output structure

## Requirements

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## License

This project is currently unlicensed. Please contact the maintainer for licensing information.

## Core Dependencies

- [httpx](https://www.python-httpx.org/) 0.28+ - HTTP/2 async client for page fetching
- [Pydantic](https://docs.pydantic.dev/) 2.9+ - YAML config validation with type coercion
- [Typer](https://typer.tiangolo.com/) 0.15+ - CLI argument parsing and command routing
- [Rich](https://rich.readthedocs.io/) 14+ - Terminal progress bars and formatted output
- [markdownify](https://github.com/matthewwithanm/python-markdownify) 0.14+ - HTML to Markdown parser
- [lxml](https://lxml.de/) 5.3+ - Fast HTML parsing for link extraction
