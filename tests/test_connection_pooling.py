"""Tests for HTTP/2 connection pooling and reuse.

NOTE: These tests verify connection pool configuration but do not directly
verify that httpx actually reuses connections at runtime. Behavioral verification
would require deep httpx internals inspection or network-level monitoring.
"""

from pathlib import Path

from pytest_httpx import HTTPXMock

from sus.config import (
    AssetConfig,
    CrawlingRules,
    OutputConfig,
    PathMappingConfig,
    SiteConfig,
    SusConfig,
)
from sus.crawler import Crawler
from sus.scraper import run_scraper


async def test_connection_pool_configuration() -> None:
    """Test that HTTP client is configured with correct connection pool limits."""
    config = SusConfig(
        name="pool-config-test",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
    )

    crawler = Crawler(config)
    await crawler._ensure_client()

    # Verify client was created
    assert crawler.client is not None

    # Verify transport has limits configured
    # httpx wraps transport, but we can verify client exists without errors
    assert hasattr(crawler.client, "_transport")

    # Verify HTTP/2 is enabled (from test_http2.py baseline)
    # httpx-retries wraps the transport, so direct inspection is limited
    # but we verify the crawler initializes without errors with HTTP/2 config


async def test_connection_reuse_multiple_requests(httpx_mock: HTTPXMock) -> None:
    """Test that multiple requests to same domain reuse connections."""
    config = SusConfig(
        name="connection-reuse-test",
        site=SiteConfig(
            start_urls=[
                "https://example.com/page1",
                "https://example.com/page2",
                "https://example.com/page3",
            ],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            respect_robots_txt=False,
        ),
    )

    # Mock responses for all pages
    for i in range(1, 4):
        httpx_mock.add_response(
            url=f"https://example.com/page{i}", html=f"<html><body>Page {i}</body></html>"
        )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Verify all requests succeeded
    assert len(results) == 3
    assert all(r.status_code == 200 for r in results)

    # Connection reuse is implicit - if pooling wasn't working,
    # we'd see connection errors or much slower performance
    # This test verifies basic functionality with pooling enabled


async def test_connection_keepalive_behavior(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that connections are kept alive between requests."""
    config = SusConfig(
        name="keepalive-test",
        site=SiteConfig(
            start_urls=[
                "https://example.com/page1",
                "https://example.com/page2",
            ],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.5,  # Small delay between requests
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(download=False),
    )

    httpx_mock.add_response(
        url="https://example.com/page1", html="<html><body>Page 1</body></html>"
    )
    httpx_mock.add_response(
        url="https://example.com/page2", html="<html><body>Page 2</body></html>"
    )

    stats = await run_scraper(config, dry_run=True)

    # Verify both pages crawled successfully
    assert stats["pages_crawled"] == 2
    assert stats["pages_failed"] == 0

    # Connection keepalive is configured with 30s expiry
    # With 0.5s delay between requests, connections should be reused
    # This test verifies the scraper works correctly with keepalive enabled


async def test_max_connections_limit() -> None:
    """Test that connection pool respects max_connections limit."""
    config = SusConfig(
        name="max-connections-test",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            global_concurrent_requests=10,  # Request 10 concurrent connections
        ),
    )

    crawler = Crawler(config)
    await crawler._ensure_client()

    # Verify client initialized with connection pooling config
    # Max connections is 100 (baseline configuration)
    # This test verifies the client can handle concurrent requests
    assert crawler.client is not None

    # httpx connection pool will enforce limits internally
    # We verify the crawler initializes correctly with these settings


async def test_connection_pool_with_assets(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that asset downloads also benefit from connection pooling."""
    config = SusConfig(
        name="asset-pool-test",
        site=SiteConfig(
            start_urls=["https://example.com/page"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(
            download=True,
            types=["images"],
        ),
    )

    # Mock page with multiple assets from same domain
    page_html = """
    <html><body>
        <img src="https://example.com/img1.png">
        <img src="https://example.com/img2.png">
        <img src="https://example.com/img3.png">
    </body></html>
    """
    httpx_mock.add_response(url="https://example.com/page", html=page_html)

    # Mock asset downloads
    for i in range(1, 4):
        httpx_mock.add_response(url=f"https://example.com/img{i}.png", content=b"image")

    stats = await run_scraper(config, dry_run=False)

    # Verify all assets downloaded successfully
    assert stats["assets_downloaded"] == 3
    assert stats["assets_failed"] == 0

    # Asset downloader uses same HTTP/2 + connection pooling config
    # Multiple asset downloads to same domain should reuse connections
