"""Pytest fixtures for SUS scraper tests."""

from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from sus.config import (
    AssetConfig,
    CrawlingRules,
    MarkdownConfig,
    OutputConfig,
    PathMappingConfig,
    PathPattern,
    SiteConfig,
    SusConfig,
)


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
