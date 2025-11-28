# API Reference

Complete API documentation auto-generated from source code docstrings.

All modules are fully typed with mypy --strict compliance and Google-style docstring documentation.

## Core Modules

### Configuration Layer

- **[config](config.md)** - Configuration system with Pydantic models and YAML loading
- **[exceptions](exceptions.md)** - Custom exception hierarchy

### Crawling & URL Handling Layer

- **[crawler](crawler.md)** - Async web crawler with rate limiting and concurrency control
- **[rules](rules.md)** - URL filtering, normalization, and link extraction

### Content Processing Layer

- **[converter](converter.md)** - HTML to Markdown conversion with frontmatter
- **[outputs](outputs.md)** - File path mapping and link rewriting
- **[assets](assets.md)** - Concurrent asset downloading

### Orchestration Layer

- **[scraper](scraper.md)** - Main pipeline orchestrator
- **[cli](cli.md)** - Typer-based command-line interface

### Utilities

- **[utils](utils.md)** - Shared utility functions

## Usage Patterns

All modules follow consistent patterns:

1. **Type Safety**: Full type hints with mypy --strict compliance
2. **Async Support**: Async/await patterns using httpx and asyncio
3. **Documentation**: Google-style docstrings with examples and type annotations
4. **Pydantic Validation**: Configuration validated with Pydantic error messages

## Getting Started with the API

For most use cases, you'll interact with:

1. **[config.load_config()](config.md#sus.config.load_config)** - Load YAML configuration
2. **[Crawler](crawler.md#sus.crawler.Crawler)** - Async web crawler
3. **[run_scraper()](scraper.md#sus.scraper.run_scraper)** - Main orchestration function

## Architecture Overview

SUS implements a six-stage pipeline architecture:

1. **Configuration System** (`config.py`) - Pydantic 2.9+ models with YAML validation
2. **Crawler Engine** (`crawler.py`) - httpx async client with token bucket rate limiter
3. **URL Filtering** (`rules.py`) - lxml-based link extraction with pattern matching
4. **Content Conversion** (`converter.py`) - html-to-markdown (Rust-powered) with frontmatter
5. **CLI Interface** (`cli.py`) - Typer commands with Rich progress bars
6. **Testing** (`tests/`) - 139+ pytest tests with mypy --strict compliance

See individual module documentation for detailed API references.
