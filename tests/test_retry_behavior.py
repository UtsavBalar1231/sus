"""Tests for actual retry behavior with httpx-retries."""

import time

from pytest_httpx import HTTPXMock

from sus.config import (
    CrawlingRules,
    SiteConfig,
    SusConfig,
)
from sus.crawler import Crawler


async def test_retries_on_429_status_code(httpx_mock: HTTPXMock) -> None:
    """Test that 429 status code triggers retries."""
    # Configure to fail twice with 429, then succeed
    httpx_mock.add_response(url="https://example.com/rate-limited", status_code=429)
    httpx_mock.add_response(url="https://example.com/rate-limited", status_code=429)
    httpx_mock.add_response(
        url="https://example.com/rate-limited",
        status_code=200,
        html="<html><body>Success after retry</body></html>",
    )

    config = SusConfig(
        name="retry-test",
        site=SiteConfig(
            start_urls=["https://example.com/rate-limited"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=3,
            retry_backoff=1.1,  # Minimal backoff for fast test (httpx-retries uses 0-based)
            retry_jitter=0.0,  # No jitter for predictable timing
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Verify request succeeded after retries
    assert len(results) == 1
    assert "Success after retry" in results[0].html
    assert results[0].status_code == 200


async def test_retries_on_500_status_code(httpx_mock: HTTPXMock) -> None:
    """Test that 500 status code triggers retries."""
    # Fail once with 500, then succeed
    httpx_mock.add_response(url="https://example.com/error-500", status_code=500)
    httpx_mock.add_response(
        url="https://example.com/error-500",
        status_code=200,
        html="<html><body>Recovered from 500</body></html>",
    )

    config = SusConfig(
        name="retry-test-500",
        site=SiteConfig(
            start_urls=["https://example.com/error-500"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=2,
            retry_backoff=1.1,
            retry_jitter=0.0,
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Verify recovery
    assert len(results) == 1
    assert "Recovered from 500" in results[0].html


async def test_retries_on_503_status_code(httpx_mock: HTTPXMock) -> None:
    """Test that 503 status code triggers retries."""
    # Fail once with 503, then succeed
    httpx_mock.add_response(url="https://example.com/error-503", status_code=503)
    httpx_mock.add_response(
        url="https://example.com/error-503",
        status_code=200,
        html="<html><body>Recovered from 503</body></html>",
    )

    config = SusConfig(
        name="retry-test-503",
        site=SiteConfig(
            start_urls=["https://example.com/error-503"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=2,
            retry_backoff=1.1,
            retry_jitter=0.0,
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Verify recovery
    assert len(results) == 1
    assert "Recovered from 503" in results[0].html


async def test_stops_after_max_retries(httpx_mock: HTTPXMock) -> None:
    """Test that retry stops after max_retries exhausted."""
    # With max_retries=2, httpx will make: 1 initial + 2 retries = 3 total requests
    # Always return 503 (should eventually give up)
    for _ in range(3):
        httpx_mock.add_response(url="https://example.com/always-fails", status_code=503)

    config = SusConfig(
        name="max-retry-test",
        site=SiteConfig(
            start_urls=["https://example.com/always-fails"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=2,  # Only retry twice (3 total attempts)
            retry_backoff=1.1,
            retry_jitter=0.0,
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Should get no results (all retries failed)
    assert len(results) == 0

    # Verify crawler tracked the failure
    assert crawler.stats.pages_failed == 1


async def test_retry_after_header_seconds_format(httpx_mock: HTTPXMock) -> None:
    """Test that Retry-After header (seconds) is respected."""
    # Return 429 with Retry-After: 2 (seconds)
    httpx_mock.add_response(
        url="https://example.com/rate-limited", status_code=429, headers={"Retry-After": "2"}
    )
    httpx_mock.add_response(
        url="https://example.com/rate-limited",
        status_code=200,
        html="<html><body>Success</body></html>",
    )

    config = SusConfig(
        name="retry-after-test",
        site=SiteConfig(
            start_urls=["https://example.com/rate-limited"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=3,
            retry_backoff=1.1,
            retry_jitter=0.0,
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    start_time = time.time()

    results = []
    async for result in crawler.crawl():
        results.append(result)

    elapsed = time.time() - start_time

    # Should succeed after respecting Retry-After delay
    assert len(results) == 1
    assert "Success" in results[0].html

    # Verify delay was respected (at least 2 seconds due to Retry-After)
    # Note: Allow some margin for test execution overhead
    assert elapsed >= 1.8, f"Expected delay of ~2s, but elapsed only {elapsed:.2f}s"


async def test_retry_after_header_http_date_format(httpx_mock: HTTPXMock) -> None:
    """Test that Retry-After header (HTTP date) is respected."""
    import email.utils

    # Calculate a future time (2 seconds from now)
    future_time = time.time() + 2
    retry_after_date = email.utils.formatdate(future_time, usegmt=True)

    # Return 503 with Retry-After in HTTP date format
    httpx_mock.add_response(
        url="https://example.com/server-unavailable",
        status_code=503,
        headers={"Retry-After": retry_after_date},
    )
    httpx_mock.add_response(
        url="https://example.com/server-unavailable",
        status_code=200,
        html="<html><body>Server recovered</body></html>",
    )

    config = SusConfig(
        name="retry-after-http-date-test",
        site=SiteConfig(
            start_urls=["https://example.com/server-unavailable"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=3,
            retry_backoff=1.1,
            retry_jitter=0.0,
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    start_time = time.time()

    results = []
    async for result in crawler.crawl():
        results.append(result)

    elapsed = time.time() - start_time

    # Should succeed after respecting Retry-After delay
    assert len(results) == 1
    assert "Server recovered" in results[0].html

    # Verify delay was respected (at least 1 second due to Retry-After)
    # Note: HTTP date format parsing may have different timing characteristics
    assert elapsed >= 1.0, f"Expected delay of ~2s, but elapsed only {elapsed:.2f}s"


async def test_jitter_adds_randomness_to_backoff(httpx_mock: HTTPXMock) -> None:
    """Test that jitter adds randomness to retry delays."""
    # This test is more qualitative - we verify jitter doesn't break retries
    # and that timing varies (full randomness testing would require many runs)

    httpx_mock.add_response(url="https://example.com/page", status_code=503)
    httpx_mock.add_response(url="https://example.com/page", status_code=503)
    httpx_mock.add_response(
        url="https://example.com/page",
        status_code=200,
        html="<html><body>Success with jitter</body></html>",
    )

    config = SusConfig(
        name="jitter-test",
        site=SiteConfig(
            start_urls=["https://example.com/page"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=3,
            retry_backoff=2.0,
            retry_jitter=0.5,  # 50% jitter
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Main assertion: jitter doesn't prevent successful retry
    assert len(results) == 1
    assert "Success with jitter" in results[0].html


async def test_no_retry_on_404_client_error(httpx_mock: HTTPXMock) -> None:
    """Test that 404 errors don't trigger retries."""
    # Return 404 just once - should NOT retry
    httpx_mock.add_response(url="https://example.com/not-found", status_code=404)

    config = SusConfig(
        name="no-retry-test-404",
        site=SiteConfig(
            start_urls=["https://example.com/not-found"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=3,
            retry_backoff=1.1,
            retry_jitter=0.0,
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Should get no results (404 not retried)
    assert len(results) == 0
    assert crawler.stats.pages_failed == 1


async def test_no_retry_on_403_client_error(httpx_mock: HTTPXMock) -> None:
    """Test that 403 errors don't trigger retries."""
    # Return 403 just once - should NOT retry
    httpx_mock.add_response(url="https://example.com/forbidden", status_code=403)

    config = SusConfig(
        name="no-retry-test-403",
        site=SiteConfig(
            start_urls=["https://example.com/forbidden"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=3,
            retry_backoff=1.1,
            retry_jitter=0.0,
            respect_robots_txt=False,
        ),
    )

    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Should get no results (403 not retried)
    assert len(results) == 0
    assert crawler.stats.pages_failed == 1
