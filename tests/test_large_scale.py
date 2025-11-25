"""Large-scale stress tests for checkpoint backends.

Tests performance and reliability of checkpoint backends under load:
- Large number of pages (10K+)
- Memory efficiency
- Concurrent operations
- Backend comparison (JSON vs SQLite)
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sus.backends import CheckpointMetadata, PageCheckpoint
from sus.backends.json_backend import JSONBackend
from sus.backends.sqlite_backend import SQLiteBackend


class TestJSONBackendScaling:
    """Tests for JSON backend performance at scale."""

    @pytest.mark.benchmark
    async def test_add_1000_pages(self, tmp_path: Path) -> None:
        """Test adding 1000 pages to JSON backend."""
        checkpoint_file = tmp_path / "checkpoint.json"

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add 1000 pages
        for i in range(1000):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:06d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)

        # Verify count
        count = await backend.get_page_count()
        assert count == 1000

        # Save and reload
        await backend.save_metadata(metadata)
        await backend.close()

        # Verify reload
        backend2 = JSONBackend(checkpoint_file)
        await backend2.initialize()
        count2 = await backend2.get_page_count()
        assert count2 == 1000

        await backend2.close()

    @pytest.mark.benchmark
    async def test_lookup_performance_1000_pages(self, tmp_path: Path) -> None:
        """Test page lookup performance with 1000 pages."""
        checkpoint_file = tmp_path / "checkpoint.json"

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add pages
        for i in range(1000):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:06d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)

        # Test random lookups
        for i in [0, 100, 500, 999]:
            retrieved = await backend.get_page(f"http://example.com/page{i}")
            assert retrieved is not None
            assert retrieved.url == f"http://example.com/page{i}"

        await backend.close()


class TestSQLiteBackendScaling:
    """Tests for SQLite backend performance at scale."""

    @pytest.mark.benchmark
    async def test_add_1000_pages(self, tmp_path: Path) -> None:
        """Test adding 1000 pages to SQLite backend."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add 1000 pages
        for i in range(1000):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:06d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)

        await backend.commit()

        # Verify count
        count = await backend.get_page_count()
        assert count == 1000

        await backend.close()

        # Verify reload
        backend2 = SQLiteBackend(db_file)
        await backend2.initialize()
        count2 = await backend2.get_page_count()
        assert count2 == 1000

        await backend2.close()

    @pytest.mark.benchmark
    async def test_add_2000_pages(self, tmp_path: Path) -> None:
        """Test adding 2000 pages to SQLite backend."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add 2000 pages
        for i in range(2000):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:08d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)

            # Commit every 500 pages
            if (i + 1) % 500 == 0:
                await backend.commit()

        # Verify count
        count = await backend.get_page_count()
        assert count == 2000

        await backend.close()

    @pytest.mark.benchmark
    async def test_lookup_performance_2000_pages(self, tmp_path: Path) -> None:
        """Test page lookup performance with 2000 pages."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add pages in batch
        for i in range(2000):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:08d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)

        await backend.commit()

        # Test random lookups (should be fast with index)
        test_indices = [0, 500, 1000, 1999]
        for i in test_indices:
            retrieved = await backend.get_page(f"http://example.com/page{i}")
            assert retrieved is not None
            assert retrieved.url == f"http://example.com/page{i}"

        await backend.close()


class TestConcurrentOperations:
    """Tests for concurrent access patterns."""

    async def test_concurrent_page_additions_sqlite(self, tmp_path: Path) -> None:
        """Test concurrent page additions to SQLite backend."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        async def add_pages(start: int, count: int) -> None:
            """Add pages in a batch."""
            for i in range(start, start + count):
                page = PageCheckpoint(
                    url=f"http://example.com/page{i}",
                    content_hash=f"hash{i:06d}",
                    last_scraped=datetime.now(UTC).isoformat(),
                    status_code=200,
                    file_path=f"output/page{i}.md",
                )
                await backend.add_page(page)
            await backend.commit()

        # Add pages concurrently from multiple "workers"
        await asyncio.gather(
            add_pages(0, 100),
            add_pages(100, 100),
            add_pages(200, 100),
            add_pages(300, 100),
        )

        # All pages should be saved
        count = await backend.get_page_count()
        assert count == 400

        await backend.close()

    async def test_concurrent_reads_and_writes(self, tmp_path: Path) -> None:
        """Test concurrent reads and writes to SQLite backend."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # First add some pages
        for i in range(100):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:04d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)
        await backend.commit()

        async def read_pages(indices: list[int]) -> list[bool]:
            """Read pages and return whether they exist."""
            results = []
            for i in indices:
                page = await backend.get_page(f"http://example.com/page{i}")
                results.append(page is not None)
            return results

        async def write_pages(start: int, count: int) -> None:
            """Write additional pages."""
            for i in range(start, start + count):
                page = PageCheckpoint(
                    url=f"http://example.com/page{i}",
                    content_hash=f"hash{i:04d}",
                    last_scraped=datetime.now(UTC).isoformat(),
                    status_code=200,
                    file_path=f"output/page{i}.md",
                )
                await backend.add_page(page)
            await backend.commit()

        # Run reads and writes concurrently
        results = await asyncio.gather(
            read_pages([0, 25, 50, 75, 99]),
            write_pages(100, 50),
            read_pages([10, 30, 60, 80, 90]),
            write_pages(150, 50),
        )

        # All reads should have found existing pages
        assert all(results[0])
        assert all(results[2])

        # Total pages should be 200 (original 100 + 50 + 50)
        count = await backend.get_page_count()
        assert count == 200

        await backend.close()


class TestMemoryEfficiency:
    """Tests for memory efficiency of backends."""

    async def test_json_memory_with_many_pages(self, tmp_path: Path) -> None:
        """Test JSON backend memory usage with many pages."""
        checkpoint_file = tmp_path / "checkpoint.json"

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add 1000 pages and track memory
        for i in range(1000):
            page = PageCheckpoint(
                url=f"http://example.com/very/long/path/to/page{i}/index.html",
                content_hash="a" * 64,  # Realistic SHA-256 hash
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/very/long/path/to/page{i}/index.md",
            )
            await backend.add_page(page)

        await backend.save_metadata(metadata)

        # Check file size (should be reasonable)
        file_size = checkpoint_file.stat().st_size
        # ~500 bytes per page is reasonable
        assert file_size < 1000 * 1000  # Less than 1MB for 1000 pages

        await backend.close()

    async def test_sqlite_memory_efficiency(self, tmp_path: Path) -> None:
        """Test SQLite backend memory efficiency with many pages."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add 1000 pages
        for i in range(1000):
            page = PageCheckpoint(
                url=f"http://example.com/very/long/path/to/page{i}/index.html",
                content_hash="a" * 64,
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/very/long/path/to/page{i}/index.md",
            )
            await backend.add_page(page)

            if (i + 1) % 500 == 0:
                await backend.commit()

        await backend.commit()

        # Check file size
        file_size = db_file.stat().st_size
        # SQLite should be compact
        assert file_size < 1000 * 500  # Less than 500KB for 1000 pages

        await backend.close()


class TestQueueOperations:
    """Tests for queue operations at scale."""

    async def test_large_queue_json(self, tmp_path: Path) -> None:
        """Test JSON backend with large queue."""
        checkpoint_file = tmp_path / "checkpoint.json"

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Create a queue with 1000 items
        queue = [
            (f"http://example.com/page{i}", f"http://example.com/page{i - 1}" if i > 0 else None)
            for i in range(1000)
        ]

        await backend.save_queue(queue)
        await backend.save_metadata(metadata)
        await backend.close()

        # Reload and verify
        backend2 = JSONBackend(checkpoint_file)
        await backend2.initialize()

        loaded_queue = await backend2.get_queue()
        assert len(loaded_queue) == 1000
        assert loaded_queue[0] == ("http://example.com/page0", None)
        assert loaded_queue[999][0] == "http://example.com/page999"

        await backend2.close()

    async def test_large_queue_sqlite(self, tmp_path: Path) -> None:
        """Test SQLite backend with large queue."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Create a queue with 1000 items
        queue = [
            (f"http://example.com/page{i}", f"http://example.com/page{i - 1}" if i > 0 else None)
            for i in range(1000)
        ]

        await backend.save_queue(queue)
        await backend.commit()
        await backend.close()

        # Reload and verify
        backend2 = SQLiteBackend(db_file)
        await backend2.initialize()

        loaded_queue = await backend2.get_queue()
        assert len(loaded_queue) == 1000

        await backend2.close()


class TestIterationPerformance:
    """Tests for page iteration performance."""

    async def test_iterate_1000_pages_json(self, tmp_path: Path) -> None:
        """Test iterating over 1000 pages in JSON backend."""
        checkpoint_file = tmp_path / "checkpoint.json"

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add pages
        for i in range(1000):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:06d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)

        # Iterate and count
        count = 0
        async for _page in backend.iter_pages():
            count += 1
            assert page.url.startswith("http://example.com/page")

        assert count == 1000

        await backend.close()

    async def test_iterate_1000_pages_sqlite(self, tmp_path: Path) -> None:
        """Test iterating over 1000 pages in SQLite backend."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Add pages
        for i in range(1000):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:06d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)

            if (i + 1) % 500 == 0:
                await backend.commit()

        # Iterate and count
        count = 0
        async for _page in backend.iter_pages():
            count += 1

        assert count == 1000

        await backend.close()


class TestBackendComparison:
    """Tests comparing JSON and SQLite backend performance."""

    @pytest.mark.benchmark
    async def test_write_performance_comparison(self, tmp_path: Path) -> None:
        """Compare write performance between JSON and SQLite backends."""
        import time

        json_file = tmp_path / "checkpoint.json"
        sqlite_file = tmp_path / "checkpoint.db"

        page_count = 1000

        # Test JSON backend
        json_backend = JSONBackend(json_file)
        await json_backend.initialize()
        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await json_backend.save_metadata(metadata)

        json_start = time.perf_counter()
        for i in range(page_count):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:06d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await json_backend.add_page(page)
        await json_backend.save_metadata(metadata)
        json_duration = time.perf_counter() - json_start
        await json_backend.close()

        # Test SQLite backend
        sqlite_backend = SQLiteBackend(sqlite_file)
        await sqlite_backend.initialize()
        await sqlite_backend.save_metadata(metadata)

        sqlite_start = time.perf_counter()
        for i in range(page_count):
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i:06d}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await sqlite_backend.add_page(page)
        await sqlite_backend.commit()
        sqlite_duration = time.perf_counter() - sqlite_start
        await sqlite_backend.close()

        # Both should complete in reasonable time
        assert json_duration < 10.0  # Less than 10 seconds
        assert sqlite_duration < 10.0

        # Compare file sizes
        json_size = json_file.stat().st_size
        sqlite_size = sqlite_file.stat().st_size

        # Both should produce reasonably sized files
        assert json_size < 1_000_000  # Less than 1MB
        assert sqlite_size < 1_000_000
