"""Abstract base class for checkpoint state backends.

Defines the protocol that all checkpoint backends must implement for
storing and retrieving crawl state (metadata, pages, queue).
"""

from collections.abc import AsyncIterator as AsyncIteratorABC
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class CheckpointMetadata:
    """Checkpoint metadata stored separately from pages.

    Contains version info, configuration hash, timestamps, and statistics.
    """

    version: int
    config_name: str
    config_hash: str
    created_at: str  # ISO 8601 timestamp
    last_updated: str  # ISO 8601 timestamp
    stats: dict[str, Any]


@dataclass
class PageCheckpoint:
    """Checkpoint data for a single scraped page.

    Tracks content hash and metadata to detect changes on resume.
    Includes ETag/Last-Modified for conditional requests (304 Not Modified).
    """

    url: str
    content_hash: str
    last_scraped: str  # ISO 8601 timestamp
    status_code: int
    file_path: str
    etag: str | None = None  # ETag header for conditional requests
    last_modified: str | None = None  # Last-Modified header for conditional requests


class StateBackend(Protocol):
    """Abstract interface for checkpoint state persistence.

    All backends must implement this protocol to support:
    - Metadata storage (version, config, timestamps, stats)
    - Page state storage (URL -> PageCheckpoint mapping)
    - Queue storage (pending URLs)
    - Efficient queries for skip logic

    Implementations handle their own file formats and performance
    optimizations while providing a consistent async interface.
    """

    async def initialize(self) -> None:
        """Initialize backend (create schema, open connections, etc).

        Called once at the start of a crawl before any other operations.
        Must be idempotent (safe to call multiple times).
        """
        ...

    async def close(self) -> None:
        """Close backend connections and cleanup resources.

        Called at the end of a crawl or on error. Must be idempotent.
        """
        ...

    # === Metadata Operations ===

    async def load_metadata(self) -> CheckpointMetadata | None:
        """Load checkpoint metadata.

        Returns:
            CheckpointMetadata if checkpoint exists and is valid, None otherwise
        """
        ...

    async def save_metadata(self, metadata: CheckpointMetadata) -> None:
        """Save checkpoint metadata.

        Args:
            metadata: Metadata to persist
        """
        ...

    # === Page Operations ===

    async def get_page(self, url: str) -> PageCheckpoint | None:
        """Get page checkpoint by URL.

        Args:
            url: Page URL to lookup

        Returns:
            PageCheckpoint if page exists in checkpoint, None otherwise
        """
        ...

    async def add_page(self, page: PageCheckpoint) -> None:
        """Add or update page checkpoint.

        Args:
            page: Page checkpoint to persist
        """
        ...

    async def has_page(self, url: str) -> bool:
        """Check if page exists in checkpoint (fast path).

        May be optimized to avoid full page load.

        Args:
            url: Page URL to check

        Returns:
            True if page exists, False otherwise
        """
        ...

    async def get_page_count(self) -> int:
        """Get total number of pages in checkpoint.

        Returns:
            Number of pages stored
        """
        ...

    def iter_pages(self) -> AsyncIteratorABC[PageCheckpoint]:
        """Iterate over all pages (async generator).

        For large checkpoints, implementations should stream pages
        rather than loading all into memory.

        Yields:
            PageCheckpoint instances one at a time
        """
        ...

    # === Queue Operations ===

    async def get_queue(self) -> list[tuple[str, str | None]]:
        """Get pending URL queue.

        Returns:
            List of (url, parent_url) tuples in queue order
        """
        ...

    async def save_queue(self, queue: list[tuple[str, str | None]]) -> None:
        """Save pending URL queue.

        Args:
            queue: List of (url, parent_url) tuples to persist
        """
        ...

    # === Skip Logic ===

    async def should_redownload(
        self, url: str, force_redownload_after_days: int | None = None
    ) -> bool:
        """Determine if URL should be redownloaded.

        Checks if page exists and respects age-based refresh policy.

        Args:
            url: URL to check
            force_redownload_after_days: Redownload if older than N days (None = never)

        Returns:
            True if page should be redownloaded, False to skip
        """
        ...

    async def commit(self) -> None:
        """Commit any pending changes (for backends that support batching).

        Optional method for backends that batch operations for performance.
        Backends without batching can implement this as a no-op.
        """
        ...
