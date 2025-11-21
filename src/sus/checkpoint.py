"""Checkpoint system for incremental scraping.

This module provides the Checkpoint class for saving/resuming crawl state.
For new code, consider using CheckpointManager with pluggable backends instead.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sus.backends import (
    CheckpointMetadata,
    PageCheckpoint,
    compute_config_hash,
    compute_content_hash,
)

# Re-export from backends for backward compatibility
__all__ = [
    "Checkpoint",
    "CheckpointMetadata",
    "PageCheckpoint",
    "compute_content_hash",
    "compute_config_hash",
    "CHECKPOINT_VERSION",
]

CHECKPOINT_VERSION = 1


class Checkpoint:
    """Simple in-memory checkpoint for crawl state persistence.

    This is the original simple implementation used by tests. For new code,
    consider using CheckpointManager with pluggable backends for better
    scalability and performance.
    """

    def __init__(self, config_name: str, config_hash: str) -> None:
        """Initialize a new checkpoint.

        Args:
            config_name: Name of the configuration
            config_hash: Hash of configuration for validation
        """
        self.version = CHECKPOINT_VERSION
        self.config_name = config_name
        self.config_hash = config_hash
        self.created_at = datetime.now(UTC).isoformat()
        self.last_updated = datetime.now(UTC).isoformat()
        self.pages: dict[str, PageCheckpoint] = {}
        self.queue: list[tuple[str, str | None]] = []
        self.stats: dict[str, Any] = {}

    def add_page(
        self,
        url: str,
        content_hash: str,
        status_code: int,
        file_path: str,
    ) -> None:
        """Add or update a page in the checkpoint.

        Args:
            url: Page URL
            content_hash: SHA-256 hash of content
            status_code: HTTP status code
            file_path: Output file path
        """
        page = PageCheckpoint(
            url=url,
            content_hash=content_hash,
            last_scraped=datetime.now(UTC).isoformat(),
            status_code=status_code,
            file_path=file_path,
        )
        self.pages[url] = page

    async def save(self, path: Path) -> None:
        """Save checkpoint to JSON file.

        Args:
            path: Path to save checkpoint file
        """
        self.last_updated = datetime.now(UTC).isoformat()

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.version,
            "config_name": self.config_name,
            "config_hash": self.config_hash,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "pages": {
                url: {
                    "url": page.url,
                    "content_hash": page.content_hash,
                    "last_scraped": page.last_scraped,
                    "status_code": page.status_code,
                    "file_path": page.file_path,
                }
                for url, page in self.pages.items()
            },
            "queue": self.queue,
            "stats": self.stats,
        }

        # Atomic write: write to temp file, then rename
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.rename(path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    @classmethod
    async def load(cls, path: Path) -> "Checkpoint | None":
        """Load checkpoint from JSON file.

        Args:
            path: Path to checkpoint file

        Returns:
            Checkpoint instance or None if file doesn't exist or is invalid
        """
        if not path.exists():
            return None

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            if data.get("version") != CHECKPOINT_VERSION:
                return None

            checkpoint = cls.__new__(cls)
            checkpoint.version = data["version"]
            checkpoint.config_name = data["config_name"]
            checkpoint.config_hash = data["config_hash"]
            checkpoint.created_at = data["created_at"]
            checkpoint.last_updated = data["last_updated"]
            checkpoint.stats = data.get("stats", {})
            # Convert queue items back to tuples (JSON deserializes as lists)
            checkpoint.queue = [(url, parent_url) for url, parent_url in data.get("queue", [])]

            checkpoint.pages = {}
            for url, page_data in data.get("pages", {}).items():
                page = PageCheckpoint(
                    url=page_data["url"],
                    content_hash=page_data["content_hash"],
                    last_scraped=page_data["last_scraped"],
                    status_code=page_data["status_code"],
                    file_path=page_data["file_path"],
                )
                checkpoint.pages[url] = page

            return checkpoint

        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def get_all_page_urls(self) -> set[str]:
        """Get set of all page URLs in checkpoint.

        Returns:
            Set of page URLs
        """
        return set(self.pages.keys())

    def should_redownload(self, url: str, force_redownload_after_days: int | None = None) -> bool:
        """Check if a URL should be redownloaded.

        Args:
            url: URL to check
            force_redownload_after_days: If set, redownload pages older than N days

        Returns:
            True if page should be redownloaded, False otherwise
        """
        if url not in self.pages:
            return True

        if force_redownload_after_days is None:
            return False

        page = self.pages[url]
        try:
            last_scraped = datetime.fromisoformat(page.last_scraped)
            age = datetime.now(UTC) - last_scraped
            return age > timedelta(days=force_redownload_after_days)
        except (ValueError, TypeError):
            return True
