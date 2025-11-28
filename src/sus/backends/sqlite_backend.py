"""SQLite-based checkpoint backend for large sites (>10K pages).

Uses database for efficient storage and querying with lazy loading.
Only loads metadata on startup, queries pages on-demand.
"""

import json
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite

from sus.backends.base import CheckpointMetadata, PageCheckpoint

CHECKPOINT_VERSION = 1


class SQLiteBackend:
    """SQLite-based checkpoint backend.

    Uses database for efficient storage and indexed queries.
    Suitable for >10K pages (memory usage: constant ~10-20MB).

    Schema:
        metadata: Single row with version, config, timestamps, stats (JSON)
        pages: url (PK), content_hash, last_scraped, status_code, file_path
        queue: position (PK), url, parent_url

    Performance optimizations:
        - WAL mode for better concurrency
        - Index on pages.url (primary key)
        - Index on pages.last_scraped for age queries
        - Batch inserts with transactions
    """

    def __init__(self, path: Path) -> None:
        """Initialize SQLite backend.

        Args:
            path: Path to SQLite database file
        """
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open connection and create schema if needed."""
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = sqlite3.Row

        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._conn.execute("PRAGMA cache_size = -10000")  # 10MB cache
        await self._conn.execute("PRAGMA foreign_keys = ON")

        await self._create_schema()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _create_schema(self) -> None:
        """Create database schema if not exists."""
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                config_name TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                stats TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                last_scraped TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                etag TEXT,
                last_modified TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_pages_last_scraped
                ON pages(last_scraped);

            CREATE TABLE IF NOT EXISTS queue (
                position INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                parent_url TEXT
            );
        """
        )

        # Migrate existing tables: add etag/last_modified columns if missing
        await self._migrate_schema()

        await self._conn.commit()

    async def _migrate_schema(self) -> None:
        """Add new columns to existing tables (schema migration)."""
        if self._conn is None:
            return

        # Check if etag column exists
        cursor = await self._conn.execute("PRAGMA table_info(pages)")
        columns = {row[1] for row in await cursor.fetchall()}

        if "etag" not in columns:
            await self._conn.execute("ALTER TABLE pages ADD COLUMN etag TEXT")

        if "last_modified" not in columns:
            await self._conn.execute("ALTER TABLE pages ADD COLUMN last_modified TEXT")

    async def load_metadata(self) -> CheckpointMetadata | None:
        """Load checkpoint metadata from database.

        Returns:
            CheckpointMetadata if checkpoint exists, None otherwise
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        cursor = await self._conn.execute(
            """
            SELECT version, config_name, config_hash, created_at, last_updated, stats
            FROM metadata
            WHERE id = 1
            """
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        return CheckpointMetadata(
            version=row["version"],
            config_name=row["config_name"],
            config_hash=row["config_hash"],
            created_at=row["created_at"],
            last_updated=row["last_updated"],
            stats=json.loads(row["stats"]),
        )

    async def save_metadata(self, metadata: CheckpointMetadata) -> None:
        """Save checkpoint metadata to database.

        Args:
            metadata: Metadata to persist
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO metadata
                (id, version, config_name, config_hash, created_at, last_updated, stats)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata.version,
                metadata.config_name,
                metadata.config_hash,
                metadata.created_at,
                metadata.last_updated,
                json.dumps(metadata.stats),
            ),
        )
        await self._conn.commit()

    async def get_page(self, url: str) -> PageCheckpoint | None:
        """Get page checkpoint by URL (indexed lookup).

        Args:
            url: Page URL to lookup

        Returns:
            PageCheckpoint if exists, None otherwise
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        cursor = await self._conn.execute(
            """
            SELECT url, content_hash, last_scraped, status_code, file_path, etag, last_modified
            FROM pages
            WHERE url = ?
            """,
            (url,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        return PageCheckpoint(
            url=row["url"],
            content_hash=row["content_hash"],
            last_scraped=row["last_scraped"],
            status_code=row["status_code"],
            file_path=row["file_path"],
            etag=row["etag"],
            last_modified=row["last_modified"],
        )

    async def add_page(self, page: PageCheckpoint) -> None:
        """Add or update page checkpoint in database.

        Note: Changes are buffered until commit() is called for performance.

        Args:
            page: Page checkpoint to add
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO pages
                (url, content_hash, last_scraped, status_code, file_path, etag, last_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page.url,
                page.content_hash,
                page.last_scraped,
                page.status_code,
                page.file_path,
                page.etag,
                page.last_modified,
            ),
        )
        # Don't commit here - batch commits for performance

    async def has_page(self, url: str) -> bool:
        """Check if page exists (fast indexed lookup).

        Args:
            url: Page URL to check

        Returns:
            True if page exists
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        cursor = await self._conn.execute(
            "SELECT 1 FROM pages WHERE url = ? LIMIT 1",
            (url,),
        )
        row = await cursor.fetchone()
        return row is not None

    async def get_page_count(self) -> int:
        """Get total number of pages in database.

        Returns:
            Number of pages stored
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        cursor = await self._conn.execute("SELECT COUNT(*) FROM pages")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def iter_pages(self) -> AsyncIterator[PageCheckpoint]:
        """Iterate over all pages (streaming, batched reads).

        Fetches pages in batches of 1000 to avoid loading all into memory.

        Yields:
            PageCheckpoint instances one at a time
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        cursor = await self._conn.execute(
            """
            SELECT url, content_hash, last_scraped, status_code, file_path, etag, last_modified
            FROM pages
            ORDER BY url
            """
        )

        while True:
            rows = await cursor.fetchmany(1000)
            if not rows:
                break

            for row in rows:
                yield PageCheckpoint(
                    url=row["url"],
                    content_hash=row["content_hash"],
                    last_scraped=row["last_scraped"],
                    status_code=row["status_code"],
                    file_path=row["file_path"],
                    etag=row["etag"],
                    last_modified=row["last_modified"],
                )

    async def get_queue(self) -> list[tuple[str, str | None]]:
        """Get pending URL queue from database.

        Returns:
            List of (url, parent_url) tuples in queue order
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        cursor = await self._conn.execute("SELECT url, parent_url FROM queue ORDER BY position")
        rows = await cursor.fetchall()
        return [(row["url"], row["parent_url"]) for row in rows]

    async def save_queue(self, queue: list[tuple[str, str | None]]) -> None:
        """Save pending URL queue to database.

        Replaces existing queue completely. Uses explicit transaction to ensure
        atomicity - either all changes apply or none do (prevents data loss
        if crash occurs between DELETE and INSERT).

        Args:
            queue: List of (url, parent_url) tuples to persist
        """
        if self._conn is None:
            raise RuntimeError("Backend not initialized")

        # Use explicit transaction for atomicity (data loss prevention)
        # BEGIN IMMEDIATE acquires write lock immediately, preventing other writers
        await self._conn.execute("BEGIN IMMEDIATE")
        try:
            await self._conn.execute("DELETE FROM queue")

            if queue:
                await self._conn.executemany(
                    "INSERT INTO queue (position, url, parent_url) VALUES (?, ?, ?)",
                    [(i, url, parent_url) for i, (url, parent_url) in enumerate(queue)],
                )

            await self._conn.commit()
        except Exception:
            # Rollback on any error to maintain consistency
            await self._conn.rollback()
            raise

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
        """Explicitly commit transaction (for batch operations).

        Should be called periodically during crawls to persist accumulated
        page additions without committing after every single page.
        """
        if self._conn:
            await self._conn.commit()
