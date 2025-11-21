"""Tests for file size limit enforcement."""

import httpx
import pytest
from pydantic import ValidationError
from pytest_httpx import HTTPXMock

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


def test_max_page_size_default() -> None:
    """Verify max_page_size_mb defaults to 10 MB."""
    rules = CrawlingRules()
    assert rules.max_page_size_mb == 10.0


def test_max_asset_size_default() -> None:
    """Verify max_asset_size_mb defaults to 50 MB."""
    rules = CrawlingRules()
    assert rules.max_asset_size_mb == 50.0


def test_max_page_size_can_be_disabled() -> None:
    """Verify max_page_size_mb can be set to None for unlimited."""
    rules = CrawlingRules(max_page_size_mb=None)
    assert rules.max_page_size_mb is None


def test_max_page_size_validation() -> None:
    """Verify max_page_size_mb must be >= 0.1 MB if set."""
    # Valid: >= 0.1 MB
    rules = CrawlingRules(max_page_size_mb=0.1)
    assert rules.max_page_size_mb == 0.1

    # Invalid: < 0.1 MB should raise validation error
    with pytest.raises(ValidationError):
        CrawlingRules(max_page_size_mb=0.05)


async def test_crawler_skips_large_pages(httpx_mock: HTTPXMock) -> None:
    """Verify crawler skips pages exceeding max_page_size_mb."""
    config = SusConfig(
        name="size-limit-test",
        description="Test file size limits",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_page_size_mb=1.0,  # 1 MB limit
            delay_between_requests=0.0,
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

    # Mock response with Content-Length: 5 MB (exceeds 1 MB limit)
    httpx_mock.add_response(
        url="http://example.com/huge-page.html",
        headers={"Content-Length": str(5 * 1024 * 1024)},  # 5 MB
        text="<html><body>Huge page</body></html>",
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        result = await crawler._fetch_page("http://example.com/huge-page.html", None)

    # Should return None (skipped due to size)
    assert result is None
    assert crawler.stats.error_counts.get("FileTooLarge", 0) == 1


async def test_crawler_handles_invalid_content_length(httpx_mock: HTTPXMock) -> None:
    """Verify malformed Content-Length doesn't crash crawler."""
    config = SusConfig(
        name="invalid-content-length-test",
        description="Test invalid Content-Length handling",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_page_size_mb=1.0,  # 1 MB limit
            delay_between_requests=0.0,
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

    # Mock responses with various invalid Content-Length headers
    httpx_mock.add_response(
        url="http://example.com/page1",
        headers={"Content-Type": "text/html", "Content-Length": "invalid"},  # Non-numeric
        text="<html><body>Page content 1</body></html>",
    )
    httpx_mock.add_response(
        url="http://example.com/page2",
        headers={"Content-Type": "text/html", "Content-Length": "chunked"},  # Server-side encoding
        text="<html><body>Page content 2</body></html>",
    )
    httpx_mock.add_response(
        url="http://example.com/page3",
        headers={"Content-Type": "text/html", "Content-Length": "-1"},  # Negative value
        text="<html><body>Page content 3</body></html>",
    )
    httpx_mock.add_response(
        url="http://example.com/page4",
        headers={"Content-Type": "text/html", "Content-Length": "1.5"},  # Float value
        text="<html><body>Page content 4</body></html>",
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)

        # Should not crash - proceeds with download despite invalid headers
        result1 = await crawler._fetch_page("http://example.com/page1", None)
        assert result1 is not None  # Successfully downloaded
        assert result1.html == "<html><body>Page content 1</body></html>"

        result2 = await crawler._fetch_page("http://example.com/page2", None)
        assert result2 is not None  # Successfully downloaded
        assert result2.html == "<html><body>Page content 2</body></html>"

        result3 = await crawler._fetch_page("http://example.com/page3", None)
        assert result3 is not None  # Successfully downloaded
        assert result3.html == "<html><body>Page content 3</body></html>"

        result4 = await crawler._fetch_page("http://example.com/page4", None)
        assert result4 is not None  # Successfully downloaded
        assert result4.html == "<html><body>Page content 4</body></html>"

    # No FileTooLarge errors should be counted (all invalid headers were skipped)
    assert crawler.stats.error_counts.get("FileTooLarge", 0) == 0
