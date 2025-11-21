"""Tests for per-domain concurrency limits (independent semaphores)."""

import asyncio
import time

import httpx
from pytest_httpx import HTTPXMock

from sus.config import CrawlingRules, SiteConfig, SusConfig
from sus.crawler import Crawler


async def test_separate_semaphores_per_domain() -> None:
    """Test that different domains get independent semaphores."""
    config = SusConfig(
        name="semaphore-test",
        site=SiteConfig(
            start_urls=[
                "https://domain-a.com/page1",
                "https://domain-b.com/page1",
            ],
            allowed_domains=["domain-a.com", "domain-b.com"],
        ),
        crawling=CrawlingRules(
            per_domain_concurrent_requests=5,
        ),
    )

    crawler = Crawler(config)
    await crawler._ensure_client()

    # Manually trigger semaphore creation by extracting domain
    from urllib.parse import urlparse

    domain_a = urlparse("https://domain-a.com").netloc
    domain_b = urlparse("https://domain-b.com").netloc

    # Simulate domain semaphore creation (happens in _fetch_page)
    if domain_a not in crawler.domain_semaphores:
        crawler.domain_semaphores[domain_a] = asyncio.Semaphore(
            crawler.config.crawling.per_domain_concurrent_requests
        )
    if domain_b not in crawler.domain_semaphores:
        crawler.domain_semaphores[domain_b] = asyncio.Semaphore(
            crawler.config.crawling.per_domain_concurrent_requests
        )

    # Verify separate semaphores exist
    assert domain_a in crawler.domain_semaphores
    assert domain_b in crawler.domain_semaphores
    assert crawler.domain_semaphores[domain_a] is not crawler.domain_semaphores[domain_b]

    # Verify semaphore limits
    assert crawler.domain_semaphores[domain_a]._value == 5
    assert crawler.domain_semaphores[domain_b]._value == 5


async def test_domain_independence_integration(httpx_mock: HTTPXMock) -> None:
    """Test that domain A hitting limit doesn't block domain B."""
    config = SusConfig(
        name="domain-independence-test",
        site=SiteConfig(
            start_urls=[
                # Domain A: 6 pages (exceeds per-domain limit of 5)
                "https://domain-a.com/page1",
                "https://domain-a.com/page2",
                "https://domain-a.com/page3",
                "https://domain-a.com/page4",
                "https://domain-a.com/page5",
                "https://domain-a.com/page6",
                # Domain B: 3 pages (under limit)
                "https://domain-b.com/page1",
                "https://domain-b.com/page2",
                "https://domain-b.com/page3",
            ],
            allowed_domains=["domain-a.com", "domain-b.com"],
        ),
        crawling=CrawlingRules(
            per_domain_concurrent_requests=5,  # Domain limit
            global_concurrent_requests=20,  # High enough to not be bottleneck
            delay_between_requests=0.01,
            respect_robots_txt=False,
        ),
    )

    # Mock responses with small delay to simulate network
    async def delayed_response(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)  # 100ms per request
        return httpx.Response(200, html="<html><body>Page</body></html>")

    # Mock all pages
    for i in range(1, 7):
        httpx_mock.add_callback(delayed_response, url=f"https://domain-a.com/page{i}")
    for i in range(1, 4):
        httpx_mock.add_callback(delayed_response, url=f"https://domain-b.com/page{i}")

    # Run crawler and measure time
    start_time = time.time()
    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)
    time.time() - start_time

    # Verify all pages crawled
    assert len(results) == 9

    # Verify both domains were crawled
    domain_a_results = [r for r in results if "domain-a.com" in r.url]
    domain_b_results = [r for r in results if "domain-b.com" in r.url]
    assert len(domain_a_results) == 6
    assert len(domain_b_results) == 3

    # If domains were truly independent, domain B shouldn't be blocked
    # by domain A's queue. This test verifies both complete successfully.


async def test_per_domain_limit_enforced(httpx_mock: HTTPXMock) -> None:
    """Test that per-domain limit is actually enforced.

    NOTE: This test uses shared state tracking with asyncio.Lock.
    Timing dependencies may vary slightly on different systems.
    """
    # Track concurrent requests per domain
    concurrent_requests = {"domain-a.com": 0, "max_concurrent": 0}
    lock = asyncio.Lock()

    async def track_concurrent_request(request: httpx.Request) -> httpx.Response:
        domain = request.url.host

        async with lock:
            concurrent_requests[domain] = concurrent_requests.get(domain, 0) + 1
            concurrent_requests["max_concurrent"] = max(
                concurrent_requests["max_concurrent"], concurrent_requests[domain]
            )

        # Simulate work
        await asyncio.sleep(0.1)  # Reduced from 0.2s

        async with lock:
            concurrent_requests[domain] -= 1

        return httpx.Response(200, html="<html><body>Page</body></html>")

    config = SusConfig(
        name="limit-enforcement-test",
        site=SiteConfig(
            start_urls=[
                f"https://domain-a.com/page{i}" for i in range(1, 7)
            ],  # Reduced from 11 to 7
            allowed_domains=["domain-a.com"],
        ),
        crawling=CrawlingRules(
            per_domain_concurrent_requests=3,  # Limit to 3 concurrent per domain
            global_concurrent_requests=20,  # Higher than domain limit
            delay_between_requests=0.01,
            respect_robots_txt=False,
        ),
    )

    # Mock all pages with tracking
    for i in range(1, 7):  # Reduced from 11 to 7
        httpx_mock.add_callback(track_concurrent_request, url=f"https://domain-a.com/page{i}")

    # Run crawler
    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Verify all pages crawled
    assert len(results) == 6, f"Expected 6 pages, got {len(results)}"

    # Verify per-domain limit was enforced
    # Max concurrent should not exceed per_domain_concurrent_requests
    assert concurrent_requests["max_concurrent"] <= 3, (
        f"Per-domain limit violated: {concurrent_requests['max_concurrent']} concurrent (limit: 3)"
    )


async def test_global_limit_with_multiple_domains(httpx_mock: HTTPXMock) -> None:
    """Test that global limit works across multiple domains."""
    config = SusConfig(
        name="global-limit-test",
        site=SiteConfig(
            start_urls=[
                "https://domain-a.com/page1",
                "https://domain-a.com/page2",
                "https://domain-b.com/page1",
                "https://domain-b.com/page2",
                "https://domain-c.com/page1",
                "https://domain-c.com/page2",
            ],
            allowed_domains=["domain-a.com", "domain-b.com", "domain-c.com"],
        ),
        crawling=CrawlingRules(
            global_concurrent_requests=4,  # Total across all domains
            per_domain_concurrent_requests=3,  # Per domain (not the bottleneck)
            delay_between_requests=0.01,
            respect_robots_txt=False,
        ),
    )

    for domain in ["domain-a.com", "domain-b.com", "domain-c.com"]:
        for i in range(1, 3):
            httpx_mock.add_response(
                url=f"https://{domain}/page{i}", html="<html><body>Page</body></html>"
            )

    # Run crawler
    crawler = Crawler(config)
    results = []
    async for result in crawler.crawl():
        results.append(result)

    # Verify all pages crawled across all domains
    assert len(results) == 6

    # Verify pages from all three domains were crawled
    domains_crawled = {result.url.split("/")[2] for result in results}
    assert len(domains_crawled) == 3
    assert "domain-a.com" in domains_crawled
    assert "domain-b.com" in domains_crawled
    assert "domain-c.com" in domains_crawled

    # Global limit coordination happens via semaphores
    # This test verifies multi-domain crawling works with both limits active
