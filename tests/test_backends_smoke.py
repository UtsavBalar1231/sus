"""Smoke tests for backend implementations.

Quick tests to verify JSONBackend and SQLiteBackend basic functionality.
"""

import tempfile
from pathlib import Path

import pytest

from sus.backends import CheckpointMetadata, JSONBackend, PageCheckpoint, SQLiteBackend


@pytest.mark.asyncio
async def test_json_backend_basic_operations() -> None:
    """Test JSONBackend create, save, and load cycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"
        backend = JSONBackend(path)

        # Initialize
        await backend.initialize()

        # Save metadata
        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at="2025-01-01T00:00:00Z",
            last_updated="2025-01-01T00:00:00Z",
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add a page
        page = PageCheckpoint(
            url="https://example.com",
            content_hash="def456",
            last_scraped="2025-01-01T00:00:00Z",
            status_code=200,
            file_path="/output/page.md",
        )
        await backend.add_page(page)

        # Save queue
        await backend.save_queue([("https://example.com/page2", "https://example.com")])

        # For JSONBackend, need to trigger save via save_metadata (it saves everything)
        metadata.last_updated = "2025-01-01T01:00:00Z"
        await backend.save_metadata(metadata)

        await backend.commit()

        # Close and reopen
        await backend.close()

        backend2 = JSONBackend(path)
        await backend2.initialize()

        # Verify metadata
        loaded_metadata = await backend2.load_metadata()
        assert loaded_metadata is not None
        assert loaded_metadata.config_name == "test"

        loaded_page = await backend2.get_page("https://example.com")
        assert loaded_page is not None
        assert loaded_page.content_hash == "def456"

        # Verify queue
        queue = await backend2.get_queue()
        assert len(queue) == 1
        assert queue[0][0] == "https://example.com/page2"

        await backend2.close()


@pytest.mark.asyncio
async def test_sqlite_backend_basic_operations() -> None:
    """Test SQLiteBackend create, save, and load cycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        backend = SQLiteBackend(path)

        # Initialize
        await backend.initialize()

        # Save metadata
        metadata = CheckpointMetadata(
            version=1,
            config_name="test-sqlite",
            config_hash="xyz789",
            created_at="2025-01-01T00:00:00Z",
            last_updated="2025-01-01T00:00:00Z",
            stats={"pages_crawled": 0},
        )
        await backend.save_metadata(metadata)

        # Add multiple pages
        for i in range(100):
            page = PageCheckpoint(
                url=f"https://example.com/page{i}",
                content_hash=f"hash{i}",
                last_scraped="2025-01-01T00:00:00Z",
                status_code=200,
                file_path=f"/output/page{i}.md",
            )
            await backend.add_page(page)

        await backend.commit()

        # Verify page count
        count = await backend.get_page_count()
        assert count == 100

        # Verify specific page
        page50 = await backend.get_page("https://example.com/page50")
        assert page50 is not None
        assert page50.content_hash == "hash50"

        # Test iteration
        urls = set()
        async for page in backend.iter_pages():
            urls.add(page.url)
        assert len(urls) == 100

        # Save queue
        await backend.save_queue([("https://example.com/next", None)])

        # Close and reopen
        await backend.close()

        backend2 = SQLiteBackend(path)
        await backend2.initialize()

        # Verify metadata persisted
        loaded_metadata = await backend2.load_metadata()
        assert loaded_metadata is not None
        assert loaded_metadata.config_name == "test-sqlite"
        assert loaded_metadata.stats["pages_crawled"] == 0

        # Verify pages persisted
        assert await backend2.get_page_count() == 100
        assert await backend2.has_page("https://example.com/page99")

        # Verify queue persisted
        queue = await backend2.get_queue()
        assert len(queue) == 1

        await backend2.close()


@pytest.mark.asyncio
async def test_backends_should_redownload() -> None:
    """Test should_redownload logic in both backends."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test with JSONBackend
        json_path = Path(tmpdir) / "test.json"
        json_backend = JSONBackend(json_path)
        await json_backend.initialize()

        # URL not in checkpoint - should download
        assert await json_backend.should_redownload("https://example.com") is True

        page = PageCheckpoint(
            url="https://example.com",
            content_hash="abc",
            last_scraped="2020-01-01T00:00:00Z",  # Old date
            status_code=200,
            file_path="/page.md",
        )
        await json_backend.add_page(page)

        # Fresh page - should not download
        assert await json_backend.should_redownload("https://example.com", None) is False

        # Old page with force_redownload_after_days - should download
        assert await json_backend.should_redownload("https://example.com", 7) is True

        await json_backend.close()

        # Test with SQLiteBackend
        sqlite_path = Path(tmpdir) / "test.db"
        sqlite_backend = SQLiteBackend(sqlite_path)
        await sqlite_backend.initialize()

        # Same tests for SQLite
        assert await sqlite_backend.should_redownload("https://example.com") is True

        await sqlite_backend.add_page(page)
        await sqlite_backend.commit()

        assert await sqlite_backend.should_redownload("https://example.com", None) is False
        assert await sqlite_backend.should_redownload("https://example.com", 7) is True

        await sqlite_backend.close()
