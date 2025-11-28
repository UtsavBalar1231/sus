"""Checkpoint manager for backward compatibility.

High-level interface to checkpoint backends, maintaining the same API
as the original Checkpoint class for easy migration.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sus.backends import (
    CheckpointMetadata,
    PageCheckpoint,
    StateBackend,
    compute_config_hash,
    compute_content_hash,
    create_backend,
)
from sus.config import SusConfig

CHECKPOINT_VERSION = 1


class CheckpointManager:
    """High-level checkpoint manager wrapping backend implementations.

    Provides backward-compatible API with the original Checkpoint class
    while using pluggable backend implementations (JSON or SQLite).
    """

    def __init__(
        self,
        backend: StateBackend,
        config_name: str,
        config_hash: str,
    ) -> None:
        """Initialize checkpoint manager.

        Args:
            backend: StateBackend implementation to use
            config_name: Name of the configuration
            config_hash: Hash of configuration for validation
        """
        self.backend = backend
        self._config_name = config_name
        self._config_hash = config_hash
        self._metadata: CheckpointMetadata | None = None
        self._queue: list[tuple[str, str | None]] = []

    @classmethod
    async def load(cls, path: Path, config: SusConfig) -> "CheckpointManager | None":
        """Load checkpoint from file using appropriate backend.

        Args:
            path: Path to checkpoint file
            config: Current configuration for hash validation

        Returns:
            CheckpointManager if checkpoint exists and is valid, None otherwise
        """
        backend = create_backend(path, backend_type=config.crawling.checkpoint.backend)

        try:
            await backend.initialize()

            metadata = await backend.load_metadata()
            if metadata is None:
                await backend.close()
                return None

            if metadata.version != CHECKPOINT_VERSION:
                await backend.close()
                return None

            manager = cls(
                backend=backend,
                config_name=metadata.config_name,
                config_hash=metadata.config_hash,
            )
            manager._metadata = metadata
            manager._queue = await backend.get_queue()

            return manager

        except Exception:
            await backend.close()
            return None

    @classmethod
    async def create_new(cls, path: Path, config: SusConfig) -> "CheckpointManager":
        """Create a new checkpoint.

        Args:
            path: Path to checkpoint file
            config: Configuration to use

        Returns:
            New CheckpointManager instance
        """
        backend = create_backend(path, backend_type=config.crawling.checkpoint.backend)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=CHECKPOINT_VERSION,
            config_name=config.name,
            config_hash=compute_config_hash(config),
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )

        await backend.save_metadata(metadata)

        manager = cls(
            backend=backend,
            config_name=config.name,
            config_hash=metadata.config_hash,
        )
        manager._metadata = metadata

        return manager

    async def close(self) -> None:
        """Close backend connection."""
        await self.backend.close()

    @property
    def config_name(self) -> str:
        """Get configuration name."""
        return self._config_name

    @property
    def config_hash(self) -> str:
        """Get configuration hash."""
        return self._config_hash

    @property
    def queue(self) -> list[tuple[str, str | None]]:
        """Get current queue."""
        return self._queue

    @queue.setter
    def queue(self, value: list[tuple[str, str | None]]) -> None:
        """Set current queue."""
        self._queue = value

    async def add_page(
        self,
        url: str,
        content_hash: str,
        status_code: int,
        file_path: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        """Add or update page in checkpoint.

        Args:
            url: Page URL
            content_hash: SHA-256 hash of page content
            status_code: HTTP status code
            file_path: Output file path
            etag: ETag header from response (for conditional requests)
            last_modified: Last-Modified header from response (for conditional requests)
        """
        page = PageCheckpoint(
            url=url,
            content_hash=content_hash,
            last_scraped=datetime.now(UTC).isoformat(),
            status_code=status_code,
            file_path=file_path,
            etag=etag,
            last_modified=last_modified,
        )
        await self.backend.add_page(page)

    async def get_conditional_headers(self, url: str) -> dict[str, str]:
        """Get conditional request headers for a URL.

        Returns If-None-Match and/or If-Modified-Since headers if the page
        has been previously crawled with ETag/Last-Modified response headers.

        Args:
            url: URL to get conditional headers for

        Returns:
            Dict of headers to add to the request (may be empty)
        """
        page = await self.backend.get_page(url)
        if page is None:
            return {}

        headers: dict[str, str] = {}
        if page.etag:
            headers["If-None-Match"] = page.etag
        if page.last_modified:
            headers["If-Modified-Since"] = page.last_modified

        return headers

    async def has_page(self, url: str) -> bool:
        """Check if page exists in checkpoint.

        Args:
            url: Page URL to check

        Returns:
            True if page exists
        """
        return await self.backend.has_page(url)

    async def should_redownload(
        self, url: str, force_redownload_after_days: int | None = None
    ) -> bool:
        """Determine if URL should be redownloaded.

        Args:
            url: URL to check
            force_redownload_after_days: Redownload if older than N days

        Returns:
            True if page should be redownloaded
        """
        return await self.backend.should_redownload(url, force_redownload_after_days)

    async def get_page_count(self) -> int:
        """Get total number of pages in checkpoint.

        Returns:
            Number of pages stored
        """
        return await self.backend.get_page_count()

    async def get_all_page_urls(self) -> set[str]:
        """Get set of all page URLs in checkpoint.

        Returns:
            Set of page URLs
        """
        urls = set()
        async_iter = self.backend.iter_pages()
        async for page in async_iter:
            urls.add(page.url)
        return urls

    async def save(self, path: Path) -> None:
        """Save checkpoint to disk.

        Args:
            path: Path to save checkpoint to
        """
        if self._metadata is None:
            raise RuntimeError("Metadata not initialized")

        self._metadata.last_updated = datetime.now(UTC).isoformat()

        await self.backend.save_metadata(self._metadata)
        await self.backend.save_queue(self._queue)

        # Commit changes (for backends that support batching)
        await self.backend.commit()

    def update_stats(self, stats: dict[str, Any]) -> None:
        """Update checkpoint statistics.

        Args:
            stats: Statistics dict to store
        """
        if self._metadata:
            self._metadata.stats = stats


# Re-export for backward compatibility
__all__ = [
    "CheckpointManager",
    "compute_content_hash",
    "compute_config_hash",
]
