"""Sitemap.xml parsing with auto-discovery and comprehensive error handling.

Parses sitemap.xml files (regular and index sitemaps) with support for:
- Auto-discovery from robots.txt and /sitemap.xml
- Sitemap indexes with recursive parsing
- Compressed sitemaps (.xml.gz)
- Priority-based sorting
- Circular reference detection
- Both namespaced and non-namespaced XML
"""

import gzip
import logging
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

import httpx
from lxml import etree

from sus.exceptions import SitemapError

logger = logging.getLogger(__name__)

# Sitemap XML namespace
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAP_NS_MAP = {"sm": SITEMAP_NS}


@dataclass
class SitemapEntry:
    """Single entry from a sitemap.

    Represents a URL entry with optional metadata fields.
    """

    loc: str
    lastmod: datetime | None = None
    changefreq: (
        Literal["always", "hourly", "daily", "weekly", "monthly", "yearly", "never"] | None
    ) = None
    priority: float | None = None


class SitemapParser:
    """Parser for sitemap.xml files with auto-discovery and recursive parsing.

    Handles both regular sitemaps and sitemap indexes, with support for
    compressed files (.xml.gz) and circular reference detection.

    Example:
        >>> parser = SitemapParser(client)
        >>> sitemaps = await parser.discover_sitemaps("https://example.com")
        >>> entries = await parser.parse_sitemap(sitemaps[0])
    """

    def __init__(self, client: httpx.AsyncClient, strict: bool = False) -> None:
        """Initialize sitemap parser.

        Args:
            client: HTTP client for fetching sitemaps
            strict: If True, raise errors on malformed sitemaps; if False, skip invalid entries
        """
        self.client = client
        self.strict = strict
        self._visited_sitemaps: set[str] = set()  # Track visited URLs for circular detection

    async def discover_sitemaps(self, base_url: str) -> list[str]:
        """Auto-discover sitemap URLs from robots.txt and /sitemap.xml.

        Checks:
        1. robots.txt for Sitemap: directives
        2. /sitemap.xml at site root

        Args:
            base_url: Base URL of the site (e.g., "https://example.com")

        Returns:
            List of discovered sitemap URLs (may be empty)
        """
        discovered: list[str] = []
        parsed = urllib.parse.urlparse(base_url)
        site_root = f"{parsed.scheme}://{parsed.netloc}"

        robots_url = f"{site_root}/robots.txt"
        try:
            response = await self.client.get(robots_url, timeout=10.0)
            if response.status_code == 200:
                for line in response.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        discovered.append(sitemap_url)
                        logger.debug(f"Found sitemap in robots.txt: {sitemap_url}")
        except Exception as e:
            logger.debug(f"Failed to fetch robots.txt from {robots_url}: {e}")

        sitemap_url = f"{site_root}/sitemap.xml"
        try:
            response = await self.client.head(sitemap_url, timeout=10.0)
            if response.status_code == 200 and sitemap_url not in discovered:
                discovered.append(sitemap_url)
                logger.debug(f"Found sitemap at {sitemap_url}")
        except Exception as e:
            logger.debug(f"No sitemap at {sitemap_url}: {e}")

        return discovered

    async def parse_sitemap(self, sitemap_url: str) -> list[SitemapEntry]:
        """Parse a sitemap (regular or index) and return all entries.

        Automatically handles:
        - Sitemap indexes (recursively parses child sitemaps)
        - Compressed sitemaps (.xml.gz)
        - Namespaced and non-namespaced XML
        - Circular references (detected and prevented)

        Args:
            sitemap_url: URL of the sitemap to parse

        Returns:
            List of sitemap entries (may be empty)

        Raises:
            SitemapError: If strict=True and sitemap is malformed or unreachable
        """
        if sitemap_url in self._visited_sitemaps:
            logger.warning(f"Circular reference detected: {sitemap_url}")
            return []

        self._visited_sitemaps.add(sitemap_url)

        try:
            response = await self.client.get(sitemap_url, timeout=30.0)
            response.raise_for_status()

            content = self._decompress_if_needed(response.content, sitemap_url)

            root = etree.fromstring(content)

            # Check for sitemapindex tag (with or without namespace)
            is_index = root.tag == f"{{{SITEMAP_NS}}}sitemapindex" or root.tag == "sitemapindex"

            if is_index:
                return await self._parse_sitemap_index(root)
            else:
                return self._parse_regular_sitemap(root)

        except httpx.HTTPError as e:
            msg = f"Failed to fetch sitemap {sitemap_url}: {e}"
            if self.strict:
                raise SitemapError(msg) from e
            logger.warning(msg)
            return []
        except etree.XMLSyntaxError as e:
            msg = f"Invalid XML in sitemap {sitemap_url}: {e}"
            if self.strict:
                raise SitemapError(msg) from e
            logger.warning(msg)
            return []
        except Exception as e:
            msg = f"Error parsing sitemap {sitemap_url}: {e}"
            if self.strict:
                raise SitemapError(msg) from e
            logger.warning(msg)
            return []

    async def _parse_sitemap_index(self, root: etree._Element) -> list[SitemapEntry]:
        """Parse a sitemap index and recursively fetch child sitemaps.

        Args:
            root: XML root element of sitemap index

        Returns:
            Combined list of entries from all child sitemaps
        """
        entries: list[SitemapEntry] = []

        sitemap_elements = root.findall(f".//{{{SITEMAP_NS}}}sitemap")
        if not sitemap_elements:
            sitemap_elements = root.findall(".//sitemap")

        for sitemap_elem in sitemap_elements:
            loc_elem = sitemap_elem.find(f"{{{SITEMAP_NS}}}loc")
            if loc_elem is None:
                loc_elem = sitemap_elem.find("loc")

            if loc_elem is not None and loc_elem.text:
                child_url = loc_elem.text.strip()
                child_entries = await self.parse_sitemap(child_url)
                entries.extend(child_entries)

        return entries

    def _parse_regular_sitemap(self, root: etree._Element) -> list[SitemapEntry]:
        """Parse a regular sitemap and extract URL entries.

        Args:
            root: XML root element of regular sitemap

        Returns:
            List of sitemap entries
        """
        entries: list[SitemapEntry] = []

        url_elements = root.findall(f".//{{{SITEMAP_NS}}}url")
        if not url_elements:
            url_elements = root.findall(".//url")

        for url_elem in url_elements:
            try:
                loc_elem = url_elem.find(f"{{{SITEMAP_NS}}}loc")
                if loc_elem is None:
                    loc_elem = url_elem.find("loc")

                if loc_elem is None or not loc_elem.text:
                    if self.strict:
                        raise SitemapError("Missing <loc> element in sitemap entry")
                    continue

                loc = loc_elem.text.strip()

                lastmod = None
                lastmod_elem = url_elem.find(f"{{{SITEMAP_NS}}}lastmod")
                if lastmod_elem is None:
                    lastmod_elem = url_elem.find("lastmod")
                if lastmod_elem is not None and lastmod_elem.text:
                    try:
                        lastmod = datetime.fromisoformat(
                            lastmod_elem.text.strip().replace("Z", "+00:00")
                        )
                    except ValueError:
                        if self.strict:
                            raise
                        logger.debug(f"Invalid lastmod format: {lastmod_elem.text}")

                changefreq = None
                changefreq_elem = url_elem.find(f"{{{SITEMAP_NS}}}changefreq")
                if changefreq_elem is None:
                    changefreq_elem = url_elem.find("changefreq")
                if changefreq_elem is not None and changefreq_elem.text:
                    freq_text = changefreq_elem.text.strip().lower()
                    valid_freqs: tuple[str, ...] = (
                        "always",
                        "hourly",
                        "daily",
                        "weekly",
                        "monthly",
                        "yearly",
                        "never",
                    )
                    if freq_text in valid_freqs:
                        # Type assertion: freq_text is validated against valid_freqs tuple
                        changefreq = cast(
                            "Literal['always', 'hourly', 'daily', 'weekly', 'monthly', 'yearly', 'never']",  # noqa: E501
                            freq_text,
                        )
                    elif self.strict:
                        raise SitemapError(f"Invalid changefreq: {freq_text}")

                priority = None
                priority_elem = url_elem.find(f"{{{SITEMAP_NS}}}priority")
                if priority_elem is None:
                    priority_elem = url_elem.find("priority")
                if priority_elem is not None and priority_elem.text:
                    try:
                        priority = float(priority_elem.text.strip())
                        if not (0.0 <= priority <= 1.0):
                            if self.strict:
                                raise SitemapError(f"Priority must be 0.0-1.0, got {priority}")
                            priority = None
                    except ValueError:
                        if self.strict:
                            raise
                        logger.debug(f"Invalid priority format: {priority_elem.text}")

                entry = SitemapEntry(
                    loc=loc,
                    lastmod=lastmod,
                    changefreq=changefreq,
                    priority=priority,
                )
                entries.append(entry)

            except SitemapError:
                raise
            except Exception as e:
                if self.strict:
                    raise SitemapError(f"Error parsing sitemap entry: {e}") from e
                logger.debug(f"Skipping invalid sitemap entry: {e}")
                continue

        return entries

    def _decompress_if_needed(self, content: bytes, url: str) -> bytes:
        """Decompress content if URL ends with .gz.

        Args:
            content: Raw response content
            url: Sitemap URL (used to detect .gz extension)

        Returns:
            Decompressed content (or original if not compressed)
        """
        if url.endswith(".gz"):
            try:
                return gzip.decompress(content)
            except Exception as e:
                msg = f"Failed to decompress gzipped sitemap {url}: {e}"
                if self.strict:
                    raise SitemapError(msg) from e
                logger.warning(msg)
                return content
        return content
