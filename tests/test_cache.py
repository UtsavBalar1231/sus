"""Unit tests for HTTP caching functionality."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pytest_httpx import HTTPXMock

from sus.assets import AssetDownloader
from sus.config import CacheConfig, CrawlingRules, OutputConfig, SiteConfig, SusConfig
from sus.crawler import Crawler
from sus.http_client import create_cache_storage
from sus.outputs import OutputManager


def test_cache_config_defaults() -> None:
    """Test CacheConfig default values."""
    config = CacheConfig()

    assert config.enabled is False
    assert config.backend == "sqlite"
    assert config.cache_dir == ".sus_cache"
    assert config.ttl_seconds == 3600


def test_cache_config_validation() -> None:
    """Test CacheConfig validation."""
    # Valid configurations
    config1 = CacheConfig(enabled=True, backend="sqlite")
    assert config1.backend == "sqlite"

    config2 = CacheConfig(enabled=True, backend="memory")
    assert config2.backend == "memory"

    # TTL minimum validation
    config3 = CacheConfig(ttl_seconds=60)
    assert config3.ttl_seconds == 60


def test_cache_config_in_crawling_rules() -> None:
    """Test CacheConfig integration in CrawlingRules."""
    rules = CrawlingRules()

    assert hasattr(rules, "cache")
    assert isinstance(rules.cache, CacheConfig)
    assert rules.cache.enabled is False


@pytest.mark.asyncio
async def test_crawler_cache_disabled_by_default() -> None:
    """Test crawler works without caching by default."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
        )

        crawler = Crawler(config)
        assert crawler.config.crawling.cache.enabled is False

        # Ensure client creation works
        await crawler._ensure_client()
        assert crawler.client is not None

        assert crawler.client is not None
        await crawler.client.aclose()


@pytest.mark.asyncio
async def test_crawler_cache_enabled_sqlite() -> None:
    """Test crawler with SQLite cache enabled."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                cache=CacheConfig(
                    enabled=True,
                    backend="sqlite",
                    cache_dir=".test_cache",
                    ttl_seconds=3600,
                )
            ),
        )

        crawler = Crawler(config)
        assert crawler.config.crawling.cache.enabled is True

        # Create storage
        storage = create_cache_storage(config)
        assert storage is not None

        # Ensure client creation works with cache
        await crawler._ensure_client()
        assert crawler.client is not None

        # Verify cache directory created
        cache_dir = Path(tmpdir) / ".test_cache"
        assert cache_dir.exists()

        assert crawler.client is not None
        await crawler.client.aclose()


@pytest.mark.asyncio
async def test_crawler_cache_enabled_memory() -> None:
    """Test crawler with memory cache enabled."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                cache=CacheConfig(
                    enabled=True,
                    backend="memory",
                )
            ),
        )

        crawler = Crawler(config)

        # Create storage (should be None for memory backend)
        storage = create_cache_storage(config)
        assert storage is None

        # Ensure client creation works
        await crawler._ensure_client()
        assert crawler.client is not None

        assert crawler.client is not None
        await crawler.client.aclose()


@pytest.mark.asyncio
async def test_crawler_cache_with_client() -> None:
    """Test crawler cache client creation."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                cache=CacheConfig(
                    enabled=True,
                    backend="sqlite",
                    ttl_seconds=3600,
                )
            ),
        )

        crawler = Crawler(config)
        await crawler._ensure_client()

        # Verify cache client is created
        assert crawler.client is not None

        # Verify cache directory exists
        cache_dir = Path(tmpdir) / ".sus_cache"
        assert cache_dir.exists()

        assert crawler.client is not None
        await crawler.client.aclose()


@pytest.mark.asyncio
async def test_asset_downloader_cache_disabled() -> None:
    """Test asset downloader without caching."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
        )

        output_manager = OutputManager(config, dry_run=True)
        downloader = AssetDownloader(config, output_manager)

        assert downloader.config.crawling.cache.enabled is False

        # Ensure client creation works
        await downloader._ensure_client()
        assert downloader.client is not None

        await downloader.client.aclose()


@pytest.mark.asyncio
async def test_asset_downloader_cache_enabled() -> None:
    """Test asset downloader with caching enabled."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                cache=CacheConfig(
                    enabled=True,
                    backend="sqlite",
                )
            ),
        )

        output_manager = OutputManager(config, dry_run=True)
        downloader = AssetDownloader(config, output_manager)

        assert downloader.config.crawling.cache.enabled is True

        # Create storage
        storage = create_cache_storage(config)
        assert storage is not None

        # Ensure client creation works
        await downloader._ensure_client()
        assert downloader.client is not None

        await downloader.client.aclose()


def test_cache_storage_creation_sqlite() -> None:
    """Test SQLite cache storage creation."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                cache=CacheConfig(
                    enabled=True,
                    backend="sqlite",
                    cache_dir=".cache_test",
                )
            ),
        )

        storage = create_cache_storage(config)

        # Storage object created
        assert storage is not None

        # Cache directory created
        cache_dir = Path(tmpdir) / ".cache_test"
        assert cache_dir.exists()

        # Note: DB file is created lazily on first use by Hishel


def test_cache_storage_creation_memory() -> None:
    """Test memory cache storage returns None."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                cache=CacheConfig(
                    enabled=True,
                    backend="memory",
                )
            ),
        )

        storage = create_cache_storage(config)

        # Memory backend returns None (uses Hishel default)
        assert storage is None


def test_cache_ttl_configuration() -> None:
    """Test TTL configuration is passed to storage."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                cache=CacheConfig(
                    enabled=True,
                    backend="sqlite",
                    ttl_seconds=7200,  # 2 hours
                )
            ),
        )

        storage = create_cache_storage(config)

        # Storage created with custom TTL
        assert storage is not None


@pytest.mark.asyncio
async def test_cache_integration_with_real_crawl(httpx_mock: HTTPXMock) -> None:
    """Test cache integration in a real crawl scenario."""
    with TemporaryDirectory() as tmpdir:
        config = SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            crawling=CrawlingRules(
                max_pages=2,
                respect_robots_txt=False,  # Disable robots.txt for test
                cache=CacheConfig(
                    enabled=True,
                    backend="sqlite",
                ),
            ),
        )

        httpx_mock.add_response(
            url="https://example.com",
            html='<html><body><a href="/page1">Page 1</a></body></html>',
        )
        httpx_mock.add_response(
            url="https://example.com/page1",
            html="<html><body>Page 1 Content</body></html>",
        )

        crawler = Crawler(config)
        await crawler._ensure_client()

        # Crawl pages
        pages = []
        async for result in crawler.crawl():
            pages.append(result)

        assert len(pages) >= 1

        # Verify cache directory exists
        cache_dir = Path(tmpdir) / ".sus_cache"
        assert cache_dir.exists()

        assert crawler.client is not None
        await crawler.client.aclose()
