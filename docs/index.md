# SUS Documentation

**Welcome to the SUS documentation!**

SUS (Simple Universal Scraper) is a high-performance async web scraper for converting documentation websites to Markdown format. Built with Python 3.12+, httpx, and asyncio.

---

## Getting Started

New to SUS? Start here for installation and your first scrape.

**[Getting Started Guide →](getting-started.md)**

Learn how to:
- Install SUS with uv or pip
- Run your first scrape
- Understand the output structure
- Explore next steps

---

## Configuration Reference

Complete YAML configuration documentation for all features.

**[Configuration Reference →](configuration.md)**

Covers:
- Basic configuration (minimal setup)
- Authentication (Basic, Cookie, Header, OAuth2)
- Checkpoint/Resume (incremental scraping)
- JavaScript rendering (Playwright integration)
- Sitemap parsing and HTTP caching
- Pipeline mode, plugins, and more

---

## Examples

Real-world configuration files for various documentation sites.

**[Examples →](examples.md)**

Includes configurations for:
- Python documentation
- Rust documentation
- Go documentation
- Vue.js documentation
- And many more

---

## API Reference

Python API documentation auto-generated from source code.

**[API Overview →](api/overview.md)**

Complete module reference:
- Configuration system (`config.py`)
- Crawler engine (`crawler.py`)
- URL filtering (`rules.py`)
- Content conversion (`converter.py`)
- CLI interface (`cli.py`)
- And more

---

## For Contributors

Want to contribute to SUS? Check out the development guide.

**[Contributing Guide →](CONTRIBUTING.md)**

Includes:
- Development setup
- Running tests and type checking
- Coding standards
- Pull request process

---

## Quick Links

- **[GitHub Repository](https://github.com/UtsavBalar1231/sus)** - Source code
- **[Report Issues](https://github.com/UtsavBalar1231/sus/issues)** - Bug reports and feature requests
- **[CLAUDE.md](CLAUDE.md)** - Comprehensive technical reference for Claude Code

---

## What is SUS?

SUS is a **config-driven web scraper** designed for converting documentation websites to Markdown format with preserved assets. Control crawling behavior through YAML configuration files with regex/glob/prefix pattern matching, token bucket rate limiting, and dual-level concurrency controls.

**Key capabilities:**
- **25-50 pages/sec throughput** with HTTP/2 and connection pooling
- **Checkpoint/Resume** for incremental scraping and crash recovery
- **JavaScript rendering** via Playwright for SPA sites
- **Authentication** with 4 providers (Basic, Cookie, Header, OAuth2)
- **Plugin system** with 5 lifecycle hooks and 3 built-in plugins
- **Type-safe** with Pydantic 2.9+ validation and mypy --strict compliance

---

## Installation

```bash
# Using uv (recommended)
uv pip install sus

# Using pip
pip install sus

# Verify installation
sus --version
```

**Requirements:** Python 3.12+

---

## Minimal Example

```yaml
name: my-docs

site:
  start_urls:
    - https://docs.example.com/
  allowed_domains:
    - docs.example.com
```

```bash
sus scrape --config config.yaml
```

See the [Getting Started Guide](getting-started.md) for a complete tutorial.

---

## License

This project is currently unlicensed. Please contact the maintainer for licensing information.
