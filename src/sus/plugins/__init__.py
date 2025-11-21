"""Plugin system for SUS scraper.

Extensible hook-based architecture allowing custom processing at various lifecycle points.
Plugins can modify content, validate links, optimize assets, and more.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class PluginHook(str, Enum):
    """Lifecycle hooks where plugins can execute."""

    PRE_CRAWL = "pre_crawl"
    POST_FETCH = "post_fetch"
    POST_CONVERT = "post_convert"
    POST_SAVE = "post_save"
    POST_CRAWL = "post_crawl"


class Plugin(ABC):
    """Base class for all SUS plugins.

    Plugins must implement the name and hooks properties, and can optionally
    implement hook methods corresponding to their declared hooks.

    Hook methods:
    - on_pre_crawl(config): Called before crawling starts
    - on_post_fetch(url, html, status_code): Called after fetching each page
    - on_post_convert(url, markdown): Called after converting HTML to Markdown (can modify)
    - on_post_save(file_path, content_type): Called after saving a file
    - on_post_crawl(stats): Called after crawling completes

    Only POST_CONVERT returns modified content; others are notification-only.
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        """Initialize plugin with settings.

        Args:
            settings: Plugin-specific configuration from config.plugins.plugin_settings
        """
        self.settings = settings or {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier (must be unique)."""
        ...

    @property
    @abstractmethod
    def hooks(self) -> list[PluginHook]:
        """Hooks this plugin subscribes to."""
        ...

    def on_pre_crawl(self, config: Any) -> None:
        """Called before crawling starts (optional override).

        Args:
            config: SusConfig instance
        """
        return

    def on_post_fetch(self, url: str, html: str, status_code: int) -> None:
        """Called after fetching each page (optional override).

        Args:
            url: Page URL
            html: Raw HTML content
            status_code: HTTP status code
        """
        return

    def on_post_convert(self, url: str, markdown: str) -> str:
        """Called after converting HTML to Markdown.

        This is the only hook that can modify content.

        Args:
            url: Page URL
            markdown: Converted Markdown content

        Returns:
            Modified Markdown content
        """
        return markdown

    def on_post_save(self, file_path: str, content_type: str) -> None:
        """Called after saving a file (optional override).

        Args:
            file_path: Path to saved file
            content_type: Type of content ("markdown" or "asset")
        """
        return

    def on_post_crawl(self, stats: dict[str, Any]) -> None:
        """Called after crawling completes (optional override).

        Args:
            stats: Scraping statistics dictionary
        """
        return


__all__ = ["Plugin", "PluginHook"]
