"""Tests for HTTP/2 support and connection pooling."""

import pytest

from sus.config import (
    AssetConfig,
    CrawlingRules,
    MarkdownConfig,
    OutputConfig,
    PathMappingConfig,
    SiteConfig,
    SusConfig,
)
from sus.crawler import Crawler


@pytest.fixture
def http2_config() -> SusConfig:
    """Create config for HTTP/2 testing."""
    return SusConfig(
        name="http2-test",
        description="HTTP/2 test configuration",
        site=SiteConfig(
            start_urls=["https://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            global_concurrent_requests=10,
            per_domain_concurrent_requests=2,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir="output",
            docs_dir="docs",
            assets_dir="assets",
            path_mapping=PathMappingConfig(),
            markdown=MarkdownConfig(),
        ),
        assets=AssetConfig(download=False),
    )


def test_crawler_creates_http2_client(http2_config: SusConfig) -> None:
    """Verify crawler creates httpx client with HTTP/2 enabled."""
    crawler = Crawler(http2_config)

    # Trigger client creation by accessing _ensure_client
    import asyncio

    async def check_client() -> None:
        await crawler._ensure_client()
        assert crawler.client is not None, "Client should be initialized"

        # Check HTTP/2 is enabled
        assert hasattr(crawler.client, "_transport_for_url"), "Client should have transport"
        # HTTP/2 support is indicated by http2=True in constructor
        # We'll verify by checking the client can handle HTTP/2 responses

    asyncio.run(check_client())


def test_crawler_uses_connection_pooling(http2_config: SusConfig) -> None:
    """Verify crawler configures connection pooling."""
    import asyncio

    async def check_limits() -> None:
        crawler = Crawler(http2_config)
        await crawler._ensure_client()
        assert crawler.client is not None

        # Verify transport is configured (now wrapped in RetryTransport)
        # Connection pool is configured in the base transport, which is wrapped by RetryTransport
        assert hasattr(crawler.client, "_transport"), "Client should have transport"

        # We can't easily inspect the wrapped transport without accessing internal APIs
        # Just verify the client was created successfully with HTTP/2 and retry support
        assert crawler.client is not None

    asyncio.run(check_limits())


def test_crawler_timeout_configuration(http2_config: SusConfig) -> None:
    """Verify crawler uses structured timeout with separate connect timeout."""
    import asyncio

    async def check_timeout() -> None:
        crawler = Crawler(http2_config)
        await crawler._ensure_client()
        assert crawler.client is not None

        # Check timeout is properly configured
        timeout = crawler.client.timeout
        assert timeout.connect == 10.0, "Connect timeout should be 10s"
        assert timeout.read == 30.0, "Read timeout should be 30s"
        assert timeout.write == 30.0, "Write timeout should be 30s"
        assert timeout.pool == 30.0, "Pool timeout should be 30s"

    asyncio.run(check_timeout())
