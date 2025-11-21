# Example Configurations

This directory contains example configuration files demonstrating various SUS features with **real, working target sites**. All configs are immediately runnable and testable.

## Quick Start

Run any example with:

```bash
uv run sus scrape --config examples/<config-name>.yaml
```

Limit pages for testing:

```bash
uv run sus scrape --config examples/<config-name>.yaml --max-pages 10
```

---

## Available Examples

### Getting Started

#### `simple-docs.yaml` - **Flask Documentation**
Minimal configuration showing only required fields with clean, straightforward docs.

**Target:** https://flask.palletsprojects.com/en/stable/
**Use case:** Learning SUS basics, small documentation sites
**Pages:** ~50 pages (limited)

**Run:**
```bash
uv run sus scrape --config examples/simple-docs.yaml
```

#### `advanced-docs.yaml` - **Django Documentation**
Comprehensive configuration showcasing all available features with large, complex docs.

**Target:** https://docs.djangoproject.com/en/stable/
**Use case:** Large documentation sites requiring fine-tuned control
**Pages:** ~200 pages (limited), ~500 full
**Features:** Regex patterns, version filtering, Sphinx artifact exclusion

**Run:**
```bash
uv run sus scrape --config examples/advanced-docs.yaml
```

---

### Real Documentation Sites

These configs target real, production documentation sites for testing and actual use.

#### `aptly.yaml` - **Aptly Package Manager**
Aptly package management documentation scraper (original flagship example).

**Target:** https://www.aptly.info/doc/
**Pages:** ~85 pages

**Run:**
```bash
uv run sus scrape --config examples/aptly.yaml
```

#### `bottle.yaml` - **Bottle Web Framework**
Bottle.py micro-framework documentation scraper.

**Target:** https://bottlepy.org/
**Pages:** ~15-20 pages (good for quick testing)

**Run:**
```bash
uv run sus scrape --config examples/bottle.yaml
```

#### `htmx.yaml` - **HTMX Library**
HTMX library documentation with selective section scraping.

**Target:** https://htmx.org/
**Pages:** ~30-50 pages

**Run:**
```bash
uv run sus scrape --config examples/htmx.yaml
```

#### `peewee.yaml` - **Peewee ORM**
Peewee ORM documentation scraper (large site for performance testing).

**Target:** https://docs.peewee-orm.com/
**Pages:** ~60-100 pages

**Run:**
```bash
uv run sus scrape --config examples/peewee.yaml
```

#### `requests.yaml` - **Python Requests Library**
Requests library documentation scraper (ReadTheDocs site).

**Target:** https://docs.python-requests.org/
**Pages:** ~50-80 pages

**Run:**
```bash
uv run sus scrape --config examples/requests.yaml
```

---

### Feature Demonstrations

#### `content-filtering-example.yaml` - **Content Filtering**
Demonstrates CSS selector-based filtering to extract only relevant content.

**Target:** https://docs.python-requests.org/en/latest/ (ReadTheDocs site)
**Use case:** Sites with noisy layout (navigation, ads, footers)
**Features:** `keep_selectors` (whitelist) and `remove_selectors` (blacklist) strategies

**Run:**
```bash
uv run sus scrape --config examples/content-filtering-example.yaml
```

**Key config:**
```yaml
markdown:
  content_filtering:
    enabled: true
    keep_selectors:
      - div[role="main"]  # Extract only main content
```

#### `sitemap-docs.yaml` - **Sitemap.xml Parsing**
Demonstrates sitemap.xml parsing with auto-discovery feature.

**Target:** https://flask.palletsprojects.com/ (has sitemap.xml)
**Use case:** Sites with comprehensive sitemaps, priority-based crawling
**Features:** Auto-discovery from robots.txt, priority sorting, strict/non-strict modes

**Run:**
```bash
uv run sus scrape --config examples/sitemap-docs.yaml
```

**Key config:**
```yaml
crawling:
  sitemap:
    enabled: true
    auto_discover: true
    respect_priority: true
```

#### `pipeline-example.yaml` - **Pipeline Mode**
Demonstrates producer-consumer pipeline for 3-10x throughput improvement.

**Target:** https://docs.djangoproject.com/en/stable/ (large site)
**Use case:** Large sites benefiting from parallel processing
**Features:** Process workers, queue management, memory-based backpressure

**Run:**
```bash
uv run sus scrape --config examples/pipeline-example.yaml
```

**Key config:**
```yaml
crawling:
  pipeline:
    enabled: true
    process_workers: 10
    queue_maxsize: 100
    max_queue_memory_mb: 500
```

---

### JavaScript Rendering (SPAs)

#### `spa-docs.yaml` 🌟 - **Vue.js Documentation**

Example configuration for scraping Single Page Applications (SPAs) and JavaScript-heavy sites.

**Target:** https://vuejs.org/ (Vue.js SPA documentation)
**Use case:**
- React, Vue, Angular, or similar framework documentation
- Sites that load content dynamically via JavaScript
- Documentation with client-side routing
- Content that requires network requests to appear

**Requires:** Playwright installation
```bash
# Install JavaScript rendering dependencies
uv sync --group js

# Install Chromium browser
uv run playwright install chromium
```

**Run:**
```bash
uv run sus scrape --config examples/spa-docs.yaml
```

**Key features:**
- Browser-based JavaScript rendering with Playwright
- Context pooling for performance (reuse browser contexts)
- Configurable wait strategies (domcontentloaded, load, networkidle)
- Lower concurrency optimized for browser rendering
- Custom viewport and user agent support

**Performance:**
- ~3-5x slower than HTTP-only crawling (with context pooling)
- Higher memory usage (~500MB for browser instances)
- Significantly faster with context pooling vs naive approach

**Key config:**
```yaml
crawling:
  javascript:
    enabled: true
    wait_for: networkidle        # or "domcontentloaded", "load"
    context_pool_size: 5         # Reuse browser contexts
```

**See also:**
- [JavaScript Rendering Guide](../docs/guides/javascript-rendering.md) - Complete documentation
- [Benchmark Script](../benchmarks/benchmark_js_rendering.py) - Performance measurement

---

### Plugin System

#### `plugins-code-highlight.yaml` - **Code Syntax Highlighting**
Example using Pygments for syntax-highlighted code blocks.

**Target:** https://docs.python.org/3/tutorial/ (Python tutorial with code blocks)
**Features:** Pygments themes, line numbers, inline styles

**Requires:** Plugin dependencies
```bash
uv sync --group plugins
uv run sus scrape --config examples/plugins-code-highlight.yaml
```

**Key config:**
```yaml
plugins:
  enabled: true
  plugins:
    - "sus.plugins.code_highlight"
  plugin_settings:
    "sus.plugins.code_highlight":
      theme: "monokai"
      add_line_numbers: false
```

#### `plugins-all.yaml` - **All Built-in Plugins**
Demonstrates all three built-in plugins together (code highlighting, link validation, image optimization).

**Target:** https://flask.palletsprojects.com/en/stable/ (Flask documentation)
**Features:** Code highlighting, link validation (internal/external), image optimization

**Requires:** Plugin dependencies
```bash
uv sync --group plugins
uv run sus scrape --config examples/plugins-all.yaml
```

**Plugins included:**
1. **Code Highlighting** - Pygments syntax highlighting
2. **Link Validator** - Validate internal and external links, mark broken links
3. **Image Optimizer** - Resize and compress images to reduce file size

---

### Authentication Examples

These examples demonstrate various authentication methods for protected resources.

#### `auth-basic-example.yaml` - **HTTP Basic Authentication**
HTTP Basic Auth using public test endpoint.

**Target:** https://httpbin.org/basic-auth/testuser/testpass
**Use case:** Sites/APIs requiring HTTP Basic Auth
**Credentials:** Public test credentials (testuser/testpass)

**Run:**
```bash
uv run sus scrape --config examples/auth-basic-example.yaml --dry-run
```

**Key config:**
```yaml
crawling:
  authentication:
    enabled: true
    auth_type: basic
    username: testuser
    password: testpass
```

#### `auth-cookie-example.yaml` - **Session Cookie Authentication**
Session cookie authentication template (instructional).

**Target:** Template for your own sites (no public test available)
**Use case:** Sites requiring session cookies after login
**Instructions:** Detailed steps for obtaining cookies from browser dev tools

**Key config:**
```yaml
crawling:
  authentication:
    enabled: true
    auth_type: cookie
    cookies:
      sessionid: "YOUR_SESSION_ID_HERE"
      csrftoken: "YOUR_CSRF_TOKEN_HERE"
```

#### `auth-header-example.yaml` - **API Key / Custom Headers**
API key and custom header authentication.

**Target:** https://reqres.in/api/users (ReqRes.in free fake API)
**Use case:** APIs requiring API keys or custom headers
**Features:** Demonstrates X-API-Key and Authorization header patterns

**Run:**
```bash
uv run sus scrape --config examples/auth-header-example.yaml --dry-run
```

**Key config:**
```yaml
crawling:
  authentication:
    enabled: true
    auth_type: header
    headers:
      X-API-Key: "demo-api-key"
      # Authorization: "Bearer your-token-here"
```

#### `auth-oauth2-example.yaml` - **OAuth 2.0 (Bearer Token)**
OAuth2-style Bearer token authentication.

**Target:** https://gorest.co.in/public/v2/users (GoRest API)
**Use case:** APIs using OAuth2 Bearer tokens
**Features:** Instructions for obtaining free GoRest token, OAuth2 flow documentation

**Setup:**
1. Visit https://gorest.co.in/
2. Click "Access Token" → Sign in with Google/GitHub
3. Copy token and update config

**Run:**
```bash
uv run sus scrape --config examples/auth-oauth2-example.yaml --dry-run
```

**Key config:**
```yaml
crawling:
  authentication:
    enabled: true
    auth_type: header  # GoRest uses Bearer tokens
    headers:
      Authorization: "Bearer YOUR_GOREST_TOKEN_HERE"
```

**Note:** For true OAuth2 Client Credentials flow, see commented example in config.

---

## Configuration Guide

All examples follow the same structure:

```yaml
name: config-name
description: What this configuration does

site:
  start_urls: [...]
  allowed_domains: [...]

crawling:
  include_patterns: [...]
  exclude_patterns: [...]
  # ... other crawling options

output:
  base_dir: output
  docs_dir: docs
  assets_dir: assets

assets:
  download: true
  types: [...]
```

### Common Customizations

#### Limit pages for testing
```yaml
crawling:
  max_pages: 10  # Only scrape 10 pages
```

#### Adjust rate limiting
```yaml
crawling:
  delay_between_requests: 1.0  # Wait 1 second between requests
  rate_limiter_burst_size: 5   # Allow bursts of 5 requests
```

#### Change output directory
```yaml
output:
  base_dir: /path/to/output
  site_dir: my-site-name
```

#### Pattern matching
```yaml
crawling:
  include_patterns:
    - pattern: "/docs/"    # Prefix matching
      type: prefix
    - pattern: "*.html"    # Glob matching
      type: glob
    - pattern: "^/api/"    # Regex matching
      type: regex

  exclude_patterns:
    - pattern: "*.pdf"     # Exclude PDFs
      type: glob
```

---

## Creating Custom Configurations

1. Copy an existing example:
   ```bash
   cp examples/simple-docs.yaml my-config.yaml
   ```

2. Edit the configuration:
   - Update `name` and `description`
   - Set `start_urls` and `allowed_domains` to your target site
   - Customize `include_patterns` and `exclude_patterns`
   - Adjust concurrency and rate limiting
   - Enable JavaScript rendering if needed
   - Configure authentication if site requires it

3. Validate the configuration:
   ```bash
   uv run sus validate my-config.yaml
   ```

4. Test with limited pages:
   ```bash
   uv run sus scrape --config my-config.yaml --max-pages 5 --verbose
   ```

5. Run full scrape:
   ```bash
   uv run sus scrape --config my-config.yaml
   ```

---

## Example Summary Table

| Config | Target Site | Purpose | Pages | Special Features |
|--------|------------|---------|-------|-----------------|
| `simple-docs.yaml` | Flask docs | Getting started | ~50 | Minimal config |
| `advanced-docs.yaml` | Django docs | Advanced features | ~200 | Regex patterns, filtering |
| `aptly.yaml` | Aptly | Real docs scraping | ~85 | Flagship example |
| `bottle.yaml` | Bottle.py | Quick testing | ~20 | Small site |
| `htmx.yaml` | HTMX | Section filtering | ~40 | Pattern matching |
| `peewee.yaml` | Peewee ORM | Performance testing | ~80 | Large site |
| `requests.yaml` | Requests lib | ReadTheDocs pattern | ~60 | Sphinx artifacts |
| `content-filtering-example.yaml` | Requests docs | Content filtering | ~100 | CSS selectors |
| `sitemap-docs.yaml` | Flask (sitemap) | Sitemap parsing | ~50 | Auto-discovery |
| `pipeline-example.yaml` | Django | Pipeline mode | ~300 | Parallel processing |
| `spa-docs.yaml` | Vue.js | JavaScript rendering | ~100 | Playwright, SPAs |
| `plugins-code-highlight.yaml` | Python tutorial | Code highlighting | ~20 | Pygments |
| `plugins-all.yaml` | Flask | All plugins | ~100 | 3 plugins |
| `auth-basic-example.yaml` | httpbin.org | Basic Auth | ~10 | Public test endpoint |
| `auth-cookie-example.yaml` | Template | Cookie auth | N/A | Instructional |
| `auth-header-example.yaml` | ReqRes API | API keys | ~10 | Header auth |
| `auth-oauth2-example.yaml` | GoRest API | OAuth2/Bearer | ~20 | Token auth |

---

## Tips

- **Start small**: Test with `--max-pages 10` before full scrape
- **Use dry-run**: Preview without writing files with `--dry-run`
- **Check patterns**: Use `sus validate` to check your configuration
- **Monitor memory**: Watch memory usage with large scrapes
- **Respect sites**: Use appropriate delays and limits (especially public test APIs)
- **JavaScript**: Only enable if content requires it (3-5x slower)
- **Auth credentials**: Never commit real credentials to version control
- **Public APIs**: Be respectful with rate limits on test services (httpbin, reqres, gorest)

---

## Further Reading

- [Configuration Reference](../docs/configuration.md) - Full config options
- [JavaScript Rendering Guide](../docs/guides/javascript-rendering.md) - Detailed JS rendering docs
- [Contributing Guide](../CONTRIBUTING.md) - Add your own examples
- [Main Documentation](../docs/) - Complete SUS documentation
