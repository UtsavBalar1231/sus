"""Link validation plugin.

Validates internal and external links in markdown content, marking broken links
with HTML comments for easy identification.
"""

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from sus.plugins import Plugin, PluginHook


class LinkValidatorPlugin(Plugin):
    """Link validation plugin.

    Validates both internal and external links:
    - Internal: Checks if file exists in output directory
    - External: Performs HTTP HEAD request to verify link

    Broken links are marked with HTML comments: <!-- BROKEN LINK: ... -->

    Settings:
        timeout: HTTP request timeout in seconds (default: 5.0)
        max_concurrent: Maximum concurrent external link checks (default: 10)
        cache_results: Cache validation results to avoid duplicate checks (default: True)
        ignore_patterns: List of regex patterns for links to skip (default: [])
        check_internal: Validate internal links (default: True)
        check_external: Validate external links (default: True)
        base_dir: Base output directory for internal link validation
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        """Initialize link validator plugin.

        Args:
            settings: Plugin settings
        """
        super().__init__(settings)

        self.timeout = self.settings.get("timeout", 5.0)
        self.max_concurrent = self.settings.get("max_concurrent", 10)
        self.cache_results = self.settings.get("cache_results", True)
        self.ignore_patterns = [
            re.compile(pattern) for pattern in self.settings.get("ignore_patterns", [])
        ]
        self.check_internal = self.settings.get("check_internal", True)
        self.check_external = self.settings.get("check_external", True)
        self.base_dir = self.settings.get("base_dir", "output")

        self._cache: dict[str, bool] = {} if self.cache_results else {}
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "link_validator"

    @property
    def hooks(self) -> list[PluginHook]:
        """Subscribe to POST_CONVERT hook."""
        return [PluginHook.POST_CONVERT]

    def on_post_convert(self, url: str, markdown: str) -> str:
        """Validate links in markdown content.

        Args:
            url: Page URL (for resolving relative links)
            markdown: Markdown content

        Returns:
            Markdown with broken links marked
        """
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def validate_link(match: re.Match[str]) -> str:
            """Validate a single link.

            Args:
                match: Regex match for markdown link

            Returns:
                Original link or link with broken marker
            """
            text = match.group(1)
            link = match.group(2)

            if self._should_ignore_link(link):
                return match.group(0)

            is_valid = self._validate_link_sync(url, link)

            if is_valid:
                return match.group(0)
            else:
                return f"[{text}]({link})<!-- BROKEN LINK: {link} -->"

        return re.sub(link_pattern, validate_link, markdown)

    def _should_ignore_link(self, link: str) -> bool:
        """Check if link should be ignored.

        Args:
            link: Link URL

        Returns:
            True if link matches ignore patterns
        """
        return any(pattern.search(link) for pattern in self.ignore_patterns)

    def _validate_link_sync(self, base_url: str, link: str) -> bool:
        """Synchronously validate a link (wrapper for async validation).

        Args:
            base_url: Base URL for resolving relative links
            link: Link to validate

        Returns:
            True if link is valid
        """
        if link.startswith("#"):
            return True

        if self.cache_results and link in self._cache:
            return self._cache[link]

        try:
            loop = asyncio.get_running_loop()
            result: bool = loop.run_until_complete(self._validate_link_async(base_url, link))
        except RuntimeError:
            result = asyncio.run(self._validate_link_async(base_url, link))

        if self.cache_results:
            self._cache[link] = result

        return result

    async def _validate_link_async(self, base_url: str, link: str) -> bool:
        """Asynchronously validate a link.

        Args:
            base_url: Base URL for resolving relative links
            link: Link to validate

        Returns:
            True if link is valid
        """
        absolute_url = urljoin(base_url, link)
        parsed = urlparse(absolute_url)

        if parsed.scheme in ("http", "https"):
            if not self.check_external:
                return True
            return await self._check_external_link(absolute_url)
        else:
            if not self.check_internal:
                return True
            return self._check_internal_link(link)

    async def _check_external_link(self, url: str) -> bool:
        """Check if external link is valid.

        Args:
            url: Absolute URL to check

        Returns:
            True if link returns successful status
        """
        async with self._semaphore:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.head(
                        url,
                        timeout=self.timeout,
                        follow_redirects=True,
                    )
                    is_valid: bool = response.status_code < 400
                    return is_valid
            except Exception:
                return False

    def _check_internal_link(self, link: str) -> bool:
        """Check if internal link file exists.

        Args:
            link: Relative link path

        Returns:
            True if file exists
        """
        if link.startswith("/"):
            link = link[1:]

        if "#" in link:
            link = link.split("#")[0]

        if not link:
            return True

        base_path = Path(self.base_dir)
        file_path = base_path / link

        if file_path.suffix == "":
            if (file_path / "index.md").exists():
                return True
            if file_path.with_suffix(".md").exists():
                return True

        return file_path.exists()


__all__ = ["LinkValidatorPlugin"]
