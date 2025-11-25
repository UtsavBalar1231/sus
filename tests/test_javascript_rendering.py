"""Unit tests for JavaScript rendering with Playwright.

Tests cover configuration validation, browser lifecycle, context pooling,
page fetching, error handling, and resource cleanup.
"""

import asyncio
import sys
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from sus.config import CrawlingRules, JavaScriptConfig, SiteConfig, SusConfig
from sus.crawler import Crawler, CrawlResult


def create_mock_playwright_module(mock_playwright: MagicMock) -> tuple[ModuleType, ModuleType]:
    """Create mock playwright modules for testing without playwright installed.

    Args:
        mock_playwright: Mock playwright instance to use

    Returns:
        Tuple of (playwright module, playwright.async_api module)
    """
    mock_pw_module = ModuleType("playwright")
    mock_async_api = ModuleType("playwright.async_api")

    def mock_async_playwright() -> Any:
        """Mock async_playwright factory."""
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock(return_value=mock_playwright)
        return mock_instance

    mock_async_api.async_playwright = mock_async_playwright  # type: ignore[attr-defined]
    mock_pw_module.async_api = mock_async_api  # type: ignore[attr-defined]

    return mock_pw_module, mock_async_api


def test_javascript_config_defaults() -> None:
    """Test JavaScriptConfig default values."""
    config = JavaScriptConfig()
    assert config.enabled is False
    assert config.wait_for == "networkidle"
    assert config.wait_timeout_ms == 30000
    assert config.user_agent_override is None
    assert config.viewport_width == 1920
    assert config.viewport_height == 1080
    assert config.javascript_enabled is True
    assert config.context_pool_size == 5


def test_javascript_config_enabled() -> None:
    """Test enabling JavaScript rendering."""
    config = JavaScriptConfig(enabled=True)
    assert config.enabled is True


def test_javascript_config_wait_for_domcontentloaded() -> None:
    """Test wait_for domcontentloaded strategy."""
    config = JavaScriptConfig(wait_for="domcontentloaded")
    assert config.wait_for == "domcontentloaded"


def test_javascript_config_wait_for_load() -> None:
    """Test wait_for load strategy."""
    config = JavaScriptConfig(wait_for="load")
    assert config.wait_for == "load"


def test_javascript_config_wait_for_networkidle() -> None:
    """Test wait_for networkidle strategy."""
    config = JavaScriptConfig(wait_for="networkidle")
    assert config.wait_for == "networkidle"


def test_javascript_config_wait_for_invalid() -> None:
    """Test invalid wait_for value raises error."""
    from typing import cast

    with pytest.raises(ValidationError, match="Input should be"):
        JavaScriptConfig(wait_for=cast("Any", "invalid"))


def test_javascript_config_wait_timeout_min() -> None:
    """Test minimum wait timeout (1000ms)."""
    config = JavaScriptConfig(wait_timeout_ms=1000)
    assert config.wait_timeout_ms == 1000


def test_javascript_config_wait_timeout_max() -> None:
    """Test maximum wait timeout (120000ms)."""
    config = JavaScriptConfig(wait_timeout_ms=120000)
    assert config.wait_timeout_ms == 120000


def test_javascript_config_wait_timeout_below_min() -> None:
    """Test wait timeout below minimum raises error."""
    with pytest.raises(ValidationError, match="greater than or equal to 1000"):
        JavaScriptConfig(wait_timeout_ms=500)


def test_javascript_config_wait_timeout_above_max() -> None:
    """Test wait timeout above maximum raises error."""
    with pytest.raises(ValidationError, match="less than or equal to 120000"):
        JavaScriptConfig(wait_timeout_ms=150000)


def test_javascript_config_user_agent_override() -> None:
    """Test custom user agent override."""
    config = JavaScriptConfig(user_agent_override="CustomBot/1.0")
    assert config.user_agent_override == "CustomBot/1.0"


def test_javascript_config_viewport_dimensions() -> None:
    """Test custom viewport dimensions."""
    config = JavaScriptConfig(viewport_width=1280, viewport_height=720)
    assert config.viewport_width == 1280
    assert config.viewport_height == 720


def test_javascript_config_viewport_width_min() -> None:
    """Test minimum viewport width (320px)."""
    config = JavaScriptConfig(viewport_width=320)
    assert config.viewport_width == 320


def test_javascript_config_viewport_width_below_min() -> None:
    """Test viewport width below minimum raises error."""
    with pytest.raises(ValidationError, match="greater than or equal to 320"):
        JavaScriptConfig(viewport_width=200)


def test_javascript_config_context_pool_size() -> None:
    """Test context pool size configuration."""
    config = JavaScriptConfig(context_pool_size=10)
    assert config.context_pool_size == 10


def test_javascript_config_context_pool_size_min() -> None:
    """Test minimum context pool size (1)."""
    config = JavaScriptConfig(context_pool_size=1)
    assert config.context_pool_size == 1


def test_javascript_config_context_pool_size_max() -> None:
    """Test maximum context pool size (20)."""
    config = JavaScriptConfig(context_pool_size=20)
    assert config.context_pool_size == 20


def test_javascript_config_context_pool_size_below_min() -> None:
    """Test context pool size below minimum raises error."""
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        JavaScriptConfig(context_pool_size=0)


def test_javascript_config_context_pool_size_above_max() -> None:
    """Test context pool size above maximum raises error."""
    with pytest.raises(ValidationError, match="less than or equal to 20"):
        JavaScriptConfig(context_pool_size=25)


def test_javascript_config_javascript_disabled() -> None:
    """Test disabling JavaScript execution in browser."""
    config = JavaScriptConfig(javascript_enabled=False)
    assert config.javascript_enabled is False


@pytest.mark.asyncio
async def test_ensure_browser_not_installed() -> None:
    """Test error when Playwright not installed."""
    from typing import cast

    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    # Mock the module import to simulate missing playwright
    old_modules = sys.modules.copy()
    sys.modules["playwright"] = cast("Any", None)
    sys.modules["playwright.async_api"] = cast("Any", None)

    try:
        with pytest.raises(ImportError, match="Playwright is required"):
            await crawler._ensure_browser()
    finally:
        # Restore original modules
        sys.modules.clear()
        sys.modules.update(old_modules)


@pytest.mark.asyncio
async def test_ensure_browser_creates_browser() -> None:
    """Test browser creation on first call."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_playwright = MagicMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    # Create mock playwright modules
    mock_pw_module, mock_async_api = create_mock_playwright_module(mock_playwright)
    sys.modules["playwright"] = mock_pw_module
    sys.modules["playwright.async_api"] = mock_async_api

    try:
        await crawler._ensure_browser()

        assert crawler.playwright_browser is mock_browser
        assert crawler.context_pool is not None
        assert crawler.context_pool.qsize() == 5  # Default pool size
    finally:
        sys.modules.pop("playwright", None)
        sys.modules.pop("playwright.async_api", None)


@pytest.mark.asyncio
async def test_ensure_browser_idempotent() -> None:
    """Test ensure_browser is idempotent (doesn't reinitialize)."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_browser = AsyncMock()
    crawler.playwright_browser = mock_browser

    # Call ensure_browser again
    await crawler._ensure_browser()

    # Should not change the browser
    assert crawler.playwright_browser is mock_browser


@pytest.mark.asyncio
async def test_ensure_browser_custom_pool_size() -> None:
    """Test browser initialization with custom context pool size."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, context_pool_size=10)),
    )
    crawler = Crawler(config)

    mock_playwright = MagicMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    # Create mock playwright modules
    mock_pw_module, mock_async_api = create_mock_playwright_module(mock_playwright)
    sys.modules["playwright"] = mock_pw_module
    sys.modules["playwright.async_api"] = mock_async_api

    try:
        await crawler._ensure_browser()

        assert crawler.context_pool is not None
        assert crawler.context_pool.qsize() == 10
    finally:
        sys.modules.pop("playwright", None)
        sys.modules.pop("playwright.async_api", None)


@pytest.mark.asyncio
async def test_create_browser_context_default_options() -> None:
    """Test browser context creation with default options."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_browser = AsyncMock()
    crawler.playwright_browser = mock_browser

    await crawler._create_browser_context()

    mock_browser.new_context.assert_called_once()
    call_args = mock_browser.new_context.call_args
    assert call_args is not None
    kwargs = call_args[1]
    assert kwargs["viewport"] == {"width": 1920, "height": 1080}
    assert kwargs["java_script_enabled"] is True
    assert "user_agent" not in kwargs


@pytest.mark.asyncio
async def test_create_browser_context_custom_viewport() -> None:
    """Test browser context with custom viewport."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(
            javascript=JavaScriptConfig(enabled=True, viewport_width=1280, viewport_height=720)
        ),
    )
    crawler = Crawler(config)

    mock_browser = AsyncMock()
    crawler.playwright_browser = mock_browser

    await crawler._create_browser_context()

    call_args = mock_browser.new_context.call_args
    assert call_args is not None
    kwargs = call_args[1]
    assert kwargs["viewport"] == {"width": 1280, "height": 720}


@pytest.mark.asyncio
async def test_create_browser_context_custom_user_agent() -> None:
    """Test browser context with custom user agent."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(
            javascript=JavaScriptConfig(enabled=True, user_agent_override="CustomBot/1.0")
        ),
    )
    crawler = Crawler(config)

    mock_browser = AsyncMock()
    crawler.playwright_browser = mock_browser

    await crawler._create_browser_context()

    call_args = mock_browser.new_context.call_args
    assert call_args is not None
    kwargs = call_args[1]
    assert kwargs["user_agent"] == "CustomBot/1.0"


@pytest.mark.asyncio
async def test_create_browser_context_javascript_disabled() -> None:
    """Test browser context with JavaScript disabled."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, javascript_enabled=False)),
    )
    crawler = Crawler(config)

    mock_browser = AsyncMock()
    crawler.playwright_browser = mock_browser

    await crawler._create_browser_context()

    call_args = mock_browser.new_context.call_args
    assert call_args is not None
    kwargs = call_args[1]
    assert kwargs["java_script_enabled"] is False


@pytest.mark.asyncio
async def test_close_browser_cleans_up() -> None:
    """Test browser cleanup closes all resources."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context1 = AsyncMock()
    mock_context2 = AsyncMock()

    crawler.playwright = mock_playwright
    crawler.playwright_browser = mock_browser
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context1)
    await crawler.context_pool.put(mock_context2)

    await crawler._close_browser()

    mock_context1.close.assert_called_once()
    mock_context2.close.assert_called_once()
    mock_browser.close.assert_called_once()
    mock_playwright.stop.assert_called_once()
    assert crawler.context_pool is None
    assert crawler.playwright_browser is None
    assert crawler.playwright is None


@pytest.mark.asyncio
async def test_close_browser_handles_errors() -> None:
    """Test browser cleanup handles errors gracefully."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()

    # Simulate errors during cleanup
    mock_context.close.side_effect = Exception("Context close error")
    mock_browser.close.side_effect = Exception("Browser close error")
    mock_playwright.stop.side_effect = Exception("Playwright stop error")

    crawler.playwright = mock_playwright
    crawler.playwright_browser = mock_browser
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    # Should not raise exceptions
    await crawler._close_browser()

    assert crawler.context_pool is None
    assert crawler.playwright_browser is None


@pytest.mark.asyncio
async def test_get_context_from_pool_when_available() -> None:
    """Test getting context from non-empty pool."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    context = await crawler._get_context_from_pool()

    assert context is mock_context
    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 0


@pytest.mark.asyncio
async def test_get_context_from_pool_fifo_order() -> None:
    """Test context pool uses FIFO order with asyncio.Queue."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context1 = AsyncMock()
    mock_context2 = AsyncMock()
    mock_context3 = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context1)
    await crawler.context_pool.put(mock_context2)
    await crawler.context_pool.put(mock_context3)

    # Queue uses FIFO order
    ctx1 = await crawler._get_context_from_pool()
    ctx2 = await crawler._get_context_from_pool()
    ctx3 = await crawler._get_context_from_pool()

    assert ctx1 is mock_context1
    assert ctx2 is mock_context2
    assert ctx3 is mock_context3


@pytest.mark.asyncio
async def test_get_context_from_pool_waits_when_empty() -> None:
    """Test get_context waits when pool is empty."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()

    # Simulate pool being populated after delay
    async def populate_pool() -> None:
        await asyncio.sleep(0.2)
        assert crawler.context_pool is not None
        await crawler.context_pool.put(mock_context)

    task = asyncio.create_task(populate_pool())
    context = await crawler._get_context_from_pool()
    await task

    assert context is mock_context


@pytest.mark.asyncio
async def test_return_context_to_pool() -> None:
    """Test returning context to pool."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()

    await crawler._return_context_to_pool(mock_context)

    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 1
    # Verify the context is in the queue by getting it back
    returned_context = await crawler.context_pool.get()
    assert returned_context is mock_context
    # Put it back for cleanup
    await crawler.context_pool.put(returned_context)


@pytest.mark.asyncio
async def test_return_context_to_pool_thread_safe() -> None:
    """Test context pool operations are thread-safe."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)
    crawler.context_pool = asyncio.Queue[Any]()

    mock_contexts = [AsyncMock() for _ in range(10)]

    # Concurrently return contexts to pool
    tasks = [crawler._return_context_to_pool(ctx) for ctx in mock_contexts]
    await asyncio.gather(*tasks)

    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 10


@pytest.mark.asyncio
async def test_context_pool_reuse() -> None:
    """Test contexts are reused from pool."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    # Get from pool
    ctx1 = await crawler._get_context_from_pool()
    assert ctx1 is mock_context
    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 0

    # Return to pool
    await crawler._return_context_to_pool(ctx1)
    assert crawler.context_pool.qsize() == 1

    # Get again - should be the same context
    ctx2 = await crawler._get_context_from_pool()
    assert ctx2 is mock_context
    assert ctx2 is ctx1


@pytest.mark.asyncio
async def test_context_pool_size_limit() -> None:
    """Test context pool doesn't exceed configured size during initialization."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, context_pool_size=3)),
    )
    crawler = Crawler(config)

    mock_playwright = MagicMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    # Create mock playwright modules
    mock_pw_module, mock_async_api = create_mock_playwright_module(mock_playwright)
    sys.modules["playwright"] = mock_pw_module
    sys.modules["playwright.async_api"] = mock_async_api

    try:
        await crawler._ensure_browser()

        # Should create exactly 3 contexts
        assert crawler.context_pool is not None
        assert crawler.context_pool.qsize() == 3
        assert mock_browser.new_context.call_count == 3
    finally:
        sys.modules.pop("playwright", None)
        sys.modules.pop("playwright.async_api", None)


@pytest.mark.asyncio
async def test_context_pool_concurrent_access() -> None:
    """Test multiple concurrent accesses to context pool."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_contexts = [AsyncMock() for _ in range(5)]
    crawler.context_pool = asyncio.Queue[Any]()
    for ctx in mock_contexts:
        await crawler.context_pool.put(ctx)

    # Concurrently get all contexts
    tasks = [crawler._get_context_from_pool() for _ in range(5)]
    results = await asyncio.gather(*tasks)

    # All contexts should be retrieved
    assert len(results) == 5
    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 0
    assert set(results) == set(mock_contexts)


@pytest.mark.asyncio
async def test_context_pool_get_return_cycle() -> None:
    """Test complete get-return cycle maintains pool integrity."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    initial_pool_size = 1
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    # Get from pool
    ctx = await crawler._get_context_from_pool()
    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 0

    # Return to pool
    await crawler._return_context_to_pool(ctx)
    assert crawler.context_pool.qsize() == initial_pool_size

    # Pool should be in same state
    # Removed direct index access - Queue doesn't support indexing


@pytest.mark.asyncio
async def test_context_pool_lock_prevents_race_conditions() -> None:
    """Test context pool lock prevents race conditions."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    results: list[Any] = []

    async def get_context() -> None:
        ctx = await crawler._get_context_from_pool()
        results.append(ctx)

    # Try to get same context concurrently
    # Only one should succeed immediately, other should wait
    tasks = [get_context(), get_context()]

    # Add context back after first retrieval
    async def add_context() -> None:
        await asyncio.sleep(0.15)
        await crawler._return_context_to_pool(mock_context)

    await asyncio.gather(*tasks, add_context())

    # Both should have retrieved contexts
    assert len(results) == 2


@pytest.mark.asyncio
async def test_fetch_page_js_basic() -> None:
    """Test basic JavaScript page fetch."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    # Mock Playwright components
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body><h1>Test</h1></body></html>")
    mock_page.evaluate = AsyncMock(
        side_effect=[
            ["https://example.com/link1", "https://example.com/link2"],  # Links
            ["https://example.com/style.css"],  # Assets
        ]
    )
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    result = await crawler._fetch_page_js("https://example.com/test", None)

    assert result is not None
    assert result.url == "https://example.com/test"
    assert "<h1>Test</h1>" in result.html
    assert result.status_code == 200
    assert len(result.links) == 2
    assert len(result.assets) == 1


@pytest.mark.asyncio
async def test_fetch_page_js_respects_robots_txt() -> None:
    """Test JavaScript fetch respects robots.txt."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True), respect_robots_txt=True),
    )
    crawler = Crawler(config)

    # Mock robots.txt checker
    mock_robots_checker = AsyncMock()
    mock_robots_checker.is_allowed = AsyncMock(return_value=False)
    crawler.robots_checker = mock_robots_checker

    result = await crawler._fetch_page_js("https://example.com/blocked", None)

    assert result is None
    mock_robots_checker.is_allowed.assert_called_once_with("https://example.com/blocked")


@pytest.mark.asyncio
async def test_fetch_page_js_timeout_error() -> None:
    """Test JavaScript fetch handles timeout errors."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_timeout_ms=5000)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=Exception("Timeout exceeded"))
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    result = await crawler._fetch_page_js("https://example.com/slow", None)

    assert result is None
    assert crawler.stats.pages_failed == 1


@pytest.mark.asyncio
async def test_fetch_page_js_navigation_error() -> None:
    """Test JavaScript fetch handles navigation errors."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=Exception("net::ERR_NAME_NOT_RESOLVED"))
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    result = await crawler._fetch_page_js("https://invalid.example.com", None)

    assert result is None
    assert crawler.stats.pages_failed == 1


@pytest.mark.asyncio
async def test_fetch_page_js_closes_page() -> None:
    """Test page is closed after fetch (success or failure)."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(side_effect=[[], []])
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    await crawler._fetch_page_js("https://example.com", None)

    mock_page.close.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_page_js_returns_context_to_pool() -> None:
    """Test context is returned to pool after fetch."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(side_effect=[[], []])
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    assert crawler.context_pool.qsize() == 1

    await crawler._fetch_page_js("https://example.com", None)

    # Context should be returned to pool
    assert crawler.context_pool is not None
    assert crawler.context_pool.qsize() == 1


@pytest.mark.asyncio
async def test_fetch_page_js_wait_strategy_domcontentloaded() -> None:
    """Test JavaScript fetch with domcontentloaded wait strategy."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(
            javascript=JavaScriptConfig(enabled=True, wait_for="domcontentloaded")
        ),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(side_effect=[[], []])
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    await crawler._fetch_page_js("https://example.com", None)

    mock_page.goto.assert_called_once()
    call_args = mock_page.goto.call_args
    assert call_args is not None
    kwargs = call_args[1]
    assert kwargs["wait_until"] == "domcontentloaded"


@pytest.mark.asyncio
async def test_fetch_page_js_wait_strategy_load() -> None:
    """Test JavaScript fetch with load wait strategy."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True, wait_for="load")),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(side_effect=[[], []])
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    await crawler._fetch_page_js("https://example.com", None)

    call_args = mock_page.goto.call_args
    assert call_args is not None
    kwargs = call_args[1]
    assert kwargs["wait_until"] == "load"


@pytest.mark.asyncio
async def test_fetch_page_js_updates_stats() -> None:
    """Test JavaScript fetch updates crawler stats."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    html_content = "<html><body>Test content</body></html>"
    mock_page.content = AsyncMock(return_value=html_content)
    mock_page.evaluate = AsyncMock(
        side_effect=[
            ["https://example.com/link"],
            ["https://example.com/img.png", "https://example.com/style.css"],
        ]
    )
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    await crawler._fetch_page_js("https://example.com", None)

    assert crawler.stats.pages_crawled == 1
    assert crawler.stats.total_bytes == len(html_content)
    assert crawler.stats.assets_discovered == 2


@pytest.mark.asyncio
async def test_fetch_page_js_adds_links_to_queue() -> None:
    """Test JavaScript fetch adds valid links to queue."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(
        side_effect=[
            ["https://example.com/page1", "https://example.com/page2"],
            [],
        ]
    )
    mock_context.new_page = AsyncMock(return_value=mock_page)

    crawler.playwright_browser = AsyncMock()
    crawler.context_pool = asyncio.Queue[Any]()
    await crawler.context_pool.put(mock_context)

    await crawler._fetch_page_js("https://example.com", None)

    # Queue should have new links added (if they pass rules)
    assert not crawler.queue.empty()


@pytest.mark.asyncio
async def test_extract_links_js_basic() -> None:
    """Test extracting links from JavaScript-rendered page."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
    )
    crawler = Crawler(config)

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(
        return_value=[
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page1",  # Duplicate
        ]
    )

    links = await crawler._extract_links_js(mock_page, "https://example.com")

    assert len(links) == 2  # Deduplicated
    assert "https://example.com/page1" in links
    assert "https://example.com/page2" in links


@pytest.mark.asyncio
async def test_extract_links_js_error_handling() -> None:
    """Test link extraction handles errors gracefully."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
    )
    crawler = Crawler(config)

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(side_effect=Exception("Evaluation failed"))

    links = await crawler._extract_links_js(mock_page, "https://example.com")

    assert links == []


@pytest.mark.asyncio
async def test_extract_assets_js_basic() -> None:
    """Test extracting assets from JavaScript-rendered page."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
    )
    crawler = Crawler(config)

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(
        return_value=[
            "https://example.com/style.css",
            "https://example.com/img.png",
            "https://example.com/script.js",
            "https://example.com/img.png",  # Duplicate
        ]
    )

    assets = await crawler._extract_assets_js(mock_page, "https://example.com")

    assert len(assets) == 3  # Deduplicated
    assert "https://example.com/style.css" in assets
    assert "https://example.com/img.png" in assets
    assert "https://example.com/script.js" in assets


@pytest.mark.asyncio
async def test_extract_assets_js_error_handling() -> None:
    """Test asset extraction handles errors gracefully."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
    )
    crawler = Crawler(config)

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(side_effect=Exception("Evaluation failed"))

    assets = await crawler._extract_assets_js(mock_page, "https://example.com")

    assert assets == []


@pytest.mark.asyncio
async def test_extract_assets_js_empty_page() -> None:
    """Test asset extraction from page with no assets."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
    )
    crawler = Crawler(config)

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=[])

    assets = await crawler._extract_assets_js(mock_page, "https://example.com")

    assert assets == []


@pytest.mark.asyncio
async def test_fetch_page_routes_to_js_when_enabled() -> None:
    """Test _fetch_page routes to JS rendering when enabled."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    # Mock _fetch_page_js
    mock_result = Mock(spec=CrawlResult)
    mock_fetch_js = AsyncMock(return_value=mock_result)
    with patch.object(crawler, "_fetch_page_js", new=mock_fetch_js):
        result = await crawler._fetch_page("https://example.com", None)

        assert result is mock_result
        mock_fetch_js.assert_called_once_with("https://example.com", None)


@pytest.mark.asyncio
async def test_fetch_page_routes_to_http_when_disabled() -> None:
    """Test _fetch_page routes to HTTP when JS disabled."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=False)),
    )

    # Need to create a proper mock client
    mock_client = AsyncMock()
    crawler = Crawler(config, client=mock_client)

    # Mock _fetch_page_http
    mock_result = Mock(spec=CrawlResult)
    mock_fetch_http = AsyncMock(return_value=mock_result)
    with patch.object(crawler, "_fetch_page_http", new=mock_fetch_http):
        result = await crawler._fetch_page("https://example.com", None)

        assert result is mock_result
        mock_fetch_http.assert_called_once_with("https://example.com", None)


@pytest.mark.asyncio
async def test_fetch_page_js_disabled_by_default() -> None:
    """Test JavaScript rendering is disabled by default."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
    )

    assert config.crawling.javascript.enabled is False


@pytest.mark.asyncio
async def test_crawl_integration_disabled_config() -> None:
    """Test crawler with JS explicitly disabled uses HTTP fetching."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=False)),
    )

    # Mock HTTP client
    mock_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = "<html><body>HTTP content</body></html>"
    mock_client.get = AsyncMock(return_value=mock_response)

    crawler = Crawler(config, client=mock_client)

    # Should use HTTP, not initialize browser
    results: list[CrawlResult] = []
    async for result in crawler.crawl():
        results.append(result)
        if len(results) >= 1:
            break

    # Browser should never be initialized
    assert crawler.playwright_browser is None
    assert crawler.context_pool is None


@pytest.mark.asyncio
async def test_browser_cleanup_on_crawl_finish() -> None:
    """Test browser is cleaned up when crawl finishes."""
    config = SusConfig(
        name="test",
        site=SiteConfig(start_urls=["https://example.com"], allowed_domains=["example.com"]),
        crawling=CrawlingRules(javascript=JavaScriptConfig(enabled=True)),
    )
    crawler = Crawler(config)

    # Mock browser components
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(side_effect=[[], []])
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    # Create mock playwright modules
    mock_pw_module, mock_async_api = create_mock_playwright_module(mock_playwright)
    sys.modules["playwright"] = mock_pw_module
    sys.modules["playwright.async_api"] = mock_async_api

    try:
        # Run crawl (will process start_urls)
        results: list[CrawlResult] = []
        gen = crawler.crawl()
        try:
            async for result in gen:
                results.append(result)
                if len(results) >= 1:
                    break
        finally:
            # Properly close the generator to trigger cleanup
            await gen.aclose()

        # Browser should be cleaned up after generator is closed
        mock_browser.close.assert_called()
        mock_playwright.stop.assert_called()
    finally:
        sys.modules.pop("playwright", None)
        sys.modules.pop("playwright.async_api", None)
