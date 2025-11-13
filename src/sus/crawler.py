"""Async web crawler with rate limiting and concurrency control."""

import asyncio
import logging
import urllib.parse
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import httpx
import lxml.html
from robotexclusionrulesparser import RobotFileParserLookalike

from sus.config import SusConfig
from sus.rules import LinkExtractor, RulesEngine, URLNormalizer

logger = logging.getLogger(__name__)


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
        self.last_update = asyncio.get_event_loop().time()
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
                now = asyncio.get_event_loop().time()
                time_passed = now - self.last_update
                self.last_update = now

                # Add tokens based on time passed
                self.tokens = min(self.burst, self.tokens + time_passed * self.rate)

                # Try to consume a token
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


@dataclass
class CrawlerStats:
    """Statistics collected during crawl.

    Tracks pages crawled, failures, bytes downloaded, and errors by type.
    """

    pages_crawled: int = 0
    pages_failed: int = 0
    assets_discovered: int = 0
    total_bytes: int = 0
    start_time: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    error_counts: dict[str, int] = field(default_factory=dict)  # error_type -> count


class RobotsTxtChecker:
    """Checks robots.txt files to determine if URLs can be crawled.

    Caches robots.txt files per domain to avoid re-fetching. On fetch errors,
    defaults to allowing the URL (graceful degradation).

    Example:
        >>> checker = RobotsTxtChecker(client, user_agent="MyBot/1.0")
        >>> allowed = await checker.is_allowed("https://example.com/page")
    """

    def __init__(self, client: httpx.AsyncClient, user_agent: str = "SUS/0.1.0") -> None:
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

        # Check cache
        if domain not in self._cache:
            # Fetch robots.txt
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
                logger.debug(f"Failed to fetch robots.txt for {domain}: {e}")
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
    ) -> None:
        """Initialize crawler.

        Args:
            config: Validated configuration
            client: Optional HTTP client (for testing with mocks)
        """
        self.config = config
        self.client = client  # If None, create default in crawl()
        self.visited: set[str] = set()
        self.queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()  # (url, parent_url)
        self.stats = CrawlerStats()

        # Initialize semaphores for concurrency control
        self.global_semaphore = asyncio.Semaphore(config.crawling.global_concurrent_requests)
        self.domain_semaphores: dict[str, asyncio.Semaphore] = {}  # domain -> semaphore

        # Initialize rate limiter
        rate = (
            1.0 / config.crawling.delay_between_requests
            if config.crawling.delay_between_requests > 0
            else 1000.0
        )
        self.rate_limiter = RateLimiter(rate=rate, burst=config.crawling.rate_limiter_burst_size)

        # Per-domain retry counters
        self.retry_counters: dict[str, int] = {}  # url -> retry_count

        # Initialize RulesEngine and LinkExtractor
        self.rules_engine = RulesEngine(config)
        self.link_extractor = LinkExtractor(config.crawling.link_selectors)

        # robots.txt checker (initialized when client is created)
        self.robots_checker: RobotsTxtChecker | None = None

    async def crawl(self) -> AsyncGenerator[CrawlResult, None]:
        """Crawl pages starting from start_urls.

        Implements queue-based crawling with concurrency control. Pages are
        fetched in parallel up to the configured concurrency limits, and new
        links are added to the queue as they are discovered.

        Yields:
            CrawlResult for each successfully crawled page
        """
        # 1. Create HTTP client if not provided
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "SUS/0.1.0 (Simple Universal Scraper)"},
            )

        # Initialize robots.txt checker if respect_robots_txt is enabled
        if self.config.crawling.respect_robots_txt and self.robots_checker is None:
            self.robots_checker = RobotsTxtChecker(
                self.client, user_agent="SUS/0.1.0 (Simple Universal Scraper)"
            )

        try:
            # 2. Add start_urls to queue (normalized)
            for url in self.config.site.start_urls:
                normalized_url = URLNormalizer.normalize_url(url)
                await self.queue.put((normalized_url, None))

            # 3. Process queue with concurrency control
            tasks: list[asyncio.Task[CrawlResult | None]] = []
            max_pages = self.config.crawling.max_pages

            while not self.queue.empty() or tasks:
                # Check max_pages limit
                if max_pages and self.stats.pages_crawled >= max_pages:
                    break

                # Launch workers up to concurrency limit
                while (
                    len(tasks) < self.config.crawling.global_concurrent_requests
                    and not self.queue.empty()
                ):
                    url, parent_url = await self.queue.get()

                    # Skip if already visited
                    if url in self.visited:
                        continue

                    self.visited.add(url)

                    # Create task to fetch page
                    task = asyncio.create_task(self._fetch_page(url, parent_url))
                    tasks.append(task)

                # Wait for at least one task to complete
                if tasks:
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(pending)

                    # Process completed tasks
                    for task in done:
                        result = await task
                        if result:
                            yield result

        finally:
            # 4. Close client if we created it
            if self.client:
                await self.client.aclose()

    async def _fetch_page(self, url: str, parent_url: str | None) -> CrawlResult | None:
        """Fetch a single page with rate limiting and retries.

        Implements exponential backoff retry logic and per-domain concurrency
        control. Skips non-HTML content and handles errors gracefully.

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

        # 3. Get or create per-domain semaphore
        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(
                self.config.crawling.per_domain_concurrent_requests
            )

        # 4. Acquire both global and per-domain semaphores
        async with self.global_semaphore, self.domain_semaphores[domain]:
            # 5. Wait for rate limit
            await self.rate_limiter.acquire()

            # 6. Fetch with retry logic
            retry_count = 0
            max_retries = self.config.crawling.max_retries
            backoff = self.config.crawling.retry_backoff

            while retry_count <= max_retries:
                try:
                    # Make HTTP request
                    response = await self.client.get(url)  # type: ignore[union-attr]
                    response.raise_for_status()

                    # Check content-type
                    content_type = response.headers.get("content-type", "")
                    if "text/html" not in content_type.lower():
                        # Skip non-HTML content
                        return None

                    # Parse HTML and extract links/assets
                    html = response.text
                    links_set = self.link_extractor.extract_links(html, url)
                    links = list(links_set)
                    assets = self._extract_assets(html, url)

                    # Add new links to queue (if they pass rules)
                    for link in links:
                        # Normalize link first
                        normalized_link = URLNormalizer.normalize_url(link)
                        if self.rules_engine.should_follow(normalized_link, url):
                            await self.queue.put((normalized_link, url))

                    # Update stats
                    self.stats.pages_crawled += 1
                    self.stats.total_bytes += len(html)
                    self.stats.assets_discovered += len(assets)

                    return CrawlResult(
                        url=url,
                        html=html,
                        status_code=response.status_code,
                        content_type=content_type,
                        links=links,
                        assets=assets,
                    )

                except httpx.HTTPError as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        # Max retries exceeded
                        self.stats.pages_failed += 1
                        error_type = type(e).__name__
                        self.stats.error_counts[error_type] = (
                            self.stats.error_counts.get(error_type, 0) + 1
                        )
                        return None

                    # Exponential backoff
                    wait_time = backoff**retry_count
                    await asyncio.sleep(wait_time)

            return None

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
            # Parse HTML with lxml
            doc = lxml.html.fromstring(html)
            doc.make_links_absolute(base_url)  # type: ignore[attr-defined]

            assets: set[str] = set()

            # Extract images
            for img in doc.xpath("//img[@src]"):  # type: ignore[union-attr]
                src = img.get("src")  # type: ignore[union-attr]
                if src:
                    assets.add(src)

            # Extract CSS
            for link in doc.xpath("//link[@rel='stylesheet'][@href]"):  # type: ignore[union-attr]
                href = link.get("href")  # type: ignore[union-attr]
                if href:
                    assets.add(href)

            # Extract JavaScript
            for script in doc.xpath("//script[@src]"):  # type: ignore[union-attr]
                src = script.get("src")  # type: ignore[union-attr]
                if src:
                    assets.add(src)

            return sorted(assets)  # Sort for deterministic output

        except Exception:
            # If parsing fails, return empty list
            # Don't let asset extraction failures stop the crawl
            return []
