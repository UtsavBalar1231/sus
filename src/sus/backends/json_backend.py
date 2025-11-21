"""JSON-based checkpoint backend (original implementation).

Loads entire state into memory for fast access. Suitable for <10K pages.
Uses atomic writes (temp file + rename) for crash safety.
"""

import json
import tempfile
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path

import aiofiles

from sus.backends.base import CheckpointMetadata, PageCheckpoint

CHECKPOINT_VERSION = 1


class JSONBackend:
    """JSON file-based checkpoint backend.

    Loads entire state into memory for fast access. All operations
    work with in-memory data structures, with periodic saves to disk.

    Suitable for <10K pages (memory usage: ~5MB per 10K pages).

    File format:
        {
          "version": 1,
          "config_name": "my-docs",
          "config_hash": "sha256...",
          "created_at": "2025-01-01T00:00:00Z",
          "last_updated": "2025-01-01T12:00:00Z",
          "pages": {...},
          "queue": [...],
          "stats": {...}
        }
    """

    def __init__(self, path: Path) -> None:
        """Initialize JSON backend.

        Args:
            path: Path to JSON checkpoint file
        """
        self.path = path
        self._metadata: CheckpointMetadata | None = None
        self._pages: dict[str, PageCheckpoint] = {}
        self._queue: list[tuple[str, str | None]] = []

    async def initialize(self) -> None:
        """Load checkpoint from JSON file if it exists."""
        if not self.path.exists():
            return

        try:
            async with aiofiles.open(self.path, encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

            # Validate version
            if data.get("version") != CHECKPOINT_VERSION:
                return

            # Validate required fields
            required_fields = ["config_name", "config_hash", "created_at", "last_updated"]
            if not all(field in data for field in required_fields):
                return

            self._metadata = CheckpointMetadata(
                version=data["version"],
                config_name=data["config_name"],
                config_hash=data["config_hash"],
                created_at=data["created_at"],
                last_updated=data["last_updated"],
                stats=data.get("stats", {}),
            )

            for url, page_data in data.get("pages", {}).items():
                self._pages[url] = PageCheckpoint(**page_data)

            queue_data = data.get("queue", [])
            self._queue = [(item[0], item[1]) for item in queue_data]

        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
            # Corrupted checkpoint - start fresh
            pass

    async def close(self) -> None:
        """No cleanup needed for JSON backend."""
        pass

    async def load_metadata(self) -> CheckpointMetadata | None:
        """Load checkpoint metadata from memory.

        Returns:
            CheckpointMetadata if loaded, None otherwise
        """
        return self._metadata

    async def save_metadata(self, metadata: CheckpointMetadata) -> None:
        """Save checkpoint metadata and trigger full disk write.

        Args:
            metadata: Metadata to save
        """
        self._metadata = metadata
        await self._save_to_disk()

    async def get_page(self, url: str) -> PageCheckpoint | None:
        """Get page checkpoint from memory.

        Args:
            url: Page URL to lookup

        Returns:
            PageCheckpoint if exists, None otherwise
        """
        return self._pages.get(url)

    async def add_page(self, page: PageCheckpoint) -> None:
        """Add or update page checkpoint in memory.

        Note: Changes are not persisted until save_metadata() is called.

        Args:
            page: Page checkpoint to add
        """
        self._pages[page.url] = page

    async def has_page(self, url: str) -> bool:
        """Check if page exists (O(1) dict lookup).

        Args:
            url: Page URL to check

        Returns:
            True if page exists
        """
        return url in self._pages

    async def get_page_count(self) -> int:
        """Get total number of pages in memory.

        Returns:
            Number of pages stored
        """
        return len(self._pages)

    async def iter_pages(self) -> AsyncIterator[PageCheckpoint]:
        """Iterate over all pages in memory.

        Since all pages are already loaded, this is a simple iteration.

        Yields:
            PageCheckpoint instances
        """
        for page in self._pages.values():
            yield page

    async def get_queue(self) -> list[tuple[str, str | None]]:
        """Get pending URL queue from memory.

        Returns:
            Copy of queue list
        """
        return self._queue.copy()

    async def save_queue(self, queue: list[tuple[str, str | None]]) -> None:
        """Save pending URL queue to memory.

        Note: Changes are not persisted until save_metadata() is called.

        Args:
            queue: Queue list to save
        """
        self._queue = queue

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
        from datetime import UTC, datetime

        page = await self.get_page(url)
        if page is None:
            return True

        if force_redownload_after_days is not None:
            try:
                last_scraped = datetime.fromisoformat(page.last_scraped)
                now = datetime.now(UTC)
                age_days = (now - last_scraped).total_seconds() / 86400

                if age_days > force_redownload_after_days:
                    return True
            except (ValueError, TypeError):
                return True

        return False

    async def commit(self) -> None:
        """No-op for JSON backend (changes saved via save_metadata)."""
        pass

    async def _save_to_disk(self) -> None:
        """Save complete state to JSON file with atomic write.

        Uses temp file + rename pattern to ensure atomicity and prevent
        corruption from crashes during write.
        """
        if self._metadata is None:
            return

        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize state
        data = {
            "version": self._metadata.version,
            "config_name": self._metadata.config_name,
            "config_hash": self._metadata.config_hash,
            "created_at": self._metadata.created_at,
            "last_updated": self._metadata.last_updated,
            "pages": {url: asdict(page) for url, page in self._pages.items()},
            "queue": self._queue,
            "stats": self._metadata.stats,
        }

        # Atomic write: temp file + rename
        # Use same directory as target to ensure atomic rename on same filesystem
        temp_fd, temp_path_str = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=".sus_checkpoint_",
            suffix=".tmp",
        )
        temp_path = Path(temp_path_str)

        try:
            # Write to temp file
            async with aiofiles.open(temp_fd, "w", encoding="utf-8", closefd=True) as f:
                await f.write(json.dumps(data, indent=2))

            # Atomic rename (overwrites target)
            temp_path.replace(self.path)

        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise
