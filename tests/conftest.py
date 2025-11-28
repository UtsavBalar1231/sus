"""Pytest fixtures for SUS scraper tests."""

import hashlib
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

import httpx
import pytest

from sus.backends import CheckpointMetadata, PageCheckpoint
from sus.config import (
    AssetConfig,
    AuthenticationConfig,
    CheckpointConfig,
    CrawlingRules,
    JavaScriptConfig,
    MarkdownConfig,
    OutputConfig,
    PathMappingConfig,
    PathPattern,
    SiteConfig,
    SusConfig,
)
from sus.crawler import Crawler, CrawlResult


@pytest.fixture
def sample_config() -> SusConfig:
    """Create a sample SusConfig for testing.

    Returns a basic configuration with sensible defaults suitable
    for most tests.
    """
    return SusConfig(
        name="test-site",
        description="Test configuration",
        site=SiteConfig(
            start_urls=["http://example.com/docs/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            include_patterns=[
                PathPattern(pattern="^/docs/", type="regex"),
            ],
            exclude_patterns=[
                PathPattern(pattern="*.pdf", type="glob"),
            ],
            depth_limit=2,
            delay_between_requests=0.01,  # Fast for testing
            global_concurrent_requests=2,
            per_domain_concurrent_requests=1,
            max_retries=1,
            retry_backoff=1.5,
            respect_robots_txt=False,  # Disable for testing to avoid mocking robots.txt
        ),
        output=OutputConfig(
            base_dir="output",
            docs_dir="docs",
            assets_dir="assets",
            path_mapping=PathMappingConfig(
                strip_prefix="/docs",
                index_file="index.md",
            ),
            markdown=MarkdownConfig(
                add_frontmatter=True,
                frontmatter_fields=["title", "url", "scraped_at"],
            ),
        ),
        assets=AssetConfig(
            download=False,  # Disabled by default for testing
            types=["image", "css", "javascript"],
            rewrite_paths=True,
        ),
    )


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for output files.

    Automatically cleaned up after test completes.

    Yields:
        Path to temporary directory
    """
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_html() -> str:
    """Return sample HTML content for testing.

    Contains common HTML elements including:
    - Title, headings, paragraphs
    - Internal and external links
    - Images, CSS, JavaScript references
    - Lists and tables
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sample Page</title>
    <link rel="stylesheet" href="/css/style.css">
    <script src="/js/app.js"></script>
</head>
<body>
    <h1>Welcome to Sample Page</h1>
    <p>This is a <strong>sample</strong> page for <em>testing</em>.</p>

    <h2>Links</h2>
    <ul>
        <li><a href="/docs/guide">Guide</a></li>
        <li><a href="/docs/api/reference">API Reference</a></li>
        <li><a href="http://example.com/blog/post">Blog Post</a></li>
        <li><a href="http://external.com/page">External Link</a></li>
    </ul>

    <h2>Images</h2>
    <img src="/img/logo.png" alt="Logo">
    <img src="http://example.com/img/banner.jpg" alt="Banner">

    <h2>Table</h2>
    <table>
        <tr><th>Name</th><th>Value</th></tr>
        <tr><td>Item 1</td><td>100</td></tr>
        <tr><td>Item 2</td><td>200</td></tr>
    </table>
</body>
</html>"""


@pytest.fixture
def sample_html_with_dangerous_links() -> str:
    """Return HTML with various dangerous link schemes.

    Used for testing link filtering and sanitization.
    """
    return """<!DOCTYPE html>
<html>
<body>
    <a href="http://example.com/safe">Safe HTTP</a>
    <a href="https://example.com/safe">Safe HTTPS</a>
    <a href="mailto:user@example.com">Email</a>
    <a href="tel:+1234567890">Phone</a>
    <a href="javascript:alert('xss')">JavaScript</a>
    <a href="data:text/html,<script>alert('xss')</script>">Data URI</a>
    <a href="file:///etc/passwd">File</a>
    <a href="ftp://ftp.example.com/file">FTP</a>
</body>
</html>"""


@pytest.fixture
def sample_html_minimal() -> str:
    """Return minimal HTML for basic testing.

    Contains just a title and one paragraph.
    """
    return """<!DOCTYPE html>
<html>
<head><title>Minimal Page</title></head>
<body><p>Hello World</p></body>
</html>"""


@pytest.fixture
def config_with_no_rate_limit(sample_config: SusConfig) -> SusConfig:
    """Create config with no rate limiting for faster tests.

    Args:
        sample_config: Base configuration

    Returns:
        Modified config with no delays
    """
    config = sample_config.model_copy(deep=True)
    config.crawling.delay_between_requests = 0.0
    config.crawling.global_concurrent_requests = 10
    config.crawling.per_domain_concurrent_requests = 5
    return config


def create_basic_config(
    name: str = "test-site",
    start_urls: list[str] | None = None,
    allowed_domains: list[str] | None = None,
    output_dir: Path | None = None,
    *,
    respect_robots_txt: bool = False,
    max_retries: int = 1,
    delay_between_requests: float = 0.01,
) -> SusConfig:
    """Create a basic SusConfig for testing.

    Factory function for creating minimal test configurations with sensible defaults.

    Args:
        name: Configuration name
        start_urls: List of starting URLs (defaults to ["http://example.com/"])
        allowed_domains: List of allowed domains (defaults to ["example.com"])
        output_dir: Output directory path (defaults to "output")
        respect_robots_txt: Whether to respect robots.txt (default: False for testing)
        max_retries: Maximum retry attempts (default: 1 for fast tests)
        delay_between_requests: Delay between requests in seconds (default: 0.01)

    Returns:
        SusConfig with minimal configuration suitable for most tests

    Example:
        >>> config = create_basic_config(
        ...     name="my-test",
        ...     start_urls=["https://example.com/docs"],
        ...     output_dir=Path("/tmp/output")
        ... )
        >>> assert config.name == "my-test"
        >>> assert config.site.start_urls == ["https://example.com/docs"]
    """
    if start_urls is None:
        start_urls = ["http://example.com/"]
    if allowed_domains is None:
        allowed_domains = ["example.com"]

    return SusConfig(
        name=name,
        site=SiteConfig(
            start_urls=start_urls,
            allowed_domains=allowed_domains,
        ),
        crawling=CrawlingRules(
            delay_between_requests=delay_between_requests,
            max_retries=max_retries,
            respect_robots_txt=respect_robots_txt,
            global_concurrent_requests=2,
            per_domain_concurrent_requests=1,
        ),
        output=OutputConfig(
            base_dir=str(output_dir) if output_dir else "output",
        ),
        assets=AssetConfig(
            download=False,  # Disabled by default for testing
        ),
    )


def create_config_with_javascript(
    name: str = "test-js-site",
    start_urls: list[str] | None = None,
    *,
    wait_for: Literal["domcontentloaded", "load", "networkidle"] = "networkidle",
    wait_timeout_ms: int = 30000,
    output_dir: Path | None = None,
) -> SusConfig:
    """Create SusConfig with JavaScript rendering enabled.

    Factory for testing Playwright-based JavaScript rendering scenarios.

    Args:
        name: Configuration name
        start_urls: List of starting URLs
        wait_for: Wait strategy ("domcontentloaded", "load", "networkidle")
        wait_timeout_ms: Wait timeout in milliseconds
        output_dir: Output directory path

    Returns:
        SusConfig with JavaScript rendering enabled

    Example:
        >>> config = create_config_with_javascript(
        ...     start_urls=["https://spa.example.com"],
        ...     wait_for="domcontentloaded"
        ... )
        >>> assert config.crawling.javascript.enabled is True
        >>> assert config.crawling.javascript.wait_for == "domcontentloaded"
    """
    config = create_basic_config(
        name=name,
        start_urls=start_urls,
        output_dir=output_dir,
    )

    config.crawling.javascript = JavaScriptConfig(
        enabled=True,
        wait_for=wait_for,
        wait_timeout_ms=wait_timeout_ms,
    )

    return config


def create_config_with_checkpoint(
    name: str = "test-checkpoint-site",
    start_urls: list[str] | None = None,
    *,
    checkpoint_file: Path | None = None,
    backend: Literal["json", "sqlite"] = "json",
    output_dir: Path | None = None,
) -> SusConfig:
    """Create SusConfig with checkpoint/resume enabled.

    Factory for testing checkpoint and incremental scraping scenarios.

    Args:
        name: Configuration name
        start_urls: List of starting URLs
        checkpoint_file: Path to checkpoint file (defaults to "checkpoint.json")
        backend: Backend type ("json" or "sqlite")
        output_dir: Output directory path

    Returns:
        SusConfig with checkpoint enabled

    Example:
        >>> config = create_config_with_checkpoint(
        ...     checkpoint_file=Path("/tmp/checkpoint.db"),
        ...     backend="sqlite"
        ... )
        >>> assert config.crawling.checkpoint.enabled is True
        >>> assert config.crawling.checkpoint.backend == "sqlite"
    """
    config = create_basic_config(
        name=name,
        start_urls=start_urls,
        output_dir=output_dir,
    )

    config.crawling.checkpoint = CheckpointConfig(
        enabled=True,
        checkpoint_file=str(checkpoint_file) if checkpoint_file else "checkpoint.json",
        backend=backend,
    )

    return config


def create_config_with_auth(
    name: str = "test-auth-site",
    start_urls: list[str] | None = None,
    *,
    auth_type: str = "basic",
    username: str = "testuser",
    password: str = "testpass",
    output_dir: Path | None = None,
) -> SusConfig:
    """Create SusConfig with authentication enabled.

    Factory for testing authentication scenarios (basic, cookie, header, oauth2).

    Args:
        name: Configuration name
        start_urls: List of starting URLs
        auth_type: Authentication type ("basic", "cookie", "header", "oauth2")
        username: Username (for basic auth)
        password: Password (for basic auth)
        output_dir: Output directory path

    Returns:
        SusConfig with authentication enabled

    Example:
        >>> config = create_config_with_auth(
        ...     auth_type="basic",
        ...     username="admin",
        ...     password="secret"
        ... )
        >>> assert config.crawling.authentication.auth_type == "basic"
        >>> assert config.crawling.authentication.username == "admin"
    """
    config = create_basic_config(
        name=name,
        start_urls=start_urls,
        output_dir=output_dir,
    )

    if auth_type == "basic":
        config.crawling.authentication = AuthenticationConfig(
            enabled=True,
            auth_type="basic",
            username=username,
            password=password,
        )
    elif auth_type == "cookie":
        config.crawling.authentication = AuthenticationConfig(
            enabled=True,
            auth_type="cookie",
            cookies={"session": "test-session-token"},
        )
    elif auth_type == "header":
        config.crawling.authentication = AuthenticationConfig(
            enabled=True,
            auth_type="header",
            headers={"Authorization": "Bearer test-token"},
        )
    elif auth_type == "oauth2":
        config.crawling.authentication = AuthenticationConfig(
            enabled=True,
            auth_type="oauth2",
            client_id="test-client",
            client_secret="test-secret",
            token_url="https://example.com/oauth/token",
        )
    else:
        msg = f"Unknown auth_type: {auth_type}"
        raise ValueError(msg)

    return config


def create_config_with_patterns(
    name: str = "test-pattern-site",
    start_urls: list[str] | None = None,
    *,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    output_dir: Path | None = None,
) -> SusConfig:
    """Create SusConfig with URL filtering patterns.

    Factory for testing URL include/exclude pattern matching.

    Args:
        name: Configuration name
        start_urls: List of starting URLs
        include_patterns: List of include patterns (regex, glob, or prefix)
        exclude_patterns: List of exclude patterns (regex, glob, or prefix)
        output_dir: Output directory path

    Returns:
        SusConfig with URL filtering patterns

    Example:
        >>> config = create_config_with_patterns(
        ...     include_patterns=["^/docs/"],
        ...     exclude_patterns=["*.pdf", "*/private/*"]
        ... )
        >>> assert len(config.crawling.include_patterns) == 1
        >>> assert len(config.crawling.exclude_patterns) == 2
    """
    config = create_basic_config(
        name=name,
        start_urls=start_urls,
        output_dir=output_dir,
    )

    if include_patterns:
        config.crawling.include_patterns = [
            PathPattern(pattern=p, type="regex")
            if p.startswith("^")
            else PathPattern(pattern=p, type="prefix")
            for p in include_patterns
        ]

    if exclude_patterns:
        config.crawling.exclude_patterns = [
            PathPattern(pattern=p, type="regex")
            if p.startswith("^")
            else PathPattern(pattern=p, type="glob")
            if "*" in p
            else PathPattern(pattern=p, type="prefix")
            for p in exclude_patterns
        ]

    return config


def create_crawl_result(
    url: str = "http://example.com/page",
    html: str | None = None,
    *,
    status_code: int = 200,
    content_type: str = "text/html; charset=utf-8",
    links: list[str] | None = None,
    assets: list[str] | None = None,
    content_hash: str = "",
    queue_size: int = 0,
) -> CrawlResult:
    """Create a CrawlResult instance for testing.

    Factory for creating mock crawl results with realistic data.

    Args:
        url: Page URL
        html: HTML content (defaults to minimal valid HTML)
        status_code: HTTP status code
        content_type: Content-Type header value
        links: Extracted links (absolute URLs)
        assets: Extracted asset URLs (images, CSS, JS)
        content_hash: SHA-256 hash of content (auto-computed if empty)
        queue_size: Current crawl queue size

    Returns:
        CrawlResult with specified or default values

    Example:
        >>> result = create_crawl_result(
        ...     url="https://example.com/docs",
        ...     links=["https://example.com/docs/guide"],
        ...     assets=["https://example.com/img/logo.png"]
        ... )
        >>> assert result.status_code == 200
        >>> assert len(result.links) == 1
    """
    if html is None:
        html = """<!DOCTYPE html>
<html><head><title>Test Page</title></head>
<body><h1>Test Page</h1><p>Test content</p></body></html>"""

    if links is None:
        links = []

    if assets is None:
        assets = []

    if not content_hash:
        content_hash = hashlib.sha256(html.encode()).hexdigest()

    return CrawlResult(
        url=url,
        final_url=url,  # For tests, assume no redirect (final_url == url)
        html=html,
        status_code=status_code,
        content_type=content_type,
        links=links,
        assets=assets,
        content_hash=content_hash,
        queue_size=queue_size,
    )


def create_page_checkpoint(
    url: str = "http://example.com/page",
    *,
    content_hash: str = "a" * 64,
    last_scraped: str | None = None,
    status_code: int = 200,
    file_path: str = "output/page.md",
) -> PageCheckpoint:
    """Create a PageCheckpoint instance for testing.

    Factory for creating checkpoint page records.

    Args:
        url: Page URL
        content_hash: SHA-256 hash of page content
        last_scraped: ISO 8601 timestamp (defaults to current time)
        status_code: HTTP status code
        file_path: Output file path

    Returns:
        PageCheckpoint with specified values

    Example:
        >>> checkpoint = create_page_checkpoint(
        ...     url="https://example.com/docs",
        ...     content_hash="abc123...",
        ...     file_path="output/docs.md"
        ... )
        >>> assert checkpoint.url == "https://example.com/docs"
        >>> assert checkpoint.status_code == 200
    """
    if last_scraped is None:
        last_scraped = datetime.now(UTC).isoformat()

    return PageCheckpoint(
        url=url,
        content_hash=content_hash,
        last_scraped=last_scraped,
        status_code=status_code,
        file_path=file_path,
    )


def create_checkpoint_metadata(
    config_name: str = "test-site",
    config_hash: str = "a" * 64,
    *,
    version: int = 1,
    created_at: str | None = None,
    last_updated: str | None = None,
    stats: dict[str, Any] | None = None,
) -> CheckpointMetadata:
    """Create CheckpointMetadata instance for testing.

    Factory for creating checkpoint metadata records.

    Args:
        config_name: Configuration name
        config_hash: SHA-256 hash of configuration
        version: Checkpoint format version
        created_at: ISO 8601 timestamp (defaults to current time)
        last_updated: ISO 8601 timestamp (defaults to current time)
        stats: Crawl statistics dictionary

    Returns:
        CheckpointMetadata with specified values

    Example:
        >>> metadata = create_checkpoint_metadata(
        ...     config_name="docs-site",
        ...     stats={"pages_crawled": 100, "pages_failed": 2}
        ... )
        >>> assert metadata.config_name == "docs-site"
        >>> assert metadata.stats["pages_crawled"] == 100
    """
    now = datetime.now(UTC).isoformat()

    if created_at is None:
        created_at = now

    if last_updated is None:
        last_updated = now

    if stats is None:
        stats = {}

    return CheckpointMetadata(
        version=version,
        config_name=config_name,
        config_hash=config_hash,
        created_at=created_at,
        last_updated=last_updated,
        stats=stats,
    )


@pytest.fixture
async def mock_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create a mock httpx.AsyncClient for testing.

    Provides a properly configured async HTTP client that can be used
    with pytest-httpx's respx.mock decorator for mocking HTTP requests.

    Yields:
        httpx.AsyncClient with sensible test defaults

    Example:
        >>> async def test_something(mock_http_client):
        ...     async with mock_http_client as client:
        ...         response = await client.get("http://example.com")
        ...         assert response.status_code == 200
    """
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    ) as client:
        yield client


@pytest.fixture
def mock_crawler_factory(tmp_path: Path) -> type[Crawler]:
    """Create a factory for mock Crawler instances.

    Returns a Crawler class that can be instantiated with test configurations.
    Note: Actual Crawler instances require async context managers and should be
    created within async test functions.

    Args:
        tmp_path: Pytest tmp_path fixture

    Returns:
        Crawler class for instantiation in tests

    Example:
        >>> async def test_crawler(mock_crawler_factory):
        ...     config = create_basic_config()
        ...     crawler = mock_crawler_factory(config)
        ...     # Use crawler in async context
    """
    return Crawler
