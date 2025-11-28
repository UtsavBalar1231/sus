"""Configuration system.

YAML configuration files validated by Pydantic models with type-safe schemas, validation,
sensible defaults, and clear error messages. Entry point: load_config().
"""

import fnmatch
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from sus.exceptions import ConfigError


class PathPattern(BaseModel):
    """URL pattern matching configuration.

    Supports three pattern types:
    - regex: Regular expression matching
    - glob: Shell-style glob patterns (e.g., "*.html")
    - prefix: Simple prefix matching (e.g., "/docs/")
    """

    pattern: str = Field(
        ...,
        description=(
            "Pattern to match URL paths against. "
            "For prefix: '/docs/' matches all paths starting with /docs/. "
            "For glob: '*.html' matches page.html, docs/intro.html. "
            "For regex: '^/api/v\\d+/' matches /api/v1/, /api/v2/, etc."
        ),
    )
    type: Literal["regex", "glob", "prefix"] = Field(
        ...,
        description=(
            "Pattern type. Use 'prefix' for simple path matching (fastest, most common). "
            "Use 'glob' for wildcards like *.html, /docs/*. "
            "Use 'regex' for complex patterns like /api/v\\d+/ or (foo|bar)."
        ),
    )

    def matches(self, path: str) -> bool:
        """Check if URL path matches this pattern.

        Args:
            path: URL path component (e.g., "/docs/guide/")

        Returns:
            True if path matches the pattern

        Examples:
            >>> pattern = PathPattern(pattern="/docs/", type="prefix")
            >>> pattern.matches("/docs/guide/")
            True
            >>> pattern.matches("/blog/")
            False

            >>> pattern = PathPattern(pattern="*.html", type="glob")
            >>> pattern.matches("/page.html")
            True

            >>> pattern = PathPattern(pattern=r"^/api/v\\d+/", type="regex")
            >>> pattern.matches("/api/v2/users")
            True
        """
        if self.type == "regex":
            # Use re.match() which matches from the beginning
            return bool(re.match(self.pattern, path))
        elif self.type == "glob":
            # Convert glob to regex using fnmatch.translate()
            regex_pattern = fnmatch.translate(self.pattern)
            # fnmatch.translate() adds \Z at the end for full match
            # We want to match if the pattern matches anywhere in the path
            return bool(re.match(regex_pattern, path))
        elif self.type == "prefix":
            # Simple startswith() check
            return path.startswith(self.pattern)
        return False


class SiteConfig(BaseModel):
    """Website configuration for crawling."""

    start_urls: list[str] = Field(..., min_length=1, description="Starting URLs for the crawler")
    allowed_domains: list[str] = Field(
        ..., min_length=1, description="Domains allowed for crawling"
    )


class SitemapConfig(BaseModel):
    """Sitemap.xml parsing configuration.

    Controls whether to parse sitemaps, how to discover them, and how to handle URLs.
    """

    enabled: bool = Field(
        default=False,
        description="Whether to parse sitemap.xml files",
    )
    auto_discover: bool = Field(
        default=True,
        description="Auto-discover sitemaps from robots.txt and /sitemap.xml",
    )
    urls: list[str] = Field(
        default_factory=list,
        description="Explicit sitemap URLs to parse (in addition to auto-discovery)",
    )
    respect_priority: bool = Field(
        default=False,
        description="Sort URLs by priority field (highest first)",
    )
    max_urls: int | None = Field(
        default=None,
        ge=1,
        description="Maximum URLs to load from sitemaps (None = unlimited)",
    )
    strict: bool = Field(
        default=False,
        description="If True, raise errors on malformed sitemaps; if False, skip invalid entries",
    )


class CheckpointConfig(BaseModel):
    """Checkpoint/resume configuration for incremental scraping."""

    enabled: bool = Field(
        default=False,
        description="Enable checkpoint/resume functionality",
    )
    backend: Literal["json", "sqlite"] = Field(
        default="json",
        description="Backend type: json (default, <10K pages) or sqlite (>10K pages)",
    )
    checkpoint_file: str = Field(
        default=".sus_checkpoint.json",
        description=(
            "Checkpoint file name (relative to output directory). Use .json or .db extension."
        ),
    )
    checkpoint_interval_pages: int = Field(
        default=10,
        ge=1,
        description="Save checkpoint every N pages",
    )
    detect_changes: bool = Field(
        default=True,
        description="Detect content changes via SHA-256 hashing",
    )
    force_redownload_after_days: int | None = Field(
        default=7,
        ge=1,
        description="Force redownload if page older than N days (None = disable)",
    )


class CacheConfig(BaseModel):
    """HTTP caching configuration for development and repeated crawls.

    Uses Hishel library for RFC 9111 compliant HTTP caching.
    Speeds up repeated crawls during development by caching HTTP responses.
    """

    enabled: bool = Field(
        default=False,
        description="Enable HTTP caching (opt-in for development/testing)",
    )
    backend: Literal["sqlite", "memory"] = Field(
        default="sqlite",
        description=(
            "Cache backend: sqlite (persistent, better performance), "
            "memory (ephemeral, cache lost on restart)"
        ),
    )
    cache_dir: str = Field(
        default=".sus_cache",
        description="Cache directory (relative to output directory)",
    )
    ttl_seconds: int | None = Field(
        default=3600,
        ge=60,
        description=(
            "Cache TTL in seconds (None = respect server headers only). "
            "Overrides server Cache-Control headers when set."
        ),
    )


class JavaScriptConfig(BaseModel):
    """JavaScript rendering configuration using Playwright.

    Controls browser-based rendering for SPAs and JavaScript-heavy sites.
    Requires optional 'js' dependency: uv sync --group js && playwright install chromium

    Modes:
    - disabled: Never use JavaScript rendering (fastest, HTTP-only)
    - enabled: Always use JavaScript rendering (slowest, most complete)
    - auto: HTTP-first with automatic JS fallback when content is insufficient (recommended)
    """

    mode: Literal["disabled", "enabled", "auto"] = Field(
        default="disabled",
        description=(
            "JS rendering mode: disabled (HTTP-only), enabled (always JS), "
            "auto (HTTP-first with JS fallback when content quality is low)"
        ),
    )
    enabled: bool = Field(
        default=False,
        description="[DEPRECATED: Use mode instead] Enable JavaScript rendering",
    )
    auto_quality_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum content quality score for auto mode (0.0-1.0). "
        "Pages below this threshold will be re-fetched with JS rendering.",
    )
    wait_for: Literal["domcontentloaded", "load", "networkidle"] = Field(
        default="load",
        description="Wait strategy: domcontentloaded (fast), load (balanced), networkidle (slow)",
    )
    wait_timeout_ms: int = Field(
        default=30000,
        ge=1000,
        le=120000,
        description="Maximum time to wait for page load in milliseconds (1s-120s)",
    )
    user_agent_override: str | None = Field(
        default=None,
        description="Custom user agent for browser (None = use default)",
    )
    viewport_width: int = Field(
        default=1920,
        ge=320,
        le=3840,
        description="Browser viewport width in pixels",
    )
    viewport_height: int = Field(
        default=1080,
        ge=240,
        le=2160,
        description="Browser viewport height in pixels",
    )
    javascript_enabled: bool = Field(
        default=True,
        description="Enable JavaScript execution in browser (disable for debugging)",
    )
    context_pool_size: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Number of browser contexts to pool for reuse (reduces overhead)",
    )

    @model_validator(mode="after")
    def validate_js_config(self) -> "JavaScriptConfig":
        """Handle backwards compatibility: enabled=True maps to mode='enabled'."""
        # If user set enabled=True but didn't set mode, upgrade to mode='enabled'
        if self.enabled and self.mode == "disabled":
            object.__setattr__(self, "mode", "enabled")
        return self

    @property
    def is_js_possible(self) -> bool:
        """Returns True if JS rendering might be used (mode is enabled or auto)."""
        return self.mode in ("enabled", "auto")


class AuthenticationConfig(BaseModel):
    """Authentication configuration for accessing protected content.

    Supports multiple authentication methods:
    - basic: HTTP Basic Authentication (username/password)
    - cookie: Cookie-based session authentication
    - header: Custom header authentication (API keys, tokens)
    - oauth2: OAuth 2.0 Client Credentials flow

    Only one auth method should be configured per site.
    """

    enabled: bool = Field(
        default=False,
        description="Enable authentication",
    )
    auth_type: Literal["basic", "cookie", "header", "oauth2"] | None = Field(
        default=None,
        description="Authentication type (required if enabled=True)",
    )

    # Basic Auth fields
    username: str | None = Field(
        default=None,
        description="Username for Basic Auth",
    )
    password: str | None = Field(
        default=None,
        description=(
            "Password for Basic Auth. "
            "⚠️ SECURITY: Use environment variables instead of plaintext. "
            "Never commit secrets to version control."
        ),
    )

    # Cookie Auth fields
    cookies: dict[str, str] = Field(
        default_factory=dict,
        description="Session cookies for Cookie Auth (key=cookie_name, value=cookie_value)",
    )

    # Header Auth fields
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Custom headers for Header Auth (e.g., {'X-API-Key': 'secret'})",
    )

    # OAuth2 fields
    client_id: str | None = Field(
        default=None,
        description="OAuth2 client ID",
    )
    client_secret: str | None = Field(
        default=None,
        description=(
            "OAuth2 client secret. "
            "⚠️ SECURITY: Use environment variables instead of plaintext. "
            "Never commit secrets to version control."
        ),
    )
    token_url: str | None = Field(
        default=None,
        description="OAuth2 token endpoint URL",
    )
    scope: str | None = Field(
        default=None,
        description="OAuth2 scope (optional)",
    )

    @model_validator(mode="after")
    def validate_auth_config(self) -> "AuthenticationConfig":
        """Validate cross-field authentication requirements."""
        if not self.enabled:
            return self

        # If enabled, auth_type is required
        if self.auth_type is None:
            raise ValueError(
                "auth_type is required when authentication is enabled. "
                "Add 'auth_type: basic|cookie|header|oauth2' to your config."
            )

        # Validate required fields for each auth type
        if self.auth_type == "basic":
            if not self.username or not self.password:
                raise ValueError(
                    "username and password are required for Basic Auth. "
                    "Add 'username' and 'password' fields under 'authentication'."
                )
        elif self.auth_type == "cookie":
            if not self.cookies:
                raise ValueError(
                    "cookies dict is required for Cookie Auth. "
                    "Add 'cookies: {cookie_name: value}' under 'authentication'."
                )
        elif self.auth_type == "header":
            if not self.headers:
                raise ValueError(
                    "headers dict is required for Header Auth. "
                    "Add 'headers: {Authorization: Bearer <token>}' under 'authentication'."
                )
        elif self.auth_type == "oauth2" and (
            not self.client_id or not self.client_secret or not self.token_url
        ):
            raise ValueError(
                "client_id, client_secret, and token_url are required for OAuth2. "
                "Add all three fields under 'authentication'."
            )

        return self


class PipelineConfig(BaseModel):
    """Producer-consumer pipeline configuration for concurrent processing.

    Enables pipeline architecture where crawling and processing happen in parallel
    via multiple worker pools. Target: 3-10x throughput improvement over sequential.

    Note: Crawl workers are controlled by global_concurrent_requests.
    Pipeline adds parallel processing of fetched pages.
    """

    enabled: bool = Field(
        default=True,
        description="Enable pipeline architecture for concurrent processing",
    )
    process_workers: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Number of process workers (None = max(1, cpu_count - 2))",
    )
    queue_maxsize: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum size of processing queue",
    )
    max_queue_memory_mb: int = Field(
        default=500,
        ge=100,
        le=4096,
        description="Maximum memory usage per queue in MB (backpressure threshold)",
    )


class PerformanceConfig(BaseModel):
    """Performance optimization configuration.

    Controls advanced performance features for high-throughput crawling:
    - HTTP client backend selection (httpx for HTTP/2, aiohttp for speed)
    - DNS caching and prefetching
    - Connection pooling tuning
    - Batch I/O for file writes

    Target: 100-200+ pages/sec with optimal settings.
    """

    http_backend: Literal["auto", "httpx", "aiohttp"] = Field(
        default="auto",
        description=(
            "HTTP client backend: "
            "'auto' (prefer aiohttp for speed, httpx when auth/HTTP2 needed), "
            "'httpx' (HTTP/2 support, auth), "
            "'aiohttp' (7.5x faster for HTTP/1.1)"
        ),
    )
    dns_cache_ttl: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="DNS cache TTL in seconds (default: 300 = 5 minutes)",
    )
    dns_max_concurrent: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Maximum concurrent DNS lookups",
    )
    max_connections: int = Field(
        default=500,
        ge=50,
        le=2000,
        description="Maximum HTTP connections in pool",
    )
    max_keepalive_connections: int = Field(
        default=100,
        ge=20,
        le=500,
        description="Maximum keepalive connections to maintain",
    )
    keepalive_expiry: float = Field(
        default=60.0,
        ge=10.0,
        le=300.0,
        description="Keepalive connection expiry in seconds",
    )
    batch_write_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of files to batch before flushing to disk",
    )
    batch_write_buffer_mb: int = Field(
        default=50,
        ge=10,
        le=500,
        description="Maximum memory buffer for batched writes in MB",
    )
    adaptive_rate_limiting: bool = Field(
        default=True,
        description=(
            "Enable adaptive rate limiting that slows down on 429s and speeds up on fast responses"
        ),
    )
    conditional_requests: bool = Field(
        default=True,
        description=(
            "Use ETag/If-Modified-Since for conditional requests "
            "(50-90% bandwidth savings on re-crawls)"
        ),
    )


class CrawlingRules(BaseModel):
    """Crawling behavior configuration.

    Controls which URLs to follow, concurrency limits, rate limiting,
    and retry behavior.
    """

    include_patterns: list[PathPattern] = Field(
        default_factory=list,
        description="URL patterns to include (whitelist)",
    )
    exclude_patterns: list[PathPattern] = Field(
        default_factory=list,
        description="URL patterns to exclude (blacklist)",
    )
    depth_limit: int | None = Field(
        default=None,
        ge=0,
        description="Maximum crawl depth from start URLs (None = unlimited)",
    )
    max_pages: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of pages to crawl (None = unlimited)",
    )
    delay_between_requests: float = Field(
        default=0.1,  # Reduced from 0.5 for faster crawling
        ge=0.0,
        description="Delay between requests in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retries for failed requests",
    )
    retry_backoff: float = Field(
        default=2.0,
        ge=1.0,
        description="Exponential backoff multiplier for retries",
    )
    retry_jitter: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Jitter for retry backoff (0-1 range, prevents thundering herd). "
        "0 = no jitter, 1 = full jitter (recommended: 0.3)",
    )
    global_concurrent_requests: int = Field(
        default=200,  # Increased from 50 for high-performance crawling
        ge=1,
        description="Global concurrency limit across all domains",
    )
    per_domain_concurrent_requests: int = Field(
        default=25,  # Increased from 10 for faster per-domain crawling
        ge=1,
        description="Per-domain concurrency limit",
    )
    rate_limiter_burst_size: int = Field(
        default=50,  # Increased from 10: Allow larger bursts for faster scraping
        ge=1,
        description="Token bucket burst size for rate limiting",
    )
    link_selectors: list[str] = Field(
        default_factory=lambda: ["a[href]"],
        description="CSS selectors for extracting links",
    )
    respect_robots_txt: bool = Field(
        default=True,
        description="Whether to respect robots.txt rules",
    )
    max_page_size_mb: float | None = Field(
        default=10.0,
        ge=0.1,
        description="Maximum page size in MB (None = unlimited). Prevents downloading huge files.",
    )
    max_asset_size_mb: float | None = Field(
        default=50.0,
        ge=0.1,
        description=(
            "Maximum asset size in MB (None = unlimited). Prevents downloading huge images/videos."
        ),
    )
    max_redirects: int = Field(
        default=10,
        ge=0,
        le=20,
        description="Maximum redirects to follow per request. Prevents redirect loops.",
    )
    memory_check_interval: int = Field(
        default=1,
        ge=1,
        description="Check memory usage every N pages (default: 1 = every page). "
        "Reduces frequency to improve performance if needed.",
    )
    sitemap: SitemapConfig = Field(
        default_factory=SitemapConfig,
        description="Sitemap.xml parsing configuration",
    )
    javascript: JavaScriptConfig = Field(
        default_factory=JavaScriptConfig,
        description="JavaScript rendering configuration",
    )
    checkpoint: CheckpointConfig = Field(
        default_factory=CheckpointConfig,
        description="Checkpoint/resume configuration",
    )
    pipeline: PipelineConfig = Field(
        default_factory=PipelineConfig,
        description="Producer-consumer pipeline configuration",
    )
    authentication: AuthenticationConfig = Field(
        default_factory=AuthenticationConfig,
        description="Authentication configuration",
    )
    cache: CacheConfig = Field(
        default_factory=CacheConfig,
        description="HTTP caching configuration",
    )
    performance: PerformanceConfig = Field(
        default_factory=PerformanceConfig,
        description="Performance optimization configuration",
    )


class PathMappingConfig(BaseModel):
    """URL to file path mapping configuration."""

    mode: Literal["auto"] = Field(
        default="auto",
        description="Path mapping mode (currently only 'auto' is supported)",
    )
    strip_prefix: str | None = Field(
        default=None,
        description="URL path prefix to strip when generating file paths",
    )
    index_file: str = Field(
        default="index.md",
        description="Filename for directory index pages",
    )


class ContentFilteringConfig(BaseModel):
    """Content filtering configuration for removing unwanted elements.

    Allows filtering HTML content by CSS selectors before conversion to Markdown.
    Useful for removing navigation bars, footers, ads, and other noise.
    """

    enabled: bool = Field(
        default=False,
        description="Enable content filtering",
    )
    remove_selectors: list[str] = Field(
        default_factory=list,
        description="CSS selectors for elements to remove (e.g., ['nav', 'footer', '.ads'])",
    )
    keep_selectors: list[str] = Field(
        default_factory=list,
        description="CSS selectors for elements to keep (extract only these, ignore rest)",
    )

    @model_validator(mode="after")
    def validate_filtering_config(self) -> "ContentFilteringConfig":
        """Validate that at least one selector is provided when filtering is enabled."""
        if self.enabled and not self.keep_selectors and not self.remove_selectors:
            raise ValueError(
                "At least one of keep_selectors or remove_selectors must be provided "
                "when content filtering is enabled. Examples:\n"
                "  keep_selectors: ['article', 'main']  # Keep only these elements\n"
                "  remove_selectors: ['nav', 'footer', '.ads']  # Remove these elements"
            )
        return self


class MarkdownConfig(BaseModel):
    """Markdown conversion options."""

    add_frontmatter: bool = Field(
        default=True,
        description="Whether to add YAML frontmatter to markdown files",
    )
    frontmatter_fields: list[str] = Field(
        default_factory=lambda: ["title", "url", "scraped_at"],
        description="Fields to include in frontmatter",
    )
    content_filtering: ContentFilteringConfig = Field(
        default_factory=ContentFilteringConfig,
        description="Content filtering configuration",
    )


class OutputConfig(BaseModel):
    """Output directory structure configuration."""

    base_dir: str = Field(
        default="output",
        description="Base output directory",
    )
    site_dir: str | None = Field(
        default=None,
        description="Site-specific subdirectory (defaults to config name)",
    )
    docs_dir: str = Field(
        default="docs",
        description="Subdirectory for markdown documentation files",
    )
    assets_dir: str = Field(
        default="assets",
        description="Subdirectory for downloaded assets",
    )
    path_mapping: PathMappingConfig = Field(
        default_factory=PathMappingConfig,
        description="URL to file path mapping configuration",
    )
    markdown: MarkdownConfig = Field(
        default_factory=MarkdownConfig,
        description="Markdown conversion configuration",
    )


class AssetConfig(BaseModel):
    """Asset download configuration."""

    download: bool = Field(
        default=True,
        description="Whether to download assets",
    )
    types: list[str] = Field(
        default_factory=lambda: ["image", "css", "javascript"],
        description="Asset types to download",
    )
    rewrite_paths: bool = Field(
        default=True,
        description="Whether to rewrite asset paths in markdown to local paths",
    )
    max_concurrent_asset_downloads: int = Field(
        default=10,
        ge=1,
        description="Maximum concurrent asset downloads",
    )


class PluginConfig(BaseModel):
    """Plugin system configuration."""

    enabled: bool = Field(
        default=False,
        description="Whether to enable plugin system",
    )
    plugins: list[str] = Field(
        default_factory=list,
        description="List of plugin module paths to load",
    )
    plugin_settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Plugin-specific settings keyed by plugin path",
    )


class SusConfig(BaseModel):
    """Main configuration model for SUS scraper.

    This is the root configuration object that contains all settings
    for a scraping project.
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Site/config name (used as default site_dir)",
    )
    description: str = Field(
        default="",
        description="Human-readable description of this configuration",
    )
    site: SiteConfig = Field(
        ...,
        description="Website configuration",
    )
    crawling: CrawlingRules = Field(
        default_factory=CrawlingRules,
        description="Crawling behavior rules",
    )
    output: OutputConfig = Field(
        default_factory=OutputConfig,
        description="Output directory structure",
    )
    assets: AssetConfig = Field(
        default_factory=AssetConfig,
        description="Asset download configuration",
    )
    plugins: PluginConfig = Field(
        default_factory=PluginConfig,
        description="Plugin system configuration",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate that name is a valid directory name.

        The name must not contain path separators or special characters
        that would be invalid in directory names.
        """
        if not v:
            raise ValueError(
                "name cannot be empty. Add 'name: my-project' at the top of your config file."
            )

        # Check for invalid characters in directory names
        invalid_chars = set('/\\:*?"<>|')
        if any(char in v for char in invalid_chars):
            raise ValueError(
                f"name contains invalid characters: {v!r}. "
                f"Use only letters, numbers, hyphens, and underscores."
            )

        # Check for dangerous names
        if v in (".", ".."):
            raise ValueError(f"name cannot be '.' or '..': {v!r}. Use a descriptive project name.")

        # Check for leading/trailing whitespace
        if v != v.strip():
            raise ValueError(
                f"name cannot have leading/trailing whitespace: {v!r}. Use '{v.strip()}' instead."
            )

        return v


def load_config(path: Path) -> SusConfig:
    """Load and validate YAML configuration file.

    Args:
        path: Path to YAML configuration file

    Returns:
        Validated SusConfig instance

    Raises:
        ConfigError: If config file is not found, invalid YAML, or validation fails
    """
    try:
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        if not path.is_file():
            raise ValueError(f"Configuration path is not a file: {path}")

        with path.open("r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)

        if config_dict is None:
            raise ValueError(f"Configuration file is empty: {path}")

        if not isinstance(config_dict, dict):
            raise ValueError(
                f"Configuration file must contain a YAML object/dict, "
                f"got {type(config_dict).__name__}"
            )

        return SusConfig(**config_dict)
    except FileNotFoundError as e:
        raise ConfigError(f"Configuration file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e
    except ValidationError as e:
        raise ConfigError(f"Configuration validation failed for {path}:\n{e}") from e
