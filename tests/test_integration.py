"""Integration tests for SUS scraper."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from sus.assets import AssetDownloader
from sus.config import (
    AssetConfig,
    CrawlingRules,
    MarkdownConfig,
    OutputConfig,
    PathMappingConfig,
    PathPattern,
    SiteConfig,
    SusConfig,
    load_config,
)
from sus.converter import ContentConverter
from sus.crawler import RateLimiter
from sus.outputs import OutputManager
from sus.rules import LinkExtractor, RulesEngine, URLNormalizer


def test_project_structure() -> None:
    """Verify src/sus/ directory and modules exist."""
    src_dir = Path("src/sus")
    assert src_dir.exists()

    modules = [
        "__init__.py",
        "__main__.py",
        "cli.py",
        "config.py",
        "crawler.py",
        "rules.py",
        "converter.py",
        "outputs.py",
        "assets.py",
        "utils.py",
        "exceptions.py",
    ]
    for module in modules:
        assert (src_dir / module).exists(), f"{module} missing"


def test_example_configs_exist() -> None:
    """Verify all example config files exist."""
    examples = ["aptly.yaml", "simple-docs.yaml", "advanced-docs.yaml"]
    for config in examples:
        assert (Path("examples") / config).exists(), f"{config} missing"


def test_pyproject_configuration() -> None:
    """Verify pyproject.toml is configured correctly."""
    pyproject = Path("pyproject.toml")
    assert pyproject.exists()
    content = pyproject.read_text()
    assert 'name = "sus"' in content
    assert "httpx" in content
    assert "pydantic" in content


@pytest.mark.parametrize(
    "config_path,expected_name",
    [
        ("examples/aptly.yaml", "aptly-docs"),
        ("examples/simple-docs.yaml", "flask-docs"),
        ("examples/advanced-docs.yaml", "django-docs"),
    ],
)
def test_load_yaml_configs(config_path: str, expected_name: str) -> None:
    """Verify YAML configs load and validate."""
    config = load_config(Path(config_path))
    assert config.name == expected_name
    assert len(config.site.start_urls) > 0
    assert len(config.site.allowed_domains) > 0


def test_config_validation() -> None:
    """Verify config fields validate correctly."""
    config = load_config(Path("examples/aptly.yaml"))
    assert config.crawling.delay_between_requests == 0.5
    assert config.crawling.global_concurrent_requests == 8
    assert config.crawling.max_retries == 3
    assert config.crawling.retry_backoff == 2.0


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        (PathPattern(pattern=r"^/doc/", type="regex"), "/doc/overview", True),
        (PathPattern(pattern=r"^/doc/", type="regex"), "/blog/post", False),
        (PathPattern(pattern="*.html", type="glob"), "index.html", True),
        (PathPattern(pattern="*.html", type="glob"), "index.md", False),
        (PathPattern(pattern="/docs/", type="prefix"), "/docs/guide", True),
        (PathPattern(pattern="/docs/", type="prefix"), "/api/guide", False),
    ],
)
def test_path_pattern_matching(pattern: PathPattern, path: str, expected: bool) -> None:
    """Verify PathPattern regex/glob/prefix matching."""
    assert pattern.matches(path) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("HTTP://Example.COM:80/Path", "http://example.com/Path"),
        ("https://example.com/path#section", "https://example.com/path"),
    ],
)
def test_url_normalization(url: str, expected: str) -> None:
    """Verify URL normalization (lowercase, strip ports, remove fragments)."""
    assert URLNormalizer.normalize_url(url) == expected


@pytest.mark.parametrize(
    "url,is_safe",
    [
        ("http://example.com", True),
        ("https://example.com", True),
        ("mailto:user@example.com", False),
        ("javascript:alert(1)", False),
    ],
)
def test_dangerous_url_filtering(url: str, is_safe: bool) -> None:
    """Verify dangerous URL schemes are blocked."""
    assert URLNormalizer.filter_dangerous_schemes(url) == is_safe


def test_query_parameter_handling() -> None:
    """Verify query parameter strip/preserve strategies."""
    url = "http://example.com/path?foo=bar"
    assert "?" not in URLNormalizer.handle_query_parameters(url, "strip")
    assert "?" in URLNormalizer.handle_query_parameters(url, "preserve")


def test_rules_engine() -> None:
    """Verify RulesEngine domain/depth/pattern filtering."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["http://example.com/docs/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            include_patterns=[PathPattern(pattern="^/docs/", type="regex")],
            exclude_patterns=[PathPattern(pattern="*.pdf", type="glob")],
            depth_limit=2,
        ),
    )
    engine = RulesEngine(config)

    # Domain filtering
    assert engine._is_allowed_domain("http://example.com/page")
    assert not engine._is_allowed_domain("http://other.com/page")

    # Depth tracking
    assert engine._get_depth("http://example.com/docs/", None) == 0
    assert engine._get_depth("http://example.com/docs/p1", "http://example.com/docs/") == 1

    # Pattern filtering
    assert engine.should_follow("http://example.com/docs/guide", None)
    assert not engine.should_follow("http://example.com/docs/manual.pdf", None)
    assert not engine.should_follow("http://example.com/blog/post", None)


def test_link_extraction() -> None:
    """Verify LinkExtractor parses HTML and filters dangerous schemes."""
    extractor = LinkExtractor(["a[href]"])
    html = """
    <html><body>
        <a href="/page1">Page 1</a>
        <a href="http://example.com/page2">Page 2</a>
        <a href="mailto:user@example.com">Email</a>
        <a href="javascript:alert(1)">JS</a>
    </body></html>
    """
    links = extractor.extract_links(html, "http://example.com/")

    assert "http://example.com/page1" in links
    assert "http://example.com/page2" in links
    assert not any("mailto" in link for link in links)
    assert not any("javascript" in link for link in links)


@pytest.mark.asyncio
async def test_rate_limiter() -> None:
    """Verify token bucket rate limiter handles bursts correctly."""
    limiter = RateLimiter(rate=10.0, burst=3)
    start = asyncio.get_event_loop().time()

    # First 3 requests should be instant (burst)
    for _ in range(3):
        await limiter.acquire()
    burst_time = asyncio.get_event_loop().time() - start
    assert burst_time < 0.1

    # 4th request should wait
    await limiter.acquire()
    total_time = asyncio.get_event_loop().time() - start
    assert total_time >= 0.1


def test_html_to_markdown_conversion() -> None:
    """Verify HTML converts to Markdown with frontmatter."""
    config = MarkdownConfig(add_frontmatter=True, frontmatter_fields=["title", "url", "scraped_at"])
    converter = ContentConverter(config)

    html = """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Hello World</h1>
            <p>This is <strong>bold</strong> and <em>italic</em>.</p>
            <ul><li>Item 1</li><li>Item 2</li></ul>
        </body>
    </html>
    """
    markdown = converter.convert(html, "https://example.com/test")

    assert "---" in markdown  # Frontmatter
    assert "title:" in markdown
    assert "url: https://example.com/test" in markdown
    assert "Hello World" in markdown
    assert "bold" in markdown or "**bold**" in markdown


def test_output_manager() -> None:
    """Verify OutputManager maps URLs to file paths correctly."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com/docs/"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(
                base_dir=tmpdir,
                docs_dir="docs",
                assets_dir="assets",
                path_mapping=PathMappingConfig(
                    mode="auto",
                    strip_prefix="/docs",
                    index_file="index.md",
                ),
            ),
        )
        manager = OutputManager(config, dry_run=False)

        # Verify directories created
        assert manager.docs_dir.exists()
        assert manager.assets_dir.exists()

        # Test URL to path mapping
        doc_path = manager.get_doc_path("https://example.com/docs/guide/install/")
        assert doc_path.name == "index.md"
        assert "guide" in str(doc_path)
        assert "install" in str(doc_path)

        doc_path2 = manager.get_doc_path("https://example.com/docs/overview")
        assert doc_path2.suffix == ".md"
        assert "overview" in str(doc_path2)

        # Test asset path mapping
        asset_path = manager.get_asset_path("https://example.com/img/logo.png")
        assert asset_path.name == "logo.png"
        assert "img" in str(asset_path)


def test_link_rewriting() -> None:
    """Verify link rewriting converts absolute URLs to relative paths."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com/docs/"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(
                base_dir=tmpdir,
                path_mapping=PathMappingConfig(strip_prefix="/docs"),
            ),
        )
        manager = OutputManager(config, dry_run=False)

        markdown = (
            "[Guide](https://example.com/docs/guide) ![Logo](https://example.com/img/logo.png)"
        )
        rewritten = manager.rewrite_links(markdown, "https://example.com/docs/")

        # Links should be rewritten (exact format may vary)
        assert "guide" in rewritten
        assert "assets/img/logo.png" in rewritten or "../assets/img/logo.png" in rewritten


def test_output_manager_with_null_strip_prefix() -> None:
    """Verify OutputManager handles strip_prefix=None correctly.

    Regression test for bug where null prefix caused ValueError during link rewriting
    due to absolute paths not being stripped of leading slashes.
    """
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(start_urls=["https://example.com/"], allowed_domains=["example.com"]),
            output=OutputConfig(
                base_dir=tmpdir,
                path_mapping=PathMappingConfig(strip_prefix=None, index_file="index.md"),
            ),
        )
        manager = OutputManager(config, dry_run=False)

        # Test URL to path mapping with null prefix
        # Path should preserve full URL structure but without leading slash
        doc_path = manager.get_doc_path("https://example.com/docs/guide/")
        assert doc_path.name == "index.md"
        assert "docs" in str(doc_path)
        assert "guide" in str(doc_path)

        # Critical: Path must be relative to docs_dir (not an absolute filesystem path)
        assert doc_path.is_relative_to(manager.docs_dir), (
            f"Path {doc_path} should be relative to {manager.docs_dir}"
        )

        # Test with non-directory URL
        doc_path2 = manager.get_doc_path("https://example.com/docs/page")
        assert doc_path2.suffix == ".md"
        assert "docs" in str(doc_path2)
        assert doc_path2.is_relative_to(manager.docs_dir)

        # Test link rewriting with null prefix (should not raise ValueError)
        markdown = "[Page](https://example.com/docs/page) ![Logo](https://example.com/img/logo.png)"
        try:
            rewritten = manager.rewrite_links(markdown, "https://example.com/docs/")
            # Should succeed without ValueError
            assert "Page" in rewritten
            assert "Logo" in rewritten
        except ValueError as e:
            pytest.fail(f"Link rewriting with null prefix should not raise ValueError: {e}")


@pytest.mark.asyncio
async def test_asset_downloader() -> None:
    """Verify AssetDownloader respects download config."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(start_urls=["https://example.com/"], allowed_domains=["example.com"]),
            output=OutputConfig(base_dir=tmpdir),
            assets=AssetConfig(download=False, types=["image"], rewrite_paths=True),
        )
        manager = OutputManager(config, dry_run=False)
        downloader = AssetDownloader(config, manager)

        # Test with download disabled
        stats = await downloader.download_all([])
        assert stats.downloaded == 0


@pytest.mark.asyncio
async def test_full_integration_pipeline() -> None:
    """Verify all components integrate correctly end-to-end."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="integration-test",
            site=SiteConfig(
                start_urls=["https://example.com/docs/"],
                allowed_domains=["example.com"],
            ),
            crawling=CrawlingRules(
                include_patterns=[PathPattern(pattern="^/docs/", type="regex")],
                delay_between_requests=0.01,
                global_concurrent_requests=2,
                max_retries=1,
            ),
            output=OutputConfig(
                base_dir=tmpdir,
                path_mapping=PathMappingConfig(strip_prefix="/docs"),
                markdown=MarkdownConfig(add_frontmatter=True),
            ),
            assets=AssetConfig(download=False),
        )

        # Initialize components
        output_manager = OutputManager(config, dry_run=False)
        converter = ContentConverter(config.output.markdown)
        rules_engine = RulesEngine(config)
        link_extractor = LinkExtractor(config.crawling.link_selectors)

        # Verify integration
        assert rules_engine.should_follow("https://example.com/docs/page1", None)
        assert not rules_engine.should_follow("https://example.com/blog/post", None)

        test_html = '<html><body><a href="/docs/page1">Page 1</a></body></html>'
        links = link_extractor.extract_links(test_html, "https://example.com/docs/")
        assert len(links) > 0

        # Test conversion pipeline
        sample_html = """
        <html>
            <head><title>Integration Test</title></head>
            <body><h1>Integration Test</h1><p>Testing pipeline.</p></body>
        </html>
        """
        markdown = converter.convert(sample_html, "https://example.com/docs/page1")
        assert "Integration Test" in markdown
        assert "title: Integration Test" in markdown

        # Verify file path mapping
        file_path = output_manager.get_doc_path("https://example.com/docs/page1")
        assert file_path.suffix == ".md"

        # Write and verify
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(markdown)
        assert file_path.exists()
        assert "Integration Test" in file_path.read_text()
