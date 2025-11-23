# Getting Started

This guide walks you through installing SUS and running your first scrape.

---

## Installation

### Prerequisites

- **Python 3.12 or later**
- **uv** (recommended) or pip

### Install SUS

**Using uv (recommended):**

```bash
uv pip install sus
```

**Using pip:**

```bash
pip install sus
```

**Verify installation:**

```bash
sus --version
```

### Optional Dependencies

**JavaScript rendering (for SPA sites):**

```bash
# With uv
uv pip install sus[js]

# With pip
pip install sus[js]

# Install Playwright browsers
playwright install chromium
```

**Plugin dependencies (code highlighting, image optimization):**

```bash
# With uv
uv pip install sus[plugins]

# With pip
pip install sus[plugins]
```

**Development tools:**

```bash
# Clone repository
git clone https://github.com/UtsavBalar1231/sus.git
cd sus

# Install with dev dependencies
uv sync --group dev
```

---

## Your First Scrape

Let's scrape a simple documentation site to see SUS in action.

### Step 1: Create a Configuration File

Create a file named `quickstart.yaml`:

```yaml
name: quickstart-example

site:
  start_urls:
    - https://docs.python.org/3/tutorial/
  allowed_domains:
    - docs.python.org

output:
  base_dir: ./output

crawling:
  max_pages: 10
  delay_between_requests: 0.2  # 5 requests/sec
  global_concurrent_requests: 10
```

**What this config does:**
- `name`: Project identifier
- `start_urls`: Where to begin crawling
- `allowed_domains`: Only crawl URLs from these domains
- `max_pages`: Limit to 10 pages (for testing)
- `delay_between_requests`: 0.2 seconds between requests (5 requests/sec)
- `global_concurrent_requests`: Up to 10 concurrent connections

### Step 2: Validate the Configuration

Check that your config is valid:

```bash
sus validate quickstart.yaml
```

Expected output:

```
✓ Configuration is valid
```

### Step 3: Run the Scraper

Start scraping:

```bash
sus scrape --config quickstart.yaml
```

You'll see real-time progress:

```
Crawling: 10 pages | 45.2 pages/s | 125KB | 0 errors
Converting: 8/10 pages | 2 pending | 0 errors
Assets: 15 downloaded | 234KB | 0 errors
```

### Step 4: Examine the Output

After completion, check the output directory:

```bash
ls -lh output/
```

You'll find:

```
output/
├── docs/                   # Converted Markdown files (default directory)
│   ├── index.md
│   ├── tutorial-introduction.md
│   └── ...
├── assets/                 # Downloaded images, CSS, JS
│   ├── python-logo.png
│   └── ...
└── checkpoint.json         # Resume state (if checkpoint enabled)
```

---

## Understanding the Output

### Markdown Files

Each HTML page becomes a Markdown file in `output/docs/`:

**Example: `output/docs/tutorial-introduction.md`**

```markdown
---
title: "An Informal Introduction to Python"
source_url: "https://docs.python.org/3/tutorial/introduction.html"
scraped_at: "2025-01-23T10:30:45Z"
---

# An Informal Introduction to Python

In the following examples, input and output are distinguished
by the presence or absence of prompts...
```

**Frontmatter fields:**
- `title`: Page title (from `<title>` tag)
- `source_url`: Original URL
- `scraped_at`: Timestamp (ISO 8601)

### Assets Directory

Downloaded assets are organized by type:

```
output/assets/
├── images/
│   ├── python-logo.png
│   └── diagram.svg
├── css/
│   └── styles.css
└── js/
    └── highlight.js
```

**Asset handling:**
- SHA-256 deduplication (identical files downloaded once)
- References in Markdown updated to relative paths
- Preserves directory structure when possible

### Checkpoint File

If checkpointing is enabled, `checkpoint.json` stores crawl state:

```json
{
  "config_hash": "a1b2c3...",
  "last_run": "2025-01-23T10:35:12Z",
  "pages_scraped": 10,
  "pages": {
    "https://example.com/page1": {
      "status": "completed",
      "content_hash": "d4e5f6...",
      "last_scraped": "2025-01-23T10:30:45Z"
    }
  }
}
```

Use checkpoints to resume interrupted crawls:

```bash
# Resume from checkpoint
sus scrape --config quickstart.yaml --resume

# Start fresh (delete checkpoint)
sus scrape --config quickstart.yaml --reset-checkpoint
```

---

## Next Steps

### Customize Your Scrape

Explore the full configuration options:

- **[Configuration Reference](configuration.md)** - Complete YAML schema documentation
- **[Examples](examples.md)** - Real-world configurations for various sites

### Common Tasks

**Scrape with authentication:**

```yaml
crawling:
  authentication:
    enabled: true
    auth_type: basic
    username: user
    password: pass
```

See [Configuration Reference → Authentication](configuration.md#authentication).

**Enable JavaScript rendering:**

```yaml
crawling:
  javascript:
    enabled: true
    wait_for: networkidle
```

See [Configuration Reference → JavaScript Rendering](configuration.md#javascript-rendering).

**Use checkpoint/resume:**

```yaml
crawling:
  checkpoint:
    enabled: true
    backend: json  # or 'sqlite' for large sites
```

See [Configuration Reference → Checkpoint/Resume](configuration.md#checkpointresume).

### Advanced Features

**Filter URLs with patterns:**

```yaml
crawling:
  include_patterns:
    - pattern: "^/docs/"
      type: regex
  exclude_patterns:
    - pattern: "*.pdf"
      type: glob
```

**Enable plugins:**

```yaml
plugins:
  enabled: true
  plugins:
    - sus.plugins.code_highlight
    - sus.plugins.image_optimizer
  plugin_settings:
    sus.plugins.image_optimizer:
      max_width: 1200
```

**Use pipeline mode for 3-10x speedup:**

```yaml
crawling:
  pipeline:
    enabled: true
    process_workers: 4
    queue_maxsize: 1000
```

See the [Configuration Reference](configuration.md) for complete documentation.

---

## CLI Quick Reference

```bash
# Scrape with config
sus scrape --config FILE

# Common options
sus scrape --config FILE \
  --output DIR \           # Override output directory
  --max-pages N \          # Limit page count
  --verbose \              # Enable debug logging
  --dry-run \              # Simulate without writing
  --preview \              # Export dry-run JSON report
  --resume \               # Resume from checkpoint
  --reset-checkpoint \     # Delete checkpoint
  --clear-cache            # Clear HTTP cache

# Validate config
sus validate FILE

# Interactive config wizard
sus init [OUTPUT] [--force]

# List example configs
sus list
```

---

## Troubleshooting

**"Configuration is invalid" error:**

Run `sus validate FILE` to see specific validation errors. Common issues:
- Missing required fields (`name`, `start_urls`)
- Invalid URL format
- Type mismatches (e.g., string instead of number)

**"Rate limit exceeded" errors:**

Adjust `delay_between_requests` or reduce `global_concurrent_requests`:

```yaml
crawling:
  delay_between_requests: 0.5  # 2 requests/sec
  global_concurrent_requests: 5    # Fewer concurrent connections
```

**Empty or incomplete output:**

Check the URL filtering rules. You may be excluding pages unintentionally:

```bash
sus scrape --config FILE --verbose
```

Look for "Filtered by rules" messages in the logs.

**JavaScript content not rendering:**

Ensure you've installed Playwright and browsers:

```bash
uv pip install sus[js]
playwright install chromium
```

Enable JavaScript in your config:

```yaml
javascript:
  enabled: true
  wait_strategy: networkidle  # Wait for network idle
```

---

## Getting Help

- **[Configuration Reference](configuration.md)** - Complete YAML documentation
- **[Examples](examples.md)** - Real-world configurations
- **[API Reference](api/overview.md)** - Python API documentation
- **[GitHub Issues](https://github.com/UtsavBalar1231/sus/issues)** - Report bugs or request features

---

**Ready to scrape?** Check out the [Configuration Reference](configuration.md) to customize your scraping workflow.
