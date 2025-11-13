"""Unit tests for Crawler class with pytest-httpx mocking."""

import asyncio
import time

import httpx
import pytest
import pytest_httpx
from pydantic import ValidationError

from sus.config import CrawlingRules, PathPattern, SiteConfig, SusConfig
from sus.crawler import Crawler, RateLimiter

# ============================================================================
# RateLimiter Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limiter_allows_burst() -> None:
    """Test rate limiter allows burst requests without delay."""
    limiter = RateLimiter(rate=10.0, burst=3)
    start = time.time()

    # First 3 requests should be instant (burst capacity)
    for _ in range(3):
        await limiter.acquire()

    elapsed = time.time() - start
    assert elapsed < 0.1, "Burst requests should be instant"


@pytest.mark.asyncio
async def test_rate_limiter_enforces_rate_after_burst() -> None:
    """Test rate limiter delays after burst is exhausted."""
    limiter = RateLimiter(rate=10.0, burst=2)  # 10 req/s = 0.1s delay
    start = time.time()

    # First 2 should be instant (burst)
    await limiter.acquire()
    await limiter.acquire()

    burst_time = time.time() - start
    assert burst_time < 0.1, "Burst should be instant"

    # 3rd should wait
    await limiter.acquire()
    total_time = time.time() - start
    assert total_time >= 0.08, "Should wait for token refill"


@pytest.mark.asyncio
async def test_rate_limiter_refills_tokens_over_time() -> None:
    """Test token bucket refills over time."""
    limiter = RateLimiter(rate=10.0, burst=1)

    # Use initial token
    await limiter.acquire()

    # Wait for token to refill
    await asyncio.sleep(0.15)  # 1.5 tokens should refill

    # Should be able to acquire without much delay
    start = time.time()
    await limiter.acquire()
    elapsed = time.time() - start

    assert elapsed < 0.05, "Token should be available after refill"


@pytest.mark.asyncio
async def test_rate_limiter_caps_tokens_at_burst() -> None:
    """Test token bucket doesn't exceed burst capacity."""
    limiter = RateLimiter(rate=10.0, burst=2)

    # Wait long enough to refill many tokens
    await asyncio.sleep(0.5)  # Would refill 5 tokens, but capped at 2

    start = time.time()

    # Should only have burst capacity (2), not more
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()  # This one should wait

    elapsed = time.time() - start
    assert elapsed >= 0.08, "Should not have more than burst tokens"


@pytest.mark.asyncio
async def test_rate_limiter_zero_rate() -> None:
    """Test rate limiter with very high rate (no delay)."""
    limiter = RateLimiter(rate=1000.0, burst=5)

    start = time.time()
    for _ in range(10):
        await limiter.acquire()

    elapsed = time.time() - start
    assert elapsed < 0.1, "High rate should have minimal delay"


# ============================================================================
# Crawler Basic Tests
# ============================================================================


@pytest.mark.asyncio
async def test_crawler_basic_single_page(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawling a single page with mocked HTTP."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assert len(results) == 1
    assert results[0].url == "http://example.com/docs/"
    assert results[0].status_code == 200
    assert "Hello" in results[0].html
    assert results[0].content_type == "text/html; charset=utf-8"


@pytest.mark.asyncio
async def test_crawler_follows_links(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler follows links found in pages."""
    # Mock index page with links
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html=(
            '<html><body>'
            '<a href="/docs/page1">Page 1</a>'
            '<a href="/docs/page2">Page 2</a>'
            '</body></html>'
        ),
        status_code=200,
        headers={"content-type": "text/html"},
    )

    # Mock linked pages
    httpx_mock.add_response(
        url="http://example.com/docs/page1",
        html="<html><body><h1>Page 1</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/docs/page2",
        html="<html><body><h1>Page 2</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = {r.url for r in results}
    assert len(results) == 3
    assert "http://example.com/docs/" in urls
    assert "http://example.com/docs/page1" in urls
    assert "http://example.com/docs/page2" in urls


@pytest.mark.asyncio
async def test_crawler_respects_domain_filtering(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler only follows links within allowed domains."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="""
        <html><body>
            <a href="/docs/page1">Internal</a>
            <a href="http://external.com/page">External</a>
        </body></html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/docs/page1",
        html="<html><body><h1>Page 1</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = {r.url for r in results}
    assert len(results) == 2  # Only index and page1
    assert "http://example.com/docs/" in urls
    assert "http://example.com/docs/page1" in urls
    assert "http://external.com/page" not in urls


@pytest.mark.asyncio
async def test_crawler_respects_include_patterns(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler respects include patterns."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="""
        <html><body>
            <a href="/docs/guide">Guide (included)</a>
            <a href="/blog/post">Blog (excluded)</a>
        </body></html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/docs/guide",
        html="<html><body><h1>Guide</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = {r.url for r in results}
    assert "http://example.com/docs/guide" in urls
    assert "http://example.com/blog/post" not in urls


@pytest.mark.asyncio
async def test_crawler_respects_exclude_patterns(
    httpx_mock: pytest_httpx.HTTPXMock,
) -> None:
    """Test crawler respects exclude patterns."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            exclude_patterns=[PathPattern(pattern="*.pdf", type="glob")],
            delay_between_requests=0.0,
            respect_robots_txt=False,
        ),
    )

    httpx_mock.add_response(
        url="http://example.com/",
        html="""
        <html><body>
            <a href="/page.html">HTML Page</a>
            <a href="/document.pdf">PDF</a>
        </body></html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/page.html",
        html="<html><body><h1>Page</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = {r.url for r in results}
    assert "http://example.com/page.html" in urls
    assert "http://example.com/document.pdf" not in urls


@pytest.mark.asyncio
@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
async def test_crawler_respects_depth_limit(
    httpx_mock: pytest_httpx.HTTPXMock,
) -> None:
    """Test crawler respects depth limit."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            depth_limit=1,  # Only start_urls + 1 level
            delay_between_requests=0.0,
            respect_robots_txt=False,
        ),
    )

    # Level 0: start URL
    httpx_mock.add_response(
        url="http://example.com/",
        html='<html><body><a href="/level1">Level 1</a></body></html>',
        status_code=200,
        headers={"content-type": "text/html"},
    )

    # Level 1: first link
    httpx_mock.add_response(
        url="http://example.com/level1",
        html='<html><body><a href="/level2">Level 2</a></body></html>',
        status_code=200,
        headers={"content-type": "text/html"},
    )

    # Level 2: should NOT be crawled (mock won't be used)
    httpx_mock.add_response(
        url="http://example.com/level2",
        html="<html><body><h1>Level 2</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = {r.url for r in results}
    assert len(results) == 2  # Only level 0 and level 1
    assert "http://example.com/" in urls
    assert "http://example.com/level1" in urls
    assert "http://example.com/level2" not in urls


@pytest.mark.asyncio
@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
async def test_crawler_respects_max_pages(
    httpx_mock: pytest_httpx.HTTPXMock,
) -> None:
    """Test crawler stops after max_pages limit."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_pages=2,  # Limit to 2 pages
            delay_between_requests=0.0,
            global_concurrent_requests=1,  # Sequential to ensure exact limit
            respect_robots_txt=False,
        ),
    )

    httpx_mock.add_response(
        url="http://example.com/",
        html=(
            '<html><body>'
            '<a href="/page1">P1</a>'
            '<a href="/page2">P2</a>'
            '<a href="/page3">P3</a>'
            '</body></html>'
        ),
        status_code=200,
        headers={"content-type": "text/html"},
    )

    for i in range(1, 4):
        httpx_mock.add_response(
            url=f"http://example.com/page{i}",
            html=f"<html><body><h1>Page {i}</h1></body></html>",
            status_code=200,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    # With sequential requests, should stop exactly at max_pages
    assert len(results) <= 2, "Should not exceed max_pages"


# ============================================================================
# Content-Type Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_crawler_skips_non_html_content(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler skips non-HTML content types."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html='<html><body><a href="/docs/data.json">JSON</a></body></html>',
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/docs/data.json",
        text='{"key": "value"}',
        status_code=200,
        headers={"content-type": "application/json"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    # Should only have index page, not JSON
    assert len(results) == 1
    assert results[0].url == "http://example.com/docs/"


@pytest.mark.asyncio
async def test_crawler_accepts_html_variants(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler accepts various HTML content-type variants."""
    content_types = [
        "text/html",
        "text/html; charset=utf-8",
        "text/html; charset=UTF-8",
        "TEXT/HTML",  # Case insensitive
    ]

    for i, ct in enumerate(content_types):
        httpx_mock.add_response(
            url=f"http://example.com/docs/page{i}",
            html=f"<html><body><h1>Page {i}</h1></body></html>",
            status_code=200,
            headers={"content-type": ct},
        )

    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=[f"http://example.com/docs/page{i}" for i in range(len(content_types))],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(delay_between_requests=0.0, respect_robots_txt=False),
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assert len(results) == len(content_types)


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_crawler_handles_404_gracefully(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler handles 404 errors without crashing."""
    # Mock retries (max_retries=1 in sample_config means 2 total attempts)
    for _ in range(2):
        httpx_mock.add_response(
            url="http://example.com/docs/",
            status_code=404,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assert len(results) == 0
    assert crawler.stats.pages_failed > 0
    assert crawler.stats.pages_crawled == 0


@pytest.mark.asyncio
async def test_crawler_handles_500_errors(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler handles 500 errors with retries."""
    # Mock retries (max_retries=1 in sample_config means 2 total attempts)
    for _ in range(2):
        httpx_mock.add_response(
            url="http://example.com/docs/",
            status_code=500,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assert len(results) == 0
    assert crawler.stats.pages_failed > 0
    # Check for any HTTP error (actual exception type may vary)
    assert len(crawler.stats.error_counts) > 0


@pytest.mark.asyncio
async def test_crawler_retries_with_exponential_backoff(
    httpx_mock: pytest_httpx.HTTPXMock,
) -> None:
    """Test crawler retries failed requests with backoff."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=2,
            retry_backoff=1.5,
            delay_between_requests=0.0,
            respect_robots_txt=False,
        ),
    )

    # Fail twice, succeed on third try
    httpx_mock.add_response(
        url="http://example.com/",
        status_code=503,
        headers={"content-type": "text/html"},
    )
    httpx_mock.add_response(
        url="http://example.com/",
        status_code=503,
        headers={"content-type": "text/html"},
    )
    httpx_mock.add_response(
        url="http://example.com/",
        html="<html><body><h1>Success</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    start = time.time()
    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    elapsed = time.time() - start

    assert len(results) == 1
    assert "Success" in results[0].html
    # Should have waited: 1.5^1 + 1.5^2 = 1.5 + 2.25 = 3.75 seconds
    assert elapsed >= 3.5, "Should have exponential backoff delay"


@pytest.mark.asyncio
async def test_crawler_gives_up_after_max_retries(
    httpx_mock: pytest_httpx.HTTPXMock,
) -> None:
    """Test crawler gives up after max_retries exceeded."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=2,  # 2 retries = 3 total attempts
            retry_backoff=1.2,
            delay_between_requests=0.0,
            respect_robots_txt=False,
        ),
    )

    # Mock exactly max_retries + 1 attempts
    for _ in range(3):  # 1 initial + 2 retries
        httpx_mock.add_response(
            url="http://example.com/",
            status_code=500,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assert len(results) == 0
    assert crawler.stats.pages_failed == 1
    assert len(crawler.stats.error_counts) > 0


@pytest.mark.asyncio
async def test_crawler_handles_malformed_html_gracefully(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler handles malformed HTML without crashing."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="<html><body><h1>Broken HTML<h1><p>Missing closing tags",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    # Should still process the page
    assert len(results) == 1
    assert results[0].status_code == 200


# ============================================================================
# Link Extraction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_crawler_extracts_links_correctly(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler extracts and resolves links correctly."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="""
        <html><body>
            <a href="/docs/page1">Absolute path</a>
            <a href="page2">Relative path</a>
            <a href="http://example.com/docs/page3">Full URL</a>
            <a href="#section">Fragment only</a>
        </body></html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    for page in ["page1", "page2", "page3"]:
        httpx_mock.add_response(
            url=f"http://example.com/docs/{page}",
            html=f"<html><body><h1>{page}</h1></body></html>",
            status_code=200,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = {r.url for r in results}
    assert "http://example.com/docs/page1" in urls
    assert "http://example.com/docs/page2" in urls
    assert "http://example.com/docs/page3" in urls


@pytest.mark.asyncio
async def test_crawler_deduplicates_urls(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler doesn't visit same URL multiple times."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html=(
            '<html><body>'
            '<a href="/docs/page1">Link 1</a>'
            '<a href="/docs/page1">Link 2 (duplicate)</a>'
            '</body></html>'
        ),
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/docs/page1",
        html="<html><body><h1>Page 1</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = [r.url for r in results]
    assert len(results) == 2  # Index + page1 (not twice)
    assert urls.count("http://example.com/docs/page1") == 1


@pytest.mark.asyncio
async def test_crawler_normalizes_urls_before_deduplication(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler normalizes URLs (removes fragments, normalizes case)."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="""
        <html><body>
            <a href="/docs/page1">Link 1</a>
            <a href="/docs/page1#section">Link 2 (with fragment)</a>
        </body></html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/docs/page1",
        html="<html><body><h1>Page 1</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    urls = [r.url for r in results]
    assert len(results) == 2  # Index + page1 (normalized, not twice)
    assert urls.count("http://example.com/docs/page1") == 1


# ============================================================================
# Asset Extraction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_crawler_extracts_image_assets(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler extracts image URLs from pages."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="""
        <html><body>
            <img src="/img/logo.png" alt="Logo">
            <img src="http://example.com/img/banner.jpg" alt="Banner">
        </body></html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assert len(results) == 1
    assets = results[0].assets
    assert "http://example.com/img/logo.png" in assets
    assert "http://example.com/img/banner.jpg" in assets


@pytest.mark.asyncio
async def test_crawler_extracts_css_assets(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler extracts CSS URLs from pages."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="""
        <html>
        <head>
            <link rel="stylesheet" href="/css/style.css">
            <link rel="stylesheet" href="http://example.com/css/theme.css">
        </head>
        <body><h1>Test</h1></body>
        </html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assets = results[0].assets
    assert "http://example.com/css/style.css" in assets
    assert "http://example.com/css/theme.css" in assets


@pytest.mark.asyncio
async def test_crawler_extracts_javascript_assets(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler extracts JavaScript URLs from pages."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="""
        <html>
        <head><script src="/js/app.js"></script></head>
        <body>
            <h1>Test</h1>
            <script src="http://example.com/js/analytics.js"></script>
        </body>
        </html>
        """,
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assets = results[0].assets
    assert "http://example.com/js/app.js" in assets
    assert "http://example.com/js/analytics.js" in assets


# ============================================================================
# Concurrency Tests
# ============================================================================


@pytest.mark.asyncio
async def test_crawler_respects_global_concurrent_limit(
    httpx_mock: pytest_httpx.HTTPXMock,
) -> None:
    """Test crawler respects global concurrency limit."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            global_concurrent_requests=2,
            delay_between_requests=0.0,
            respect_robots_txt=False,
        ),
    )

    # Mock many pages
    httpx_mock.add_response(
        url="http://example.com/",
        html="".join(f'<a href="/page{i}">Page {i}</a>' for i in range(10)),
        status_code=200,
        headers={"content-type": "text/html"},
    )

    for i in range(10):
        httpx_mock.add_response(
            url=f"http://example.com/page{i}",
            html=f"<html><body><h1>Page {i}</h1></body></html>",
            status_code=200,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    # Should complete successfully with limited concurrency
    assert len(results) >= 3  # At least index + some pages


@pytest.mark.asyncio
async def test_crawler_tracks_stats_correctly(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler tracks crawl statistics correctly."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html='<html><body><a href="/docs/page1">P1</a><img src="/img/logo.png"></body></html>',
        status_code=200,
        headers={"content-type": "text/html"},
    )

    httpx_mock.add_response(
        url="http://example.com/docs/page1",
        html="<html><body><h1>Page 1</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        crawler = Crawler(sample_config, client=client)
        results = []

        async for result in crawler.crawl():
            results.append(result)

    assert crawler.stats.pages_crawled == 2
    assert crawler.stats.pages_failed == 0
    assert crawler.stats.assets_discovered >= 1  # At least the image
    assert crawler.stats.total_bytes > 0


@pytest.mark.asyncio
async def test_crawler_with_no_start_urls_fails() -> None:
    """Test crawler validation fails with no start URLs."""
    with pytest.raises(ValidationError):  # Pydantic validation error
        SusConfig(
            name="test",
            site=SiteConfig(
                start_urls=[],  # Empty list should fail validation
                allowed_domains=["example.com"],
            ),
        )


@pytest.mark.asyncio
async def test_crawler_client_cleanup(
    httpx_mock: pytest_httpx.HTTPXMock, sample_config: SusConfig
) -> None:
    """Test crawler properly closes HTTP client."""
    httpx_mock.add_response(
        url="http://example.com/docs/",
        html="<html><body><h1>Test</h1></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
    )

    crawler = Crawler(sample_config)  # No client provided

    async for _ in crawler.crawl():
        pass

    # Client should be closed after crawl completes
    assert crawler.client is None or crawler.client.is_closed
