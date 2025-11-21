"""Tests for redirect loop protection."""

import httpx
import pytest
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


def test_max_redirects_default() -> None:
    """Verify max_redirects defaults to 10."""
    rules = CrawlingRules()
    assert rules.max_redirects == 10


def test_max_redirects_configurable() -> None:
    """Verify max_redirects can be customized."""
    rules = CrawlingRules(max_redirects=5)
    assert rules.max_redirects == 5


async def test_crawler_respects_redirect_limit(httpx_mock: HTTPXMock) -> None:
    """Verify crawler stops following redirects at configured limit."""
    config = SusConfig(
        name="redirect-test",
        description="Test redirect limits",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_redirects=2,  # Only follow 2 redirects
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

    # Create redirect chain: /start -> /1 -> /2 -> /3 (exceeds limit of 2)
    httpx_mock.add_response(
        url="http://example.com/start",
        status_code=301,
        headers={"Location": "http://example.com/1"},
    )
    httpx_mock.add_response(
        url="http://example.com/1",
        status_code=301,
        headers={"Location": "http://example.com/2"},
    )
    httpx_mock.add_response(
        url="http://example.com/2",
        status_code=301,
        headers={"Location": "http://example.com/3"},
    )

    async with httpx.AsyncClient(max_redirects=2, follow_redirects=True) as client:
        crawler = Crawler(config, client=client)
        result = await crawler._fetch_page("http://example.com/start", None)

    # Should return None (too many redirects)
    assert result is None
    assert crawler.stats.error_counts.get("TooManyRedirects", 0) == 1


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
async def test_crawler_handles_redirect_loop(httpx_mock: HTTPXMock) -> None:
    """Verify crawler detects circular redirects."""
    config = SusConfig(
        name="redirect-loop-test",
        description="Test redirect loop detection",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_redirects=5,
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

    # Create circular redirect: /a -> /b -> /a (need multiple responses for the loop)
    for _ in range(10):  # Add enough responses to handle the redirect loop
        httpx_mock.add_response(
            url="http://example.com/a",
            status_code=301,
            headers={"Location": "http://example.com/b"},
        )
        httpx_mock.add_response(
            url="http://example.com/b",
            status_code=301,
            headers={"Location": "http://example.com/a"},
        )

    async with httpx.AsyncClient(max_redirects=5, follow_redirects=True) as client:
        crawler = Crawler(config, client=client)
        result = await crawler._fetch_page("http://example.com/a", None)

    # Should catch the loop and return None
    assert result is None
    assert crawler.stats.error_counts.get("TooManyRedirects", 0) == 1
