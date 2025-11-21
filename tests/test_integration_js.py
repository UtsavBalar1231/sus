"""Integration tests for JavaScript rendering.

End-to-end tests using real Playwright browser instances with local HTML fixtures.
These tests require playwright to be installed: uv sync --group js && uv run playwright install chromium

Tests can be skipped if playwright is not available.
"""

import importlib.util
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

from sus.config import CrawlingRules, JavaScriptConfig, SiteConfig, SusConfig
from sus.crawler import Crawler

# Try to import playwright, skip tests if not available
PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None

# Skip all tests in this module if playwright not available
pytestmark = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE,
    reason="Playwright not installed. Install with: uv sync --group js && uv run playwright install chromium",
)


@pytest.fixture
def fixtures_dir() -> Path:
    """Get path to SPA test fixtures directory."""
    return Path(__file__).parent / "fixtures" / "spa"


@pytest.fixture
def simple_spa_path(fixtures_dir: Path) -> str:
    """Get file:// URL for simple SPA fixture."""
    return f"file://{fixtures_dir / 'simple-spa.html'}"


@pytest.fixture
def react_like_spa_path(fixtures_dir: Path) -> str:
    """Get file:// URL for React-like SPA fixture."""
    return f"file://{fixtures_dir / 'react-like-spa.html'}"


@pytest.fixture
def network_idle_spa_path(fixtures_dir: Path) -> str:
    """Get file:// URL for network idle SPA fixture."""
    return f"file://{fixtures_dir / 'network-idle-spa.html'}"


@pytest.mark.asyncio
async def test_simple_spa_rendering(simple_spa_path: str) -> None:
    """Test end-to-end rendering of simple SPA."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=[simple_spa_path],
            allowed_domains=[""],  # file:// URLs have empty domain
        ),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_for="domcontentloaded"), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    result = results[0]

    # Check that JavaScript-rendered content is present
    assert "Welcome to Simple SPA" in result.html
    assert "This content was rendered by JavaScript" in result.html

    # Check extracted links
    assert len(result.links) >= 3
    list(result.links)
    # Note: file:// URLs will have file:// scheme in links

    # Check extracted assets (images, css, js from the rendered content)
    assert len(result.assets) >= 1


@pytest.mark.asyncio
async def test_react_like_spa_delayed_rendering(react_like_spa_path: str) -> None:
    """Test SPA with delayed rendering (simulates React hydration)."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[react_like_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_for="networkidle", wait_timeout_ms= 10000), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    result = results[0]

    # Check that all phases of rendering completed
    assert "React-like SPA" in result.html
    assert "Dynamic Article" in result.html  # Late-rendered content
    assert "This content was loaded asynchronously" in result.html

    # Check links from dynamically loaded content
    assert len(result.links) >= 4  # Home, Products, Blog, Read more

    # Check dynamically added assets
    assert len(result.assets) >= 2  # Images and scripts


@pytest.mark.asyncio
async def test_network_idle_spa_multiple_requests(httpserver: HTTPServer) -> None:
    """Test SPA with multiple async requests (network idle wait)."""
    # Mock robots.txt to avoid 500 errors
    httpserver.expect_request("/robots.txt").respond_with_data(
        "User-agent: *\nDisallow:",
        status=200,
        content_type="text/plain",
    )

    # Serve API endpoints with delays to simulate real async operations
    httpserver.expect_request("/api/users").respond_with_json(
        {"data": "users"},
        status=200,
    )
    httpserver.expect_request("/api/posts").respond_with_json(
        {"data": "posts"},
        status=200,
    )
    httpserver.expect_request("/api/comments").respond_with_json(
        {"data": "comments"},
        status=200,
    )

    # Serve CSS asset
    httpserver.expect_request("/css/network-idle.css").respond_with_data(
        "body { color: blue; }",
        content_type="text/css",
    )

    # Serve image asset
    httpserver.expect_request("/images/users-icon.png").respond_with_data(
        b"\x89PNG",  # PNG header
        content_type="image/png",
    )

    # HTML that makes real HTTP requests to the API endpoints
    spa_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Network Idle Test SPA</title>
</head>
<body>
    <div id="app">Initializing network requests...</div>

    <script>
        async function loadApp() {{
            const app = document.getElementById('app');

            // Initial render
            app.innerHTML = `
                <h1>Network Idle Test SPA</h1>
                <div id="users">Loading users...</div>
                <div id="posts">Loading posts...</div>
                <div id="comments">Loading comments...</div>
            `;

            // Make real HTTP requests (triggers networkidle detection)
            const usersPromise = fetch('{httpserver.url_for("/api/users")}')
                .then(r => r.json())
                .then(data => {{
                    document.getElementById('users').innerHTML = `
                        <h2>Users</h2>
                        <ul>
                            <li><a href="/user/1">User 1</a></li>
                            <li><a href="/user/2">User 2</a></li>
                        </ul>
                        <img src="/images/users-icon.png" alt="Users icon">
                    `;
                }});

            const postsPromise = fetch('{httpserver.url_for("/api/posts")}')
                .then(r => r.json())
                .then(data => {{
                    document.getElementById('posts').innerHTML = `
                        <h2>Posts</h2>
                        <ul>
                            <li><a href="/post/1">First Post</a></li>
                            <li><a href="/post/2">Second Post</a></li>
                        </ul>
                    `;
                }});

            const commentsPromise = fetch('{httpserver.url_for("/api/comments")}')
                .then(r => r.json())
                .then(data => {{
                    document.getElementById('comments').innerHTML = `
                        <h2>Comments</h2>
                        <ul>
                            <li><a href="/comment/1">Great article!</a></li>
                            <li><a href="/comment/2">Thanks for sharing</a></li>
                        </ul>
                    `;

                    // Add final asset after all data is loaded
                    const link = document.createElement('link');
                    link.rel = 'stylesheet';
                    link.href = '{httpserver.url_for("/css/network-idle.css")}';
                    document.head.appendChild(link);
                }});

            // Wait for all requests to complete
            await Promise.all([usersPromise, postsPromise, commentsPromise]);
        }}

        loadApp();
    </script>
</body>
</html>"""

    # Serve the SPA HTML
    httpserver.expect_request("/spa").respond_with_data(
        spa_html,
        content_type="text/html",
    )

    spa_url = httpserver.url_for("/spa")

    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[spa_url], allowed_domains=["localhost"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_for="networkidle", wait_timeout_ms= 10000), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    result = results[0]

    # All async content should be loaded (networkidle waited for fetch requests)
    assert "Users" in result.html
    assert "Posts" in result.html
    assert "Comments" in result.html

    # Check links from all async sections
    assert len(result.links) >= 6  # Users (2), posts (2), comments (2)

    # Check final assets added after network idle
    assert len(result.assets) >= 1


@pytest.mark.asyncio
async def test_spa_vs_http_content_difference(httpserver: HTTPServer) -> None:
    """Test that JS rendering captures content missing in HTTP-only fetch."""
    # HTML with JavaScript that renders content
    spa_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SPA Test</title>
</head>
<body>
    <div id="app">Loading...</div>
    <script>
        (function() {
            const app = document.getElementById('app');
            app.innerHTML = '<h1>Welcome to Simple SPA</h1><a href="/about">About</a>';
        })();
    </script>
</body>
</html>"""

    # Serve the SPA HTML
    httpserver.expect_request("/spa").respond_with_data(
        spa_html,
        content_type="text/html",
    )

    spa_url = httpserver.url_for("/spa")

    # First, test HTTP-only mode (JavaScript disabled)
    # This should get the raw HTML response
    config_http = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[spa_url], allowed_domains=["localhost"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=False), max_pages=1),
    )

    crawler_http = Crawler(config_http)
    results_http = []

    async for result in crawler_http.crawl():
        results_http.append(result)

    assert len(results_http) == 1

    # HTTP-only mode gets raw HTML with "Loading..." before JS executes
    # Note: The HTML contains the <script> tag, but we're testing what httpx sees
    assert "Loading..." in results_http[0].html
    # The raw response has the JS code but not the RENDERED content
    assert "app.innerHTML" in results_http[0].html  # JS code is present

    # Now test with JavaScript enabled
    config_js = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[spa_url], allowed_domains=["localhost"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_for="domcontentloaded"), max_pages=1),
    )

    crawler_js = Crawler(config_js)
    results_js = []

    async for result in crawler_js.crawl():
        results_js.append(result)

    assert len(results_js) == 1

    # JavaScript-rendered HTML should contain the rendered content
    # and NOT the original "Loading..." text (it was replaced)
    assert "Welcome to Simple SPA" in results_js[0].html
    assert len(results_js[0].links) > 0
    # After JS execution, "Loading..." is replaced
    assert results_js[0].html.count("Loading...") == 0


@pytest.mark.asyncio
async def test_multiple_pages_context_reuse(simple_spa_path: str, react_like_spa_path: str) -> None:
    """Test context pool reuse across multiple page fetches."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path, react_like_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(
                enabled=True,
                wait_for="networkidle",
                context_pool_size= 2,
            ), max_pages=2),
    )

    crawler = Crawler(config)
    results = []
    pool_sizes_during_crawl = []

    async for result in crawler.crawl():
        results.append(result)
        # Check pool during crawl (before cleanup in finally block)
        assert crawler.context_pool is not None
        pool_sizes_during_crawl.append(crawler.context_pool.qsize())

    # Should have rendered both pages
    assert len(results) == 2

    # Both pages should have rendered content
    rendered_titles = [result.html for result in results]
    assert any("Simple SPA" in html for html in rendered_titles)
    assert any("React-like SPA" in html for html in rendered_titles)

    # Context pool should have been used during crawl
    # After first page, at least 1 context should be in pool (returned for reuse)
    assert max(pool_sizes_during_crawl) > 0, "Context pool was never populated"


@pytest.mark.asyncio
async def test_wait_strategy_domcontentloaded_fast(simple_spa_path: str) -> None:
    """Test domcontentloaded wait strategy (fastest)."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_for="domcontentloaded"), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    # Content should be rendered even with fast wait
    assert "Welcome to Simple SPA" in results[0].html


@pytest.mark.asyncio
async def test_custom_viewport_size(simple_spa_path: str) -> None:
    """Test custom viewport dimensions."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(
                enabled=True,
                viewport_width= 375,  # Mobile viewport
                viewport_height= 667,
            ), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    assert results[0].html is not None


@pytest.mark.asyncio
async def test_custom_user_agent(simple_spa_path: str) -> None:
    """Test custom user agent override."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(
                enabled=True,
                user_agent_override= "TestBot/1.0",
            ), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    # User agent is set but hard to verify from result
    # Just ensure it doesn't break the crawl


@pytest.mark.asyncio
async def test_invalid_url_handling() -> None:
    """Test graceful handling of invalid URLs with JS rendering."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://this-domain-definitely-does-not-exist-12345.com"], allowed_domains=["this-domain-definitely-does-not-exist-12345.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_timeout_ms= 5000), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    # Should handle error gracefully, no results
    assert len(results) == 0
    assert crawler.stats.pages_failed == 1


@pytest.mark.asyncio
async def test_timeout_handling() -> None:
    """Test timeout handling with unreachable page."""
    config = SusConfig(
        name="test",
        site=SiteConfig(
            start_urls=["https://httpbin.org/delay/60"],  # 60s delay
            allowed_domains=["httpbin.org"],
        ),
        crawling=CrawlingRules(
            javascript=JavaScriptConfig(enabled=True, wait_timeout_ms=2000),  # 2s timeout
            max_pages=1,
        ),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    # Should timeout and fail gracefully
    assert len(results) == 0
    assert crawler.stats.pages_failed == 1


@pytest.mark.asyncio
async def test_browser_cleanup_on_error(simple_spa_path: str) -> None:
    """Test browser cleanup happens even when errors occur."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path, "https://invalid-url-for-error.test"], allowed_domains=["", "invalid-url-for-error.test"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_timeout_ms= 3000), max_pages=2),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    # Should have at least the successful one
    assert len(results) >= 1

    # Browser should be cleaned up
    assert crawler.playwright_browser is None
    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 0


@pytest.mark.asyncio
async def test_link_extraction_from_js_rendered_content(simple_spa_path: str) -> None:
    """Test links are correctly extracted from JavaScript-rendered DOM."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    result = results[0]

    # Should extract links from rendered navigation
    assert len(result.links) >= 3

    # Links should be absolute URLs (file:// scheme)
    for link in result.links:
        assert link.startswith("file://") or link.startswith("http")


@pytest.mark.asyncio
async def test_asset_extraction_from_js_rendered_content(react_like_spa_path: str) -> None:
    """Test assets are correctly extracted from JavaScript-rendered DOM."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[react_like_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_for="networkidle"), max_pages=1),
    )

    crawler = Crawler(config)
    results = []

    async for result in crawler.crawl():
        results.append(result)

    assert len(results) == 1
    result = results[0]

    # Should extract assets added by JavaScript
    assert len(result.assets) >= 2

    # Assets should include images, CSS, JS
    asset_types = set()
    for asset in result.assets:
        if ".css" in asset:
            asset_types.add("css")
        elif ".js" in asset:
            asset_types.add("js")
        elif ".png" in asset or ".jpg" in asset:
            asset_types.add("image")

    # Should have multiple asset types
    assert len(asset_types) >= 2


@pytest.mark.asyncio
async def test_context_pool_concurrent_usage(
    simple_spa_path: str, react_like_spa_path: str, network_idle_spa_path: str
) -> None:
    """Test context pool handles concurrent page fetches efficiently."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path, react_like_spa_path, network_idle_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(
            javascript=JavaScriptConfig(
                enabled=True,
                context_pool_size=3,
                wait_for="domcontentloaded",  # Faster for test
            ),
            global_concurrent_requests=3,
            max_pages=3,
        ),
    )

    crawler = Crawler(config)
    results = []
    pool_sizes_during_crawl = []

    async for result in crawler.crawl():
        results.append(result)
        # Track pool size during crawl
        assert crawler.context_pool is not None
        pool_sizes_during_crawl.append(crawler.context_pool.qsize())

    # All pages should be rendered
    assert len(results) == 3

    # Context pool should have been used during concurrent usage
    # With 3 concurrent requests, pool should be populated
    assert max(pool_sizes_during_crawl) > 0, "Context pool was never populated"


@pytest.mark.asyncio
async def test_js_rendering_memory_cleanup(simple_spa_path: str) -> None:
    """Test multiple page renders don't leak memory (context reuse)."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=[simple_spa_path], allowed_domains=[""]),
        crawling=CrawlingRules(
            javascript=JavaScriptConfig(
                enabled=True,
                context_pool_size=2,
            ),
            max_pages=5,  # Render same page multiple times
        ),
    )

    crawler = Crawler(config)

    # Add same URL multiple times to queue
    for _ in range(4):
        await crawler.queue.put((simple_spa_path, None))

    results = []
    pool_sizes_during_crawl = []

    async for result in crawler.crawl():
        results.append(result)
        # Track pool size to verify contexts are being reused
        assert crawler.context_pool is not None
        pool_sizes_during_crawl.append(crawler.context_pool.qsize())

    # Should process pages without memory issues
    # Note: visited set will prevent duplicates, so only 1 result
    assert len(results) >= 1

    # Context pool should have been used during crawl (reuse prevents memory leak)
    assert max(pool_sizes_during_crawl) > 0, "Context pool was never populated"

    # After crawl completes, cleanup happens (pool is emptied in finally block)
    # This is expected behavior - pool is cleaned up to free resources
    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 0, "Pool should be empty after cleanup"
