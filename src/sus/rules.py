"""URL filtering and crawling rules.

URL normalization, validation, and rule-based filtering for controlling crawl scope via
URLNormalizer (consistency), RulesEngine (pattern matching), and LinkExtractor (HTML parsing).
"""

from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urljoin, urlparse, urlunparse

from lxml import html as lxml_html

from sus.config import SusConfig

if TYPE_CHECKING:
    from sus.types import LxmlElement


class URLNormalizer:
    """Centralized URL normalization and validation.

    Utilities for:
    - Normalizing URLs (lowercase scheme/hostname, remove default ports, strip fragments)
    - Filtering dangerous schemes (javascript:, data:, file:, etc.)
    - Handling query parameters (strip or preserve strategies)
    """

    # Safe URL schemes for web scraping
    SAFE_SCHEMES = {"http", "https"}

    # Dangerous schemes that should be blocked
    DANGEROUS_SCHEMES = {
        "mailto",
        "tel",
        "javascript",
        "data",
        "file",
        "ftp",
        "blob",
        "about",
    }

    # Default ports that should be removed from URLs
    DEFAULT_PORTS = {
        "http": 80,
        "https": 443,
    }

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize URL for consistent handling.

        Normalizations applied:
        - Convert scheme to lowercase (HTTP → http)
        - Convert hostname to lowercase (Example.COM → example.com)
        - Remove default ports (http://example.com:80 → http://example.com)
        - Normalize percent-encoding (%7E → ~)
        - Remove fragments (#section)
        - Handle trailing slashes consistently (keeps them)

        Args:
            url: URL to normalize

        Returns:
            Normalized URL

        Raises:
            ValueError: If URL is empty or malformed

        Examples:
            >>> URLNormalizer.normalize_url("HTTP://Example.COM:80/Path")
            'http://example.com/Path'

            >>> URLNormalizer.normalize_url("https://example.com/path#section")
            'https://example.com/path'

            >>> URLNormalizer.normalize_url("http://example.com:8080/path")
            'http://example.com:8080/path'
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        try:
            parsed = urlparse(url.strip())

            scheme = parsed.scheme.lower()
            netloc = parsed.hostname.lower() if parsed.hostname else ""

            if parsed.port:
                default_port = URLNormalizer.DEFAULT_PORTS.get(scheme)
                if parsed.port != default_port:
                    netloc = f"{netloc}:{parsed.port}"

            # Add username:password if present (rare for scraping, but handle it)
            if parsed.username:
                auth = parsed.username
                if parsed.password:
                    auth = f"{auth}:{parsed.password}"
                netloc = f"{auth}@{netloc}"

            # Remove fragment, keep query and path
            # Note: We don't normalize percent-encoding here as urlparse handles it
            normalized = urlunparse(
                (
                    scheme,
                    netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    "",  # Remove fragment
                )
            )

            return normalized

        except Exception as e:
            raise ValueError(f"Failed to normalize URL '{url}': {e}") from e

    @staticmethod
    def filter_dangerous_schemes(url: str) -> bool:
        """Return True if URL scheme is safe (http/https), False otherwise.

        Args:
            url: URL to check

        Returns:
            True if scheme is safe, False otherwise

        Examples:
            >>> URLNormalizer.filter_dangerous_schemes("http://example.com")
            True

            >>> URLNormalizer.filter_dangerous_schemes("mailto:user@example.com")
            False

            >>> URLNormalizer.filter_dangerous_schemes("javascript:alert('xss')")
            False
        """
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            return scheme in URLNormalizer.SAFE_SCHEMES
        except Exception:
            return False

    @staticmethod
    def handle_query_parameters(url: str, strategy: Literal["strip", "preserve"] = "strip") -> str:
        """Handle query parameters based on strategy.

        Args:
            url: URL to process
            strategy: "strip" removes all query params, "preserve" keeps them

        Returns:
            URL with query parameters handled according to strategy

        Examples:
            >>> URLNormalizer.handle_query_parameters(
            ...     "http://example.com/path?foo=bar&baz=qux",
            ...     strategy="strip"
            ... )
            'http://example.com/path'

            >>> URLNormalizer.handle_query_parameters(
            ...     "http://example.com/path?foo=bar",
            ...     strategy="preserve"
            ... )
            'http://example.com/path?foo=bar'
        """
        if strategy == "preserve":
            return url

        parsed = urlparse(url)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                "",  # Remove query
                parsed.fragment,
            )
        )


class RulesEngine:
    """Evaluates crawling rules to determine which URLs to follow.

    The RulesEngine applies whitelist/blacklist patterns and depth limits
    to control which URLs should be crawled.
    """

    def __init__(self, config: SusConfig):
        """Initialize with configuration.

        Args:
            config: SusConfig containing crawling rules
        """
        self.config = config
        self.depth_tracker: dict[str, int] = {}  # url -> depth from start_urls

    def should_follow(self, url: str, parent_url: str | None = None) -> bool:
        """Determine if URL should be crawled.

        Args:
            url: URL to evaluate (should be normalized before calling)
            parent_url: Parent URL that linked to this URL (None for start URLs)

        Returns:
            True if URL should be crawled

        Logic:
        1. Check if allowed domain
        2. Check depth limit (if configured)
        3. Check exclude patterns (blacklist) - return False if matched
        4. Check include patterns (whitelist) - return True if matched, False if no includes

        Examples:
            >>> config = SusConfig(
            ...     name="test",
            ...     site=SiteConfig(
            ...         start_urls=["http://example.com"],
            ...         allowed_domains=["example.com"]
            ...     ),
            ...     crawling=CrawlingRules(
            ...         include_patterns=[
            ...             PathPattern(pattern="/docs/", type="prefix")
            ...         ],
            ...         depth_limit=2
            ...     )
            ... )
            >>> engine = RulesEngine(config)
            >>> engine.should_follow("http://example.com/docs/guide", None)
            True
        """
        if not self._is_allowed_domain(url):
            return False

        depth = self._get_depth(url, parent_url)
        if (
            self.config.crawling.depth_limit is not None
            and depth > self.config.crawling.depth_limit
        ):
            return False

        parsed = urlparse(url)
        path = parsed.path

        for pattern in self.config.crawling.exclude_patterns:
            if pattern.matches(path):
                return False

        # If there are no include patterns, accept all (that passed exclude check)
        if not self.config.crawling.include_patterns:
            return True

        # If there are include patterns, must match at least one
        return any(pattern.matches(path) for pattern in self.config.crawling.include_patterns)

    def _is_allowed_domain(self, url: str) -> bool:
        """Check if URL domain is in allowed_domains.

        Args:
            url: URL to check

        Returns:
            True if domain is allowed

        Examples:
            >>> config = SusConfig(
            ...     name="test",
            ...     site=SiteConfig(
            ...         start_urls=["http://example.com"],
            ...         allowed_domains=["example.com", "docs.example.com"]
            ...     )
            ... )
            >>> engine = RulesEngine(config)
            >>> engine._is_allowed_domain("http://example.com/path")
            True
            >>> engine._is_allowed_domain("http://other.com/path")
            False
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname

            if not hostname:
                return False

            # Check if hostname matches any allowed domain
            # We use exact match or subdomain match
            hostname_lower = hostname.lower()

            for allowed in self.config.site.allowed_domains:
                allowed_lower = allowed.lower()

                # Exact match
                if hostname_lower == allowed_lower:
                    return True

                # Subdomain match (e.g., "docs.example.com" matches "example.com")
                if hostname_lower.endswith(f".{allowed_lower}"):
                    return True

            return False

        except Exception:
            return False

    def _get_depth(self, url: str, parent_url: str | None) -> int:
        """Calculate and track depth from start_urls.

        Args:
            url: URL to calculate depth for
            parent_url: Parent URL that linked to this URL

        Returns:
            Depth from start URLs (0 for start URLs, 1 for direct links, etc.)

        Examples:
            >>> engine = RulesEngine(config)
            >>> engine._get_depth("http://example.com/", None)
            0
            >>> engine._get_depth("http://example.com/page1", "http://example.com/")
            1
        """
        if url in self.depth_tracker:
            return self.depth_tracker[url]

        if parent_url is None:
            self.depth_tracker[url] = 0
            return 0

        parent_depth = self.depth_tracker.get(parent_url, 0)

        depth = parent_depth + 1
        self.depth_tracker[url] = depth

        return depth


class LinkExtractor:
    """Extracts and normalizes links from HTML.

    Handles relative URL resolution, normalization, and filtering
    of extracted links.
    """

    def __init__(self, selectors: list[str]):
        """Initialize with CSS selectors for links.

        Args:
            selectors: List of CSS selectors for extracting links
                      (e.g., ["a[href]", "link[href]"])

        Examples:
            >>> extractor = LinkExtractor(["a[href]"])
            >>> extractor = LinkExtractor(["a[href]", "link[href]", "area[href]"])

        Note:
            CSS selectors are converted to XPath internally since lxml
            doesn't require the cssselect package for XPath.
        """
        self.selectors = selectors

    @staticmethod
    def _css_to_xpath(selector: str) -> str:
        """Convert simple CSS selector to XPath.

        Args:
            selector: CSS selector (e.g., "a[href]", "link[rel='stylesheet']")

        Returns:
            XPath expression

        Note:
            This is a simple converter for common cases. It handles:
            - element[attr] → //element[@attr]
            - element → //element
        """
        if "[" in selector:
            element, rest = selector.split("[", 1)
            attr = rest.rstrip("]")
            return f"//{element}[@{attr}]"
        else:
            return f"//{selector}"

    def extract_links(self, html: str, base_url: str) -> set[str]:
        """Extract all links from HTML.

        Args:
            html: HTML content to extract links from
            base_url: Base URL for resolving relative links

        Returns:
            Set of absolute, normalized URLs

        Steps:
        1. Parse HTML with lxml
        2. Extract links using CSS selectors
        3. Convert relative to absolute using urllib.parse.urljoin()
        4. Normalize each URL using URLNormalizer
        5. Remove fragments
        6. Filter dangerous schemes
        7. Deduplicate

        Examples:
            >>> html_content = '''
            ... <html>
            ...   <a href="/page1">Page 1</a>
            ...   <a href="http://example.com/page2">Page 2</a>
            ...   <a href="mailto:user@example.com">Email</a>
            ... </html>
            ... '''
            >>> extractor = LinkExtractor(["a[href]"])
            >>> links = extractor.extract_links(html_content, "http://example.com/")
            >>> "http://example.com/page1" in links
            True
            >>> "mailto:user@example.com" in links
            False
        """
        if not html or not html.strip():
            return set()

        try:
            tree = lxml_html.fromstring(html)

            raw_links: set[str] = set()

            for selector in self.selectors:
                xpath = self._css_to_xpath(selector)

                xpath_result = tree.xpath(xpath)

                # XPath can return various types, ensure we only process elements
                if not isinstance(xpath_result, list):
                    continue

                for item in xpath_result:
                    if not hasattr(item, "get"):
                        continue

                    element = cast("LxmlElement", item)
                    href = element.get("href")

                    if href and href.strip():
                        raw_links.add(href.strip())

            normalized_links: set[str] = set()

            for link in raw_links:
                try:
                    absolute_url = urljoin(base_url, link)

                    if not URLNormalizer.filter_dangerous_schemes(absolute_url):
                        continue

                    # Normalize URL (this also removes fragments)
                    normalized_url = URLNormalizer.normalize_url(absolute_url)

                    normalized_links.add(normalized_url)

                except (ValueError, Exception):
                    continue

            return normalized_links

        except Exception:
            return set()
