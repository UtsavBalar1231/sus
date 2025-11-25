"""Async web crawler.

Async HTTP crawling with token bucket rate limiting, concurrency control, and robots.txt
compliance via Crawler (queue-based) and RateLimiter (burst-friendly throttling).

Supports optional JavaScript rendering via Playwright for SPAs and JS-heavy sites.
"""

import asyncio
import contextlib
import logging
import time
import urllib.parse
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import httpx
import lxml.html
from robotexclusionrulesparser import RobotFileParserLookalike

from sus.auth import AuthCredentials, SessionManager
from sus.config import SusConfig
from sus.http_client import create_http_client
from sus.rules import LinkExtractor, RulesEngine, URLNormalizer

if TYPE_CHECKING:
    from sus.checkpoint_manager import CheckpointManager
    from sus.types import LxmlDocument, LxmlElement
from sus.sitemap import SitemapParser

logger = logging.getLogger(__name__)


class SusAuth(httpx.Auth):
    """httpx Auth adapter for SessionManager."""

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize auth handler.

        Args:
            session_manager: SessionManager instance for preparing authenticated requests
        """
        self.session_manager = session_manager

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Prepare request with authentication credentials.

        Args:
            request: HTTP request to authenticate

        Yields:
            Authenticated HTTP request
        """
        await self.session_manager.prepare_request(request)
        yield request


class RateLimiter:
    """Token bucket rate limiter for burst-friendly rate limiting.

    The token bucket algorithm allows for bursts of requests while maintaining
    an average rate limit over time. Tokens are added to the bucket at a constant
    rate, and each request consumes one token.

    Example:
        >>> limiter = RateLimiter(rate=2.0, burst=5)
        >>> await limiter.acquire()  # Consumes 1 token
    """

    def __init__(self, rate: float, burst: int = 5) -> None:
        """Initialize rate limiter.

        Args:
            rate: Requests per second (e.g., 2.0 = 0.5s average delay)
            burst: Maximum burst size (tokens in bucket)
        """
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary.

        Implements the token bucket algorithm:
        1. Calculate tokens added since last update (time_passed * rate)
        2. Add tokens (cap at burst size)
        3. If tokens >= 1, consume token and return
        4. Otherwise, sleep until next token available
        """
        async with self._lock:
            while True:
                now = time.time()
                time_passed = now - self.last_update
                self.last_update = now

                self.tokens = min(self.burst, self.tokens + time_passed * self.rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                # Calculate time until next token available
                sleep_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(sleep_time)


@dataclass
class CrawlResult:
    """Result from crawling a single page.

    Contains the page content, metadata, and extracted links/assets.
    """

    url: str
    html: str
    status_code: int
    content_type: str
    links: list[str]  # Extracted links (absolute URLs)
    assets: list[str]  # Extracted asset URLs (images, CSS, JS)
    content_hash: str = ""  # SHA-256 hash of HTML content (for change detection)
    queue_size: int = 0  # Current size of crawl queue (for progress tracking)


@dataclass
class CrawlerStats:
    """Statistics collected during crawl.

    Tracks pages crawled, failures, bytes downloaded, and errors by type.
    """

    pages_crawled: int = 0
    pages_failed: int = 0
    assets_discovered: int = 0
    total_bytes: int = 0
    start_time: float = field(default_factory=time.time)
    error_counts: dict[str, int] = field(default_factory=dict)  # error_type -> count


class RobotsTxtChecker:
    """Checks robots.txt files to determine if URLs can be crawled.

    Caches robots.txt files per domain to avoid re-fetching. On fetch errors,
    defaults to allowing the URL (graceful degradation).

    Example:
        >>> checker = RobotsTxtChecker(client, user_agent="MyBot/1.0")
        >>> allowed = await checker.is_allowed("https://example.com/page")
    """

    def __init__(self, client: httpx.AsyncClient, user_agent: str = "SUS/0.2.0") -> None:
        """Initialize robots.txt checker.

        Args:
            client: HTTP client for fetching robots.txt files
            user_agent: User agent string to use for checking rules
        """
        self.client = client
        self.user_agent = user_agent
        self._cache: dict[str, RobotFileParserLookalike] = {}  # domain -> parser

    async def is_allowed(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt.

        Args:
            url: URL to check

        Returns:
            True if allowed (or on fetch error), False if disallowed
        """
        parsed = urllib.parse.urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self._cache:
            robots_url = f"{domain}/robots.txt"
            try:
                response = await self.client.get(robots_url, timeout=10.0)
                if response.status_code == 200:
                    parser = RobotFileParserLookalike()
                    parser.parse(response.text.splitlines())
                    self._cache[domain] = parser
                    logger.debug(f"Loaded robots.txt for {domain}")
                else:
                    # No robots.txt or error - allow everything
                    parser = RobotFileParserLookalike()
                    parser.parse([])  # Empty robots.txt
                    self._cache[domain] = parser
                    logger.debug(f"No robots.txt for {domain} (status {response.status_code})")
            except Exception as e:
                # On error, default to allowing (graceful degradation)
                # Warn user since this affects robots.txt compliance
                logger.warning(
                    f"Failed to fetch robots.txt for {domain}: {e}. Proceeding without it."
                )
                parser = RobotFileParserLookalike()
                parser.parse([])
                self._cache[domain] = parser

        parser = self._cache[domain]
        return bool(parser.is_allowed(self.user_agent, url))


class Crawler:
    """Async web crawler with rate limiting and concurrency control.

    Features:
    - Token bucket rate limiting for burst-friendly rate control
    - Global and per-domain concurrency limits
    - Exponential backoff retry logic
    - Dependency injection for testability
    - Content-type aware handling

    Example:
        >>> config = load_config(Path("config.yaml"))
        >>> crawler = Crawler(config)
        >>> async for result in crawler.crawl():
        ...     print(f"Crawled: {result.url}")
    """

    def __init__(
        self,
        config: SusConfig,
        client: httpx.AsyncClient | None = None,
        checkpoint: "CheckpointManager | None" = None,
    ) -> None:
        """Initialize crawler.

        Args:
            config: Validated configuration
            client: Optional HTTP client (for testing with mocks)
            checkpoint: Optional checkpoint manager for resume functionality
        """
        self.config = config
        self.client = client  # If None, create default in crawl()
        self.checkpoint = checkpoint
        self.visited: set[str] = set()
        self.queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()  # (url, parent_url)
        self._queue_lock = asyncio.Lock()  # Protects queue snapshot for checkpoints
        self.stats = CrawlerStats()

        self.global_semaphore = asyncio.Semaphore(config.crawling.global_concurrent_requests)
        self.domain_semaphores: dict[str, asyncio.Semaphore] = {}  # domain -> semaphore

        rate = (
            1.0 / config.crawling.delay_between_requests
            if config.crawling.delay_between_requests > 0
            else 1000.0
        )
        self.rate_limiter = RateLimiter(rate=rate, burst=config.crawling.rate_limiter_burst_size)

        self.rules_engine = RulesEngine(config)
        self.link_extractor = LinkExtractor(config.crawling.link_selectors)

        self.robots_checker: RobotsTxtChecker | None = None

        # Authentication - initialized in crawl() if enabled
        self.session_manager: SessionManager | None = None

        # JavaScript rendering (Playwright) - initialized on first use
        self.playwright: Any | None = None
        self.playwright_browser: Any | None = None
        self.context_pool: asyncio.Queue[Any] | None = None

    async def _ensure_client(self) -> None:
        """Ensure HTTP client is initialized."""
        if self.client is None:
            auth_handler = None
            if self.session_manager:
                auth_handler = SusAuth(self.session_manager)
            self.client = create_http_client(self.config, auth_handler)

    async def get_queue_snapshot(self) -> list[tuple[str, str | None]]:
        """Get a snapshot of the current crawl queue for checkpoint serialization.

        Returns a list copy of all items currently in the queue. This method
        accesses the internal queue state but provides a proper public API
        for checkpoint serialization.

        Uses an async lock to ensure snapshot consistency during concurrent
        queue operations. While asyncio is single-threaded, the lock makes
        the synchronization intent explicit.

        Note: asyncio.Queue doesn't provide a public API to inspect queue contents
        without modifying it, so we must access the private _queue attribute.
        This is acceptable here as we're only reading, not modifying, and it's
        the standard approach for queue introspection in asyncio code.

        Returns:
            List of (url, parent_url) tuples representing the current queue state
        """
        async with self._queue_lock:
            # Access private _queue attribute - no public API exists for non-destructive inspection
            return list(self.queue._queue)  # type: ignore[attr-defined]

    async def crawl(self) -> AsyncGenerator[CrawlResult, None]:
        """Crawl pages starting from start_urls.

        Implements queue-based crawling with concurrency control. Pages are
        fetched in parallel up to the configured concurrency limits, and new
        links are added to the queue as they are discovered.

        Yields:
            CrawlResult for each successfully crawled page
        """
        if self.config.crawling.authentication.enabled:
            auth_cfg = self.config.crawling.authentication
            if auth_cfg.auth_type is None:
                raise ValueError("auth_type must be specified when authentication.enabled=True")

            # Create credentials from config
            credentials = AuthCredentials(
                username=auth_cfg.username,
                password=auth_cfg.password,
                cookies=auth_cfg.cookies,
                headers=auth_cfg.headers,
                client_id=auth_cfg.client_id,
                client_secret=auth_cfg.client_secret,
                token_url=auth_cfg.token_url,
                scope=auth_cfg.scope,
            )

            # Create session manager
            self.session_manager = SessionManager(auth_cfg.auth_type, credentials)
            await self.session_manager.__aenter__()

        await self._ensure_client()
        assert self.client is not None  # Help mypy understand client is initialized

        if self.config.crawling.respect_robots_txt and self.robots_checker is None:
            self.robots_checker = RobotsTxtChecker(
                self.client, user_agent="SUS/0.2.0 (Simple Universal Scraper)"
            )

        try:
            checkpoint_has_pages = False
            if self.checkpoint:
                # Load visited URLs from checkpoint
                self.visited = await self.checkpoint.get_all_page_urls()
                checkpoint_has_pages = len(self.visited) > 0
                for url, parent_url in self.checkpoint.queue:
                    await self.queue.put((url, parent_url))

            # Only skip start URLs if checkpoint has actual pages (meaning we're resuming)
            if not self.checkpoint or not checkpoint_has_pages:
                for url in self.config.site.start_urls:
                    normalized_url = URLNormalizer.normalize_url(url)
                    await self.queue.put((normalized_url, None))

            sitemap_urls = await self._load_from_sitemap()
            for url in sitemap_urls:
                await self.queue.put((url, None))

            tasks: list[asyncio.Task[CrawlResult | None]] = []
            max_pages = self.config.crawling.max_pages

            while not self.queue.empty() or tasks:
                if max_pages and self.stats.pages_crawled >= max_pages:
                    break

                while (
                    len(tasks) < self.config.crawling.global_concurrent_requests
                    and not self.queue.empty()
                ):
                    url, parent_url = await self.queue.get()

                    if url in self.visited:
                        continue

                    self.visited.add(url)

                    task = asyncio.create_task(self._fetch_page(url, parent_url))
                    tasks.append(task)

                if tasks:
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(pending)

                    for task in done:
                        result = await task
                        if result:
                            yield result

            # Wait for all remaining tasks to complete before cleanup
            if tasks:
                logger.debug(f"Waiting for {len(tasks)} remaining tasks to complete...")
                done, _ = await asyncio.wait(tasks)
                for task in done:
                    result = await task
                    if result:
                        yield result

        finally:
            if self.session_manager:
                await self.session_manager.__aexit__(None, None, None)
                self.session_manager = None

            await self._close_browser()

            if self.client:
                await self.client.aclose()

    async def _fetch_page(self, url: str, parent_url: str | None) -> CrawlResult | None:
        """Fetch a single page with rate limiting and retries.

        Routes to JavaScript rendering (_fetch_page_js) if enabled, otherwise
        uses HTTP-only fetching (_fetch_page_http).

        Args:
            url: URL to fetch
            parent_url: Parent URL (for tracking depth)

        Returns:
            CrawlResult on success, None on failure
        """
        if self.checkpoint and self.config.crawling.checkpoint.enabled:
            # Check if page should be redownloaded
            should_redownload = await self.checkpoint.should_redownload(
                url, self.config.crawling.checkpoint.force_redownload_after_days
            )
            if not should_redownload:
                logger.debug(f"Skipping {url} - valid in checkpoint")
                return None

        if self.config.crawling.javascript.enabled:
            return await self._fetch_page_js(url, parent_url)
        else:
            return await self._fetch_page_http(url, parent_url)

    async def _fetch_page_http(self, url: str, parent_url: str | None) -> CrawlResult | None:
        """Fetch a single page via HTTP with rate limiting and retries.

        Implements exponential backoff retry logic and per-domain concurrency
        control. Skips non-HTML content and handles errors gracefully.

        Args:
            url: URL to fetch
            parent_url: Parent URL (for tracking depth)

        Returns:
            CrawlResult on success, None on failure
        """
        assert self.client is not None  # Client initialized in crawl()

        domain = urllib.parse.urlparse(url).netloc

        if self.robots_checker is not None:
            allowed = await self.robots_checker.is_allowed(url)
            if not allowed:
                logger.info(f"URL disallowed by robots.txt: {url}")
                return None

        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(
                self.config.crawling.per_domain_concurrent_requests
            )

        async with self.global_semaphore, self.domain_semaphores[domain]:
            await self.rate_limiter.acquire()

            # Retries handled automatically by RetryTransport
            try:
                response = await self.client.get(url)
                response.raise_for_status()

                content_length = response.headers.get("content-length")
                if content_length and self.config.crawling.max_page_size_mb:
                    try:
                        size_mb = int(content_length) / (1024 * 1024)
                        if size_mb > self.config.crawling.max_page_size_mb:
                            self.stats.pages_failed += 1
                            self.stats.error_counts["FileTooLarge"] = (
                                self.stats.error_counts.get("FileTooLarge", 0) + 1
                            )
                            max_page_mb = self.config.crawling.max_page_size_mb
                            print(
                                f"Skipping {url}: {size_mb:.1f}MB exceeds limit of {max_page_mb}MB"
                            )
                            return None
                    except ValueError:
                        # Invalid Content-Length header - skip check, proceed with download
                        pass

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type.lower():
                    # Skip non-HTML content
                    return None

                html = response.text
                links_set = self.link_extractor.extract_links(html, url)
                links = list(links_set)
                assets = self._extract_assets(html, url)

                for link in links:
                    # Normalize link first
                    normalized_link = URLNormalizer.normalize_url(link)
                    if self.rules_engine.should_follow(normalized_link, url):
                        await self.queue.put((normalized_link, url))

                self.stats.pages_crawled += 1
                self.stats.total_bytes += len(html)
                self.stats.assets_discovered += len(assets)

                from sus.backends import compute_content_hash

                content_hash = compute_content_hash(html)

                # Capture queue size for progress tracking
                current_queue_size = self.queue.qsize()

                return CrawlResult(
                    url=url,
                    html=html,
                    status_code=response.status_code,
                    content_type=content_type,
                    links=links,
                    assets=assets,
                    content_hash=content_hash,
                    queue_size=current_queue_size,
                )

            except httpx.TooManyRedirects:
                self.stats.pages_failed += 1
                self.stats.error_counts["TooManyRedirects"] = (
                    self.stats.error_counts.get("TooManyRedirects", 0) + 1
                )
                max_redirects = self.config.crawling.max_redirects
                print(f"Redirect loop detected: {url} (exceeded {max_redirects} redirects)")
                return None

            except httpx.HTTPError as e:
                # Retries are handled by RetryTransport, so if we get here, all retries failed
                self.stats.pages_failed += 1
                error_type = type(e).__name__
                self.stats.error_counts[error_type] = self.stats.error_counts.get(error_type, 0) + 1
                # Log failure to console so users see what's happening
                logger.warning(f"HTTP error fetching {url}: {error_type}")
                return None

    # ========== JavaScript Rendering ==========

    async def _ensure_browser(self) -> None:
        """Initialize Playwright browser and create context pool.

        Raises:
            ImportError: If playwright is not installed
        """
        if self.playwright_browser is not None:
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise ImportError(
                "Playwright is required for JavaScript rendering. "
                "Install with: uv sync --group js && uv run playwright install chromium"
            ) from e

        logger.info("Initializing Playwright browser...")
        self.playwright = await async_playwright().start()
        self.playwright_browser = await self.playwright.chromium.launch(headless=True)

        # Create context pool using asyncio.Queue
        js_config = self.config.crawling.javascript
        self.context_pool = asyncio.Queue(maxsize=js_config.context_pool_size)
        logger.info(f"Creating browser context pool (size={js_config.context_pool_size})...")
        for _ in range(js_config.context_pool_size):
            context = await self._create_browser_context()
            await self.context_pool.put(context)

        logger.info("Playwright browser initialized successfully")

    async def _create_browser_context(self) -> Any:
        """Create a new browser context with configured settings.

        Returns:
            Browser context object
        """
        assert self.playwright_browser is not None  # Help mypy

        js_config = self.config.crawling.javascript

        context_options: dict[str, Any] = {
            "viewport": {
                "width": js_config.viewport_width,
                "height": js_config.viewport_height,
            },
            "java_script_enabled": js_config.javascript_enabled,
        }

        if js_config.user_agent_override:
            context_options["user_agent"] = js_config.user_agent_override

        return await self.playwright_browser.new_context(**context_options)

    async def _get_context_from_pool(self) -> Any:
        """Get a browser context from the pool (waits if empty).

        Returns:
            Browser context object
        """
        assert self.context_pool is not None
        return await self.context_pool.get()

    async def _return_context_to_pool(self, context: Any) -> None:
        """Return a browser context to the pool for reuse.

        Args:
            context: Browser context to return
        """
        assert self.context_pool is not None
        await self.context_pool.put(context)

    async def _fetch_page_js(self, url: str, parent_url: str | None) -> CrawlResult | None:
        """Fetch a page using Playwright for JavaScript rendering.

        Args:
            url: URL to fetch
            parent_url: Parent URL (for tracking depth)

        Returns:
            CrawlResult on success, None on failure
        """
        # 1. Get domain from URL
        domain = urllib.parse.urlparse(url).netloc

        # 2. Check robots.txt if enabled
        if self.robots_checker is not None:
            allowed = await self.robots_checker.is_allowed(url)
            if not allowed:
                logger.info(f"URL disallowed by robots.txt: {url}")
                return None

        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(
                self.config.crawling.per_domain_concurrent_requests
            )

        async with self.global_semaphore, self.domain_semaphores[domain]:
            await self.rate_limiter.acquire()
            await self._ensure_browser()
            context = await self._get_context_from_pool()

            try:
                page = await context.new_page()

                try:
                    js_config = self.config.crawling.javascript
                    await page.goto(
                        url,
                        wait_until=js_config.wait_for,
                        timeout=js_config.wait_timeout_ms,
                    )

                    html = await page.content()
                    links = await self._extract_links_js(page, url)
                    assets = await self._extract_assets_js(page, url)

                    for link in links:
                        normalized_link = URLNormalizer.normalize_url(link)
                        if self.rules_engine.should_follow(normalized_link, url):
                            await self.queue.put((normalized_link, url))

                    self.stats.pages_crawled += 1
                    self.stats.total_bytes += len(html)
                    self.stats.assets_discovered += len(assets)

                    # Compute content hash for change detection
                    from sus.backends import compute_content_hash

                    content_hash = compute_content_hash(html)

                    # Capture queue size for progress tracking
                    current_queue_size = self.queue.qsize()

                    return CrawlResult(
                        url=url,
                        html=html,
                        status_code=200,  # Playwright doesn't expose status easily
                        content_type="text/html",
                        links=links,
                        assets=assets,
                        content_hash=content_hash,
                        queue_size=current_queue_size,
                    )

                finally:
                    # 14. Close page
                    await page.close()

            except Exception as e:
                # Handle all Playwright errors - warn user since JS render failures are significant
                self.stats.pages_failed += 1
                error_type = type(e).__name__
                self.stats.error_counts[error_type] = self.stats.error_counts.get(error_type, 0) + 1
                logger.warning(f"JS render failed for {url}: {error_type}: {e}")
                return None

            finally:
                # 15. Return context to pool
                await self._return_context_to_pool(context)

    async def _extract_links_js(self, page: Any, base_url: str) -> list[str]:
        """Extract links from rendered page using JavaScript evaluation.

        Args:
            page: Playwright page object
            base_url: Base URL for resolving relative links

        Returns:
            List of absolute link URLs
        """
        try:
            # Use page.evaluate() to extract all links from DOM
            links = await page.evaluate("""
                () => {
                    const anchors = document.querySelectorAll('a[href]');
                    return Array.from(anchors).map(a => a.href);
                }
            """)
            return sorted(set(links))  # Deduplicate and sort
        except Exception as e:
            # If extraction fails, return empty list but warn user
            logger.warning(f"JS link extraction failed for {base_url}: {e}")
            return []

    async def _extract_assets_js(self, page: Any, base_url: str) -> list[str]:
        """Extract asset URLs from rendered page using JavaScript evaluation.

        Args:
            page: Playwright page object
            base_url: Base URL for resolving relative paths

        Returns:
            List of absolute asset URLs (images, CSS, JS)
        """
        try:
            # Use page.evaluate() to extract all assets from DOM
            assets = await page.evaluate("""
                () => {
                    const assets = [];

                    // Extract images
                    document.querySelectorAll('img[src]').forEach(img => {
                        assets.push(img.src);
                    });

                    // Extract CSS
                    document.querySelectorAll('link[rel="stylesheet"][href]').forEach(link => {
                        assets.push(link.href);
                    });

                    // Extract JavaScript
                    document.querySelectorAll('script[src]').forEach(script => {
                        assets.push(script.src);
                    });

                    return assets;
                }
            """)
            return sorted(set(assets))  # Deduplicate and sort
        except Exception as e:
            # If extraction fails, return empty list but warn user
            logger.warning(f"JS asset extraction failed for {base_url}: {e}")
            return []

    async def _close_browser(self) -> None:
        """Close browser and cleanup resources."""
        if self.playwright_browser is not None:
            logger.info("Closing Playwright browser...")

            # Close all contexts in pool
            if self.context_pool is not None:
                while not self.context_pool.empty():
                    context = await self.context_pool.get()
                    with contextlib.suppress(Exception):
                        await context.close()

            # Close browser
            with contextlib.suppress(Exception):
                await self.playwright_browser.close()

            # Stop playwright
            if self.playwright is not None:
                with contextlib.suppress(Exception):
                    await self.playwright.stop()

            self.playwright_browser = None
            self.playwright = None
            self.context_pool = None
            logger.info("Playwright browser closed")

    # ========== End JavaScript Rendering ==========

    # ========== Sitemap Loading ==========

    async def _load_from_sitemap(self) -> list[str]:
        """Load URLs from sitemap.xml files.

        Auto-discovers sitemaps if configured, parses all sitemap URLs,
        sorts by priority if enabled, and applies max_urls limit.

        Returns:
            List of URLs from sitemaps (normalized, deduplicated)
        """
        if not self.config.crawling.sitemap.enabled:
            return []

        assert self.client is not None  # Help mypy understand client is initialized

        sitemap_config = self.config.crawling.sitemap
        parser = SitemapParser(self.client, strict=sitemap_config.strict)

        sitemap_urls: list[str] = []

        # 1. Auto-discover sitemaps if configured
        if sitemap_config.auto_discover:
            # Use first start_url as base for discovery
            base_url = self.config.site.start_urls[0]
            discovered = await parser.discover_sitemaps(base_url)
            sitemap_urls.extend(discovered)
            logger.info(f"Auto-discovered {len(discovered)} sitemap(s)")

        # 2. Add explicit sitemap URLs from config
        sitemap_urls.extend(sitemap_config.urls)

        if not sitemap_urls:
            logger.info("No sitemaps found or configured")
            return []

        # 3. Parse all sitemaps and collect entries
        all_entries = []
        for sitemap_url in sitemap_urls:
            logger.info(f"Parsing sitemap: {sitemap_url}")
            entries = await parser.parse_sitemap(sitemap_url)
            all_entries.extend(entries)
            logger.info(f"  Found {len(entries)} URL(s)")

        logger.info(f"Total URLs from sitemaps: {len(all_entries)}")

        # 4. Sort by priority if enabled (highest first)
        if sitemap_config.respect_priority:
            all_entries.sort(
                key=lambda e: e.priority if e.priority is not None else 0.5,
                reverse=True,
            )
            logger.debug("Sorted URLs by priority (highest first)")

        # 5. Apply max_urls limit if configured
        if sitemap_config.max_urls is not None:
            all_entries = all_entries[: sitemap_config.max_urls]
            logger.info(f"Limited to {sitemap_config.max_urls} URLs from sitemaps")

        # 6. Extract and normalize URLs
        urls = [URLNormalizer.normalize_url(entry.loc) for entry in all_entries]

        # 7. Deduplicate (preserve order)
        seen = set()
        deduplicated = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                deduplicated.append(url)

        logger.info(f"Loaded {len(deduplicated)} unique URL(s) from sitemaps")
        return deduplicated

    # ========== End Sitemap Loading ==========

    def _extract_assets(self, html: str, base_url: str) -> list[str]:
        """Extract asset URLs from HTML (images, CSS, JS).

        Uses lxml to parse HTML and extract asset references from:
        - img[src] tags
        - link[rel=stylesheet][href] tags
        - script[src] tags

        Args:
            html: HTML content
            base_url: Base URL for resolving relative paths

        Returns:
            List of absolute asset URLs (deduplicated)
        """
        try:
            # Parse HTML with lxml (cast to our Protocol for type safety)
            doc = cast("LxmlDocument", lxml.html.fromstring(html))
            doc.make_links_absolute(base_url)

            assets: set[str] = set()

            # Extract images
            for img in doc.xpath("//img[@src]"):
                element = cast("LxmlElement", img)
                src = element.get("src")
                if src:
                    assets.add(src)

            # Extract CSS
            for link in doc.xpath("//link[@rel='stylesheet'][@href]"):
                element = cast("LxmlElement", link)
                href = element.get("href")
                if href:
                    assets.add(href)

            # Extract JavaScript
            for script in doc.xpath("//script[@src]"):
                element = cast("LxmlElement", script)
                src = element.get("src")
                if src:
                    assets.add(src)

            return sorted(assets)  # Sort for deterministic output

        except Exception as e:
            # If parsing fails, return empty list but warn user
            # Don't let asset extraction failures stop the crawl
            logger.warning(f"Asset extraction failed for {base_url}: {e}")
            return []
