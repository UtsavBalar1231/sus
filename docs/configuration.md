# Configuration Reference

Complete YAML configuration schema for SUS. All settings with descriptions, types, defaults, and examples.

---

## Minimal Configuration

The absolute minimum configuration requires only `name` and `site`:

```yaml
name: my-docs

site:
  start_urls:
    - https://example.com/docs/
  allowed_domains:
    - example.com
```

All other settings have sensible defaults.

---

## Complete Configuration Example

```yaml
name: full-example
description: "Comprehensive configuration example"

site:
  start_urls:
    - https://docs.example.com/
  allowed_domains:
    - docs.example.com

crawling:
  max_pages: 1000
  depth_limit: 5
  delay_between_requests: 0.5
  global_concurrent_requests: 25
  per_domain_concurrent_requests: 5

  include_patterns:
    - pattern: "^/docs/"
      type: regex
  exclude_patterns:
    - pattern: "*.pdf"
      type: glob

  sitemap:
    enabled: true
    auto_discover: true

  javascript:
    enabled: false

  checkpoint:
    enabled: true
    backend: json
    checkpoint_interval_pages: 10

  authentication:
    enabled: false

  pipeline:
    enabled: false

  cache:
    enabled: false

output:
  base_dir: output
  docs_dir: pages
  assets_dir: assets

  markdown:
    add_frontmatter: true
    frontmatter_fields: ["title", "url", "scraped_at"]

    content_filtering:
      enabled: false

assets:
  download: true
  types: ["image", "css", "javascript"]
  rewrite_paths: true
  max_concurrent_asset_downloads: 10

plugins:
  enabled: false
  plugins: []
```

---

## Configuration Sections

## Basic Settings

### `name` (required)

Project identifier used as default output directory name.

**Type:** `string` (min length: 1)
**Example:**

```yaml
name: python-docs
```

**Validation:**
- Must not contain path separators (`/`, `\`)
- Must not contain special characters (`:`, `*`, `?`, `"`, `<`, `>`, `|`)
- Cannot be `.` or `..`
- No leading/trailing whitespace

---

### `description`

Human-readable description of this configuration.

**Type:** `string`
**Default:** `""`
**Example:**

```yaml
description: "Python 3.12 documentation scraper for offline access"
```

---

## Site Configuration

### `site.start_urls` (required)

List of URLs where crawling begins.

**Type:** `list[string]` (min length: 1)
**Example:**

```yaml
site:
  start_urls:
    - https://docs.python.org/3/
    - https://docs.python.org/3/library/
```

---

### `site.allowed_domains` (required)

Domains allowed for crawling. URLs from other domains are ignored.

**Type:** `list[string]` (min length: 1)
**Example:**

```yaml
site:
  allowed_domains:
    - docs.python.org
    - www.python.org  # Allow www subdomain too
```

---

## Crawling Configuration

### `crawling.max_pages`

Maximum number of pages to crawl.

**Type:** `int | null` (≥1)
**Default:** `null` (unlimited)
**Example:**

```yaml
crawling:
  max_pages: 500
```

---

### `crawling.depth_limit`

Maximum crawl depth from start URLs (0 = start URLs only).

**Type:** `int | null` (≥0)
**Default:** `null` (unlimited)
**Example:**

```yaml
crawling:
  depth_limit: 3  # Start URLs (depth 0) + 3 levels deep
```

---

### `crawling.delay_between_requests`

Delay between requests in seconds (applies per domain).

**Type:** `float` (≥0.0)
**Default:** `0.5`
**Example:**

```yaml
crawling:
  delay_between_requests: 1.0  # More conservative
```

---

### `crawling.global_concurrent_requests`

Maximum concurrent requests across all domains.

**Type:** `int` (≥1)
**Default:** `25`
**Example:**

```yaml
crawling:
  global_concurrent_requests: 50  # Faster scraping
```

---

### `crawling.per_domain_concurrent_requests`

Maximum concurrent requests per domain.

**Type:** `int` (≥1)
**Default:** `5`
**Example:**

```yaml
crawling:
  per_domain_concurrent_requests: 10  # HTTP/2 can handle more
```

---

### `crawling.rate_limiter_burst_size`

Token bucket burst size for rate limiting.

**Type:** `int` (≥1)
**Default:** `10`
**Example:**

```yaml
crawling:
  rate_limiter_burst_size: 20  # Allow larger bursts
```

---

### `crawling.max_retries`

Maximum retries for failed requests.

**Type:** `int` (≥0)
**Default:** `3`
**Example:**

```yaml
crawling:
  max_retries: 5  # More resilient to transient failures
```

---

### `crawling.retry_backoff`

Exponential backoff multiplier for retries.

**Type:** `float` (≥1.0)
**Default:** `2.0`
**Example:**

```yaml
crawling:
  retry_backoff: 1.5  # Gentler backoff (1.5^n seconds)
```

---

### `crawling.retry_jitter`

Jitter for retry backoff (prevents thundering herd).

**Type:** `float` (0.0-1.0)
**Default:** `0.3`
**Example:**

```yaml
crawling:
  retry_jitter: 0.5  # More randomization
```

---

### `crawling.respect_robots_txt`

Whether to respect robots.txt rules.

**Type:** `bool`
**Default:** `true`
**Example:**

```yaml
crawling:
  respect_robots_txt: false  # Ignore robots.txt (use carefully!)
```

---

### `crawling.max_page_size_mb`

Maximum page size in MB (prevents downloading huge files).

**Type:** `float | null` (≥0.1)
**Default:** `10.0`
**Example:**

```yaml
crawling:
  max_page_size_mb: 25.0  # Allow larger pages
```

---

### `crawling.max_asset_size_mb`

Maximum asset size in MB (prevents downloading huge images/videos).

**Type:** `float | null` (≥0.1)
**Default:** `50.0`
**Example:**

```yaml
crawling:
  max_asset_size_mb: 100.0  # Allow larger assets
```

---

### `crawling.max_redirects`

Maximum redirects to follow per request.

**Type:** `int` (0-20)
**Default:** `10`
**Example:**

```yaml
crawling:
  max_redirects: 5  # Fewer redirects allowed
```

---

### `crawling.memory_check_interval`

Check memory usage every N pages to prevent out-of-memory errors.

**Type:** `int` (≥1)
**Default:** `1`
**Example:**

```yaml
crawling:
  memory_check_interval: 10  # Check every 10 pages (reduces overhead)
```

**Note:** Setting this higher (e.g., 10-50) reduces performance overhead for sites with small pages, but may delay OOM detection.

---

## URL Filtering

### `crawling.include_patterns`

Whitelist of URL patterns to crawl.

**Type:** `list[PathPattern]`
**Default:** `[]` (include all)
**Example:**

```yaml
crawling:
  include_patterns:
    # Regex: Only /docs/ and /api/ paths
    - pattern: "^/(docs|api)/"
      type: regex

    # Glob: Only HTML files
    - pattern: "*.html"
      type: glob

    # Prefix: Only paths starting with /guide/
    - pattern: "/guide/"
      type: prefix
```

---

### `crawling.exclude_patterns`

Blacklist of URL patterns to skip.

**Type:** `list[PathPattern]`
**Default:** `[]` (exclude none)
**Example:**

```yaml
crawling:
  exclude_patterns:
    # Exclude PDFs
    - pattern: "*.pdf"
      type: glob

    # Exclude legacy docs
    - pattern: "^/legacy/"
      type: regex

    # Exclude search pages
    - pattern: "/search"
      type: prefix
```

---

### `crawling.link_selectors`

CSS selectors for extracting links from HTML.

**Type:** `list[string]`
**Default:** `["a[href]"]`
**Example:**

```yaml
crawling:
  link_selectors:
    - "a[href]"           # Standard links
    - "area[href]"        # Image maps
    - "link[rel='next']"  # Pagination
```

---

## Authentication

### `crawling.authentication.enabled`

Enable authentication for protected content.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
crawling:
  authentication:
    enabled: true
    auth_type: basic
```

---

### `crawling.authentication.auth_type`

Authentication method (required if `enabled: true`).

**Type:** `"basic" | "cookie" | "header" | "oauth2" | null`
**Default:** `null`
**Options:**
- `basic` - HTTP Basic Authentication
- `cookie` - Cookie-based session auth
- `header` - Custom header auth (API keys, tokens)
- `oauth2` - OAuth 2.0 Client Credentials flow

---

### Basic Authentication

```yaml
crawling:
  authentication:
    enabled: true
    auth_type: basic
    username: myuser
    password: mypass  # ⚠️ Use environment variables in production!
```

**Fields:**
- `username` (string, required)
- `password` (string, required)

---

### Cookie Authentication

```yaml
crawling:
  authentication:
    enabled: true
    auth_type: cookie
    cookies:
      session_id: abc123xyz
      auth_token: def456uvw
```

**Fields:**
- `cookies` (dict[string, string], required) - Session cookies

---

### Header Authentication

```yaml
crawling:
  authentication:
    enabled: true
    auth_type: header
    headers:
      X-API-Key: secret-api-key
      Authorization: Bearer token123
```

**Fields:**
- `headers` (dict[string, string], required) - Custom headers

---

### OAuth2 Authentication

```yaml
crawling:
  authentication:
    enabled: true
    auth_type: oauth2
    client_id: my-client-id
    client_secret: my-client-secret  # ⚠️ Use environment variables!
    token_url: https://auth.example.com/oauth/token
    scope: read:docs  # Optional
```

**Fields:**
- `client_id` (string, required)
- `client_secret` (string, required)
- `token_url` (string, required)
- `scope` (string, optional)

---

## Checkpoint/Resume

### `crawling.checkpoint.enabled`

Enable incremental scraping with checkpoint/resume.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
crawling:
  checkpoint:
    enabled: true
```

---

### `crawling.checkpoint.backend`

Checkpoint storage backend.

**Type:** `"json" | "sqlite"`
**Default:** `"json"`
**Recommendations:**
- `json` - For <10K pages (human-readable, simple)
- `sqlite` - For >10K pages (indexed, fast, 10ms load time)

**Example:**

```yaml
crawling:
  checkpoint:
    enabled: true
    backend: sqlite  # Better for large sites
```

---

### `crawling.checkpoint.checkpoint_file`

Checkpoint filename (relative to output directory).

**Type:** `string`
**Default:** `".sus_checkpoint.json"`
**Example:**

```yaml
crawling:
  checkpoint:
    checkpoint_file: checkpoint.db  # SQLite backend
```

---

### `crawling.checkpoint.checkpoint_interval_pages`

Save checkpoint every N pages.

**Type:** `int` (≥1)
**Default:** `10`
**Example:**

```yaml
crawling:
  checkpoint:
    checkpoint_interval_pages: 50  # Less frequent saves
```

---

### `crawling.checkpoint.detect_changes`

Detect content changes via SHA-256 hashing (skip unchanged pages on resume).

**Type:** `bool`
**Default:** `true`
**Example:**

```yaml
crawling:
  checkpoint:
    detect_changes: false  # Always re-download
```

---

### `crawling.checkpoint.force_redownload_after_days`

Force redownload if page older than N days.

**Type:** `int | null` (≥1)
**Default:** `7`
**Example:**

```yaml
crawling:
  checkpoint:
    force_redownload_after_days: 30  # Monthly refresh
```

---

## JavaScript Rendering

Requires optional dependency: `uv pip install sus[js] && playwright install chromium`

### `crawling.javascript.enabled`

Enable JavaScript rendering with Playwright browser.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
crawling:
  javascript:
    enabled: true
```

---

### `crawling.javascript.javascript_enabled`

Enable/disable JavaScript execution in the browser (for debugging).

**Type:** `bool`
**Default:** `true`
**Example:**

```yaml
crawling:
  javascript:
    enabled: true
    javascript_enabled: false  # Disable JS for debugging rendering issues
```

**Note:** This is different from `enabled`. When `enabled: true`, the browser is used. When `javascript_enabled: false`, the browser loads pages but doesn't execute JavaScript.

---

### `crawling.javascript.wait_for`

Wait strategy for page load.

**Type:** `"domcontentloaded" | "load" | "networkidle"`
**Default:** `"networkidle"`
**Options:**
- `domcontentloaded` - Fast (DOM ready, images may not load)
- `load` - Medium (all resources including images)
- `networkidle` - Slow (no network activity for 500ms)

**Example:**

```yaml
crawling:
  javascript:
    wait_for: load  # Balanced speed/completeness
```

---

### `crawling.javascript.wait_timeout_ms`

Maximum wait time for page load in milliseconds.

**Type:** `int` (1000-120000)
**Default:** `30000`
**Example:**

```yaml
crawling:
  javascript:
    wait_timeout_ms: 60000  # 60 seconds for slow pages
```

---

### `crawling.javascript.user_agent_override`

Custom user agent string for browser requests.

**Type:** `string | null`
**Default:** `null` (uses Playwright default)
**Example:**

```yaml
crawling:
  javascript:
    user_agent_override: "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
```

**Use cases:**
- Testing mobile layouts
- Bypassing basic bot detection
- Simulating specific browsers

---

### `crawling.javascript.viewport_width` / `viewport_height`

Browser viewport dimensions in pixels.

**Type:** `int`
**Default:** `1920` × `1080`
**Range:** Width: 320-3840, Height: 240-2160
**Example:**

```yaml
crawling:
  javascript:
    viewport_width: 1280
    viewport_height: 720  # Smaller viewport
```

---

### `crawling.javascript.context_pool_size`

Number of browser contexts to pool (reduces overhead 3-5x).

**Type:** `int` (1-20)
**Default:** `5`
**Example:**

```yaml
crawling:
  javascript:
    context_pool_size: 10  # More contexts for higher concurrency
```

---

## Sitemap Parsing

### `crawling.sitemap.enabled`

Parse sitemap.xml files for fast URL discovery.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
crawling:
  sitemap:
    enabled: true
```

---

### `crawling.sitemap.auto_discover`

Auto-discover sitemaps from robots.txt and `/sitemap.xml`.

**Type:** `bool`
**Default:** `true`
**Example:**

```yaml
crawling:
  sitemap:
    auto_discover: true
```

---

### `crawling.sitemap.urls`

Explicit sitemap URLs to parse (in addition to auto-discovery).

**Type:** `list[string]`
**Default:** `[]`
**Example:**

```yaml
crawling:
  sitemap:
    urls:
      - https://example.com/sitemap.xml
      - https://example.com/sitemap-pages.xml
```

---

### `crawling.sitemap.respect_priority`

Sort URLs by sitemap priority field (highest first).

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
crawling:
  sitemap:
    respect_priority: true
```

---

### `crawling.sitemap.max_urls`

Maximum URLs to load from sitemaps.

**Type:** `int | null` (≥1)
**Default:** `null` (unlimited)
**Example:**

```yaml
crawling:
  sitemap:
    max_urls: 1000  # Limit sitemap URLs
```

---

## Content Filtering

### `output.markdown.content_filtering.enabled`

Enable content filtering to remove unwanted HTML elements.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
output:
  markdown:
    content_filtering:
      enabled: true
```

---

### `output.markdown.content_filtering.remove_selectors`

CSS selectors for elements to remove before conversion.

**Type:** `list[string]`
**Default:** `[]`
**Example:**

```yaml
output:
  markdown:
    content_filtering:
      enabled: true
      remove_selectors:
        - "nav"           # Remove navigation
        - "footer"        # Remove footers
        - ".ads"          # Remove ads
        - "#sidebar"      # Remove sidebar
```

---

### `output.markdown.content_filtering.keep_selectors`

CSS selectors for elements to keep (extract only these, ignore rest).

**Type:** `list[string]`
**Default:** `[]`
**Example:**

```yaml
output:
  markdown:
    content_filtering:
      enabled: true
      keep_selectors:
        - "article"       # Only article content
        - ".main-content" # Or main content div
```

**Note:** Use either `remove_selectors` OR `keep_selectors`, not both.

---

## Pipeline Mode

### `crawling.pipeline.enabled`

Enable pipeline architecture for 3-10x throughput improvement.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
crawling:
  pipeline:
    enabled: true
```

---

### `crawling.pipeline.process_workers`

Number of processing workers (None = auto-detect: min(10, cpu_count)).

**Type:** `int | null` (1-50)
**Default:** `null`
**Example:**

```yaml
crawling:
  pipeline:
    process_workers: 8  # Explicit worker count
```

---

### `crawling.pipeline.queue_maxsize`

Maximum processing queue size.

**Type:** `int` (10-1000)
**Default:** `100`
**Example:**

```yaml
crawling:
  pipeline:
    queue_maxsize: 500  # Larger queue
```

---

### `crawling.pipeline.max_queue_memory_mb`

Maximum memory per queue in MB (backpressure threshold).

**Type:** `int` (100-4096)
**Default:** `500`
**Example:**

```yaml
crawling:
  pipeline:
    max_queue_memory_mb: 1000  # 1GB queue limit
```

---

## HTTP Caching

### `crawling.cache.enabled`

Enable HTTP caching for development/repeated crawls.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
crawling:
  cache:
    enabled: true  # Speed up development
```

---

### `crawling.cache.backend`

Cache storage backend.

**Type:** `"sqlite" | "memory"`
**Default:** `"sqlite"`
**Options:**
- `sqlite` - Persistent cache (survives restarts)
- `memory` - Ephemeral cache (lost on restart)

**Example:**

```yaml
crawling:
  cache:
    backend: memory  # For testing
```

---

### `crawling.cache.cache_dir`

Cache directory (relative to output directory).

**Type:** `string`
**Default:** `".sus_cache"`
**Example:**

```yaml
crawling:
  cache:
    cache_dir: http_cache
```

---

### `crawling.cache.ttl_seconds`

Cache TTL in seconds (overrides server headers).

**Type:** `int | null` (≥60)
**Default:** `3600` (1 hour)
**Example:**

```yaml
crawling:
  cache:
    ttl_seconds: 86400  # 24 hours
```

---

## Output Configuration

### `output.base_dir`

Base output directory.

**Type:** `string`
**Default:** `"output"`
**Example:**

```yaml
output:
  base_dir: ./scrape_results
```

---

### `output.site_dir`

Site-specific subdirectory (defaults to config `name`).

**Type:** `string | null`
**Default:** `null`
**Example:**

```yaml
output:
  site_dir: python-docs-v3.12
```

---

### `output.docs_dir`

Subdirectory for markdown files.

**Type:** `string`
**Default:** `"docs"`
**Example:**

```yaml
output:
  docs_dir: pages  # output/pages/ instead of output/docs/
```

---

### `output.assets_dir`

Subdirectory for downloaded assets.

**Type:** `string`
**Default:** `"assets"`
**Example:**

```yaml
output:
  assets_dir: media
```

---

### `output.markdown.add_frontmatter`

Add YAML frontmatter to markdown files.

**Type:** `bool`
**Default:** `true`
**Example:**

```yaml
output:
  markdown:
    add_frontmatter: false  # No frontmatter
```

---

### `output.markdown.frontmatter_fields`

Fields to include in frontmatter.

**Type:** `list[string]`
**Default:** `["title", "url", "scraped_at"]`
**Example:**

```yaml
output:
  markdown:
    frontmatter_fields:
      - title
      - url
      - scraped_at
      - description
```

---

### `output.path_mapping.strip_prefix`

URL path prefix to strip when generating file paths.

**Type:** `string | null`
**Default:** `null`
**Example:**

```yaml
output:
  path_mapping:
    strip_prefix: "/docs/v3/"  # /docs/v3/guide/ → guide/
```

---

### `output.path_mapping.index_file`

Filename for directory index pages.

**Type:** `string`
**Default:** `"index.md"`
**Example:**

```yaml
output:
  path_mapping:
    index_file: README.md
```

---

## Asset Configuration

### `assets.download`

Whether to download assets.

**Type:** `bool`
**Default:** `true`
**Example:**

```yaml
assets:
  download: false  # Skip asset downloads
```

---

### `assets.types`

Asset types to download.

**Type:** `list[string]`
**Default:** `["image", "css", "javascript"]`
**Example:**

```yaml
assets:
  types:
    - image  # Only images
```

---

### `assets.rewrite_paths`

Rewrite asset paths in markdown to local paths.

**Type:** `bool`
**Default:** `true`
**Example:**

```yaml
assets:
  rewrite_paths: false  # Keep absolute URLs
```

---

### `assets.max_concurrent_asset_downloads`

Maximum concurrent asset downloads.

**Type:** `int` (≥1)
**Default:** `10`
**Example:**

```yaml
assets:
  max_concurrent_asset_downloads: 20
```

---

## Plugin System

### `plugins.enabled`

Enable plugin system.

**Type:** `bool`
**Default:** `false`
**Example:**

```yaml
plugins:
  enabled: true
```

---

### `plugins.plugins`

List of plugin module paths to load.

**Type:** `list[string]`
**Default:** `[]`
**Example:**

```yaml
plugins:
  enabled: true
  plugins:
    - sus.plugins.code_highlight
    - sus.plugins.image_optimizer
    - sus.plugins.link_validator
    - my_custom_plugin.MyPlugin
```

---

### `plugins.plugin_settings`

Plugin-specific settings keyed by plugin path.

**Type:** `dict[string, any]`
**Default:** `{}`
**Example:**

```yaml
plugins:
  enabled: true
  plugins:
    - sus.plugins.code_highlight
    - sus.plugins.image_optimizer

  plugin_settings:
    sus.plugins.code_highlight:
      style: monokai
      linenos: true

    sus.plugins.image_optimizer:
      max_width: 1200
      quality: 85
```

---

## Built-in Plugins

### Code Highlighting Plugin

Syntax highlighting for code blocks using Pygments.

**Requires:** `uv pip install sus[plugins]`

```yaml
plugins:
  enabled: true
  plugins:
    - sus.plugins.code_highlight
  plugin_settings:
    sus.plugins.code_highlight:
      style: monokai      # Pygments style
      linenos: true       # Show line numbers
```

---

### Image Optimizer Plugin

Optimize and resize images.

**Requires:** `uv pip install sus[plugins]`

```yaml
plugins:
  enabled: true
  plugins:
    - sus.plugins.image_optimizer
  plugin_settings:
    sus.plugins.image_optimizer:
      max_width: 1200
      max_height: 1200
      quality: 85       # JPEG quality (1-100)
      format: null      # null = keep original format
```

---

### Link Validator Plugin

Validate internal and external links.

```yaml
plugins:
  enabled: true
  plugins:
    - sus.plugins.link_validator
  plugin_settings:
    sus.plugins.link_validator:
      check_external: false  # Only validate internal links
      timeout: 5.0           # External link check timeout
```

---

## Environment Variables

Use environment variables for sensitive data:

```yaml
crawling:
  authentication:
    enabled: true
    auth_type: basic
    username: ${USERNAME}      # From environment
    password: ${PASSWORD}      # From environment
```

Set environment variables before running:

```bash
export USERNAME=myuser
export PASSWORD=mypass
sus scrape --config config.yaml
```

---

## See Also

- **[Getting Started](getting-started.md)** - Installation and first scrape
- **[Examples](examples.md)** - Real-world configurations
- **[API Reference](api/overview.md)** - Python API documentation
