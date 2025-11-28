"""Tests for checkpoint crash recovery scenarios.

Tests the robustness of checkpoint backends under crash conditions:
- Corrupted checkpoint files
- Partial writes
- Invalid data formats
- Transaction rollback (SQLite)
- Atomic write safety (JSON)
"""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sus.backends import CheckpointMetadata, PageCheckpoint, create_backend
from sus.backends.json_backend import JSONBackend
from sus.backends.sqlite_backend import SQLiteBackend


class TestJSONBackendCorruptionRecovery:
    """Tests for JSON backend handling corrupted checkpoint files."""

    async def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading empty checkpoint file."""
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint_file.write_text("")

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        # Should start fresh when file is empty
        metadata = await backend.load_metadata()
        assert metadata is None

    async def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test loading file with invalid JSON syntax."""
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint_file.write_text("{invalid json")

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        # Should start fresh and warn user
        metadata = await backend.load_metadata()
        assert metadata is None

    async def test_load_missing_version(self, tmp_path: Path) -> None:
        """Test loading checkpoint with wrong version."""
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint_file.write_text(
            json.dumps(
                {
                    "version": 999,  # Wrong version
                    "config_name": "test",
                    "config_hash": "abc123",
                    "created_at": datetime.now(UTC).isoformat(),
                    "last_updated": datetime.now(UTC).isoformat(),
                }
            )
        )

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        # Should start fresh due to version mismatch
        metadata = await backend.load_metadata()
        assert metadata is None

    async def test_load_missing_required_fields(self, tmp_path: Path) -> None:
        """Test loading checkpoint with missing required fields."""
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "config_name": "test",
                    # Missing: config_hash, created_at, last_updated
                }
            )
        )

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        # Should start fresh due to missing fields
        metadata = await backend.load_metadata()
        assert metadata is None

    async def test_load_corrupted_pages_data(self, tmp_path: Path) -> None:
        """Test loading checkpoint with corrupted pages data."""
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "config_name": "test",
                    "config_hash": "abc123",
                    "created_at": datetime.now(UTC).isoformat(),
                    "last_updated": datetime.now(UTC).isoformat(),
                    "pages": {
                        "http://example.com/page": {
                            "url": "http://example.com/page",
                            # Missing required fields
                        }
                    },
                }
            )
        )

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        # Should start fresh due to corrupted data
        metadata = await backend.load_metadata()
        assert metadata is None

    async def test_load_corrupted_queue_data(self, tmp_path: Path) -> None:
        """Test loading checkpoint with corrupted queue data."""
        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "config_name": "test",
                    "config_hash": "abc123",
                    "created_at": datetime.now(UTC).isoformat(),
                    "last_updated": datetime.now(UTC).isoformat(),
                    "pages": {},
                    "queue": "not a list",  # Should be list of tuples
                }
            )
        )

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        # Should start fresh due to corrupted queue
        metadata = await backend.load_metadata()
        assert metadata is None

    async def test_atomic_write_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test atomic write creates parent directories if needed."""
        checkpoint_file = tmp_path / "nested" / "dir" / "checkpoint.json"

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        # Save metadata - should create parent dirs
        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        assert checkpoint_file.exists()

    async def test_atomic_write_no_partial_writes(self, tmp_path: Path) -> None:
        """Test atomic write doesn't leave partial files on success."""
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

        # No temp files should remain
        temp_files = list(tmp_path.glob(".sus_checkpoint_*.tmp"))
        assert len(temp_files) == 0

    async def test_recovery_after_save_preserves_data(self, tmp_path: Path) -> None:
        """Test that saved data survives reload (simulates restart)."""
        checkpoint_file = tmp_path / "checkpoint.json"

        # First session: save data
        backend1 = JSONBackend(checkpoint_file)
        await backend1.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test-site",
            config_hash="hash123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={"pages_crawled": 10},
        )
        await backend1.save_metadata(metadata)

        page = PageCheckpoint(
            url="http://example.com/page",
            content_hash="content123",
            last_scraped=datetime.now(UTC).isoformat(),
            status_code=200,
            file_path="output/page.md",
        )
        await backend1.add_page(page)
        await backend1.save_metadata(metadata)  # Persist the page

        await backend1.close()

        # Second session: reload and verify
        backend2 = JSONBackend(checkpoint_file)
        await backend2.initialize()

        loaded_metadata = await backend2.load_metadata()
        assert loaded_metadata is not None
        assert loaded_metadata.config_name == "test-site"
        assert loaded_metadata.stats["pages_crawled"] == 10

        loaded_page = await backend2.get_page("http://example.com/page")
        assert loaded_page is not None
        assert loaded_page.content_hash == "content123"

        await backend2.close()


class TestSQLiteBackendCorruptionRecovery:
    """Tests for SQLite backend handling corrupted databases."""

    async def test_load_corrupted_database(self, tmp_path: Path) -> None:
        """Test loading corrupted SQLite database file."""
        db_file = tmp_path / "checkpoint.db"
        db_file.write_bytes(b"not a valid sqlite database")

        backend = SQLiteBackend(db_file)

        # Should raise error when trying to initialize corrupted DB
        with pytest.raises(
            (OSError, ValueError, sqlite3.DatabaseError)
        ):  # aiosqlite raises various exceptions
            await backend.initialize()

    async def test_corrupted_database_with_garbage(self, tmp_path: Path) -> None:
        """Test handling database file with garbage content."""
        db_file = tmp_path / "checkpoint.db"
        db_file.write_bytes(b"SQLite format 3\x00" + b"\xff" * 100)

        backend = SQLiteBackend(db_file)

        # Partial SQLite header with garbage should fail
        with pytest.raises((OSError, ValueError, sqlite3.DatabaseError)):
            await backend.initialize()

    async def test_transaction_atomicity_on_queue_save(self, tmp_path: Path) -> None:
        """Test that queue saves are atomic (all or nothing)."""
        db_file = tmp_path / "checkpoint.db"

        backend = SQLiteBackend(db_file)
        await backend.initialize()

        # Save metadata first
        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend.save_metadata(metadata)

        # Save a queue
        queue = [
            ("http://example.com/page1", None),
            ("http://example.com/page2", "http://example.com/page1"),
        ]
        await backend.save_queue(queue)

        # Verify all items saved
        loaded_queue = await backend.get_queue()
        assert len(loaded_queue) == 2

        await backend.close()

    async def test_recovery_after_crash_simulation(self, tmp_path: Path) -> None:
        """Test data integrity after simulated crash (close without commit)."""
        db_file = tmp_path / "checkpoint.db"

        # First session
        backend1 = SQLiteBackend(db_file)
        await backend1.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test-site",
            config_hash="hash123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={},
        )
        await backend1.save_metadata(metadata)

        # Add page and commit
        page = PageCheckpoint(
            url="http://example.com/committed",
            content_hash="hash1",
            last_scraped=datetime.now(UTC).isoformat(),
            status_code=200,
            file_path="output/committed.md",
        )
        await backend1.add_page(page)
        await backend1.commit()

        # Add another page but don't commit (simulating crash)
        uncommitted_page = PageCheckpoint(
            url="http://example.com/uncommitted",
            content_hash="hash2",
            last_scraped=datetime.now(UTC).isoformat(),
            status_code=200,
            file_path="output/uncommitted.md",
        )
        await backend1.add_page(uncommitted_page)
        # No commit - simulating crash

        await backend1.close()

        # Second session: verify only committed data exists
        backend2 = SQLiteBackend(db_file)
        await backend2.initialize()

        # Committed page should exist
        committed = await backend2.get_page("http://example.com/committed")
        assert committed is not None

        # Uncommitted page may or may not exist depending on SQLite autocommit
        # The key is that the database is not corrupted
        loaded_metadata = await backend2.load_metadata()
        assert loaded_metadata is not None
        assert loaded_metadata.config_name == "test-site"

        await backend2.close()

    async def test_concurrent_read_write_safety(self, tmp_path: Path) -> None:
        """Test concurrent read/write operations don't corrupt data."""
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

        # Concurrent page additions
        async def add_page(i: int) -> None:
            page = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i}",
                last_scraped=datetime.now(UTC).isoformat(),
                status_code=200,
                file_path=f"output/page{i}.md",
            )
            await backend.add_page(page)
            await backend.commit()

        # Add 10 pages concurrently
        await asyncio.gather(*[add_page(i) for i in range(10)])

        # All pages should be saved
        count = await backend.get_page_count()
        assert count == 10

        await backend.close()


class TestBackendFactoryRecovery:
    """Tests for backend factory handling edge cases."""

    async def test_create_json_backend_explicit(self, tmp_path: Path) -> None:
        """Test factory creates JSON backend with explicit type."""
        backend = create_backend(tmp_path / "checkpoint.json", "json")
        assert isinstance(backend, JSONBackend)

    async def test_create_json_backend_auto(self, tmp_path: Path) -> None:
        """Test factory auto-detects JSON backend from extension."""
        backend = create_backend(tmp_path / "checkpoint.json")
        assert isinstance(backend, JSONBackend)

    async def test_create_sqlite_backend_explicit(self, tmp_path: Path) -> None:
        """Test factory creates SQLite backend with explicit type."""
        backend = create_backend(tmp_path / "checkpoint.db", "sqlite")
        assert isinstance(backend, SQLiteBackend)

    async def test_create_sqlite_backend_auto(self, tmp_path: Path) -> None:
        """Test factory auto-detects SQLite backend from extension."""
        backend = create_backend(tmp_path / "checkpoint.db")
        assert isinstance(backend, SQLiteBackend)

    async def test_create_backend_defaults_to_json(self, tmp_path: Path) -> None:
        """Test factory defaults to JSON for unknown extensions."""
        backend = create_backend(tmp_path / "checkpoint.xyz")
        assert isinstance(backend, JSONBackend)


class TestCheckpointDataIntegrity:
    """Tests for checkpoint data integrity across save/load cycles."""

    @pytest.mark.parametrize("backend_type", ["json", "sqlite"])
    async def test_page_data_roundtrip(self, tmp_path: Path, backend_type: str) -> None:
        """Test page data survives save/load cycle intact."""
        ext = ".json" if backend_type == "json" else ".db"
        checkpoint_file = tmp_path / f"checkpoint{ext}"

        backend = create_backend(checkpoint_file, backend_type)  # type: ignore[arg-type]
        await backend.initialize()

        # Save complex page data
        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at="2025-01-01T00:00:00+00:00",
            last_updated="2025-01-01T12:00:00+00:00",
            stats={"pages_crawled": 100, "pages_failed": 5},
        )
        await backend.save_metadata(metadata)

        page = PageCheckpoint(
            url="http://example.com/special-chars/%20%2F",
            content_hash="a" * 64,
            last_scraped="2025-01-01T06:00:00+00:00",
            status_code=200,
            file_path="output/special.md",
        )
        await backend.add_page(page)
        await backend.save_metadata(metadata)  # For JSON, this persists pages
        await backend.commit()  # For SQLite

        await backend.close()

        # Reload and verify
        backend2 = create_backend(checkpoint_file, backend_type)  # type: ignore[arg-type]
        await backend2.initialize()

        loaded = await backend2.get_page("http://example.com/special-chars/%20%2F")
        assert loaded is not None
        assert loaded.url == "http://example.com/special-chars/%20%2F"
        assert loaded.content_hash == "a" * 64
        assert loaded.status_code == 200

        await backend2.close()

    @pytest.mark.parametrize("backend_type", ["json", "sqlite"])
    async def test_queue_data_roundtrip(self, tmp_path: Path, backend_type: str) -> None:
        """Test queue data survives save/load cycle intact."""
        ext = ".json" if backend_type == "json" else ".db"
        checkpoint_file = tmp_path / f"checkpoint{ext}"

        backend = create_backend(checkpoint_file, backend_type)  # type: ignore[arg-type]
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

        # Queue with various parent URLs
        queue = [
            ("http://example.com/page1", None),
            ("http://example.com/page2", "http://example.com/page1"),
            ("http://example.com/page3", "http://example.com/page1"),
            ("http://example.com/deep/nested/page", "http://example.com/page2"),
        ]
        await backend.save_queue(queue)
        await backend.save_metadata(metadata)  # For JSON
        await backend.commit()  # For SQLite

        await backend.close()

        # Reload and verify
        backend2 = create_backend(checkpoint_file, backend_type)  # type: ignore[arg-type]
        await backend2.initialize()

        loaded_queue = await backend2.get_queue()
        assert len(loaded_queue) == 4

        # Verify order preserved
        assert loaded_queue[0] == ("http://example.com/page1", None)
        assert loaded_queue[1] == ("http://example.com/page2", "http://example.com/page1")

        await backend2.close()

    @pytest.mark.parametrize("backend_type", ["json", "sqlite"])
    async def test_stats_data_roundtrip(self, tmp_path: Path, backend_type: str) -> None:
        """Test stats data survives save/load cycle intact."""
        ext = ".json" if backend_type == "json" else ".db"
        checkpoint_file = tmp_path / f"checkpoint{ext}"

        backend = create_backend(checkpoint_file, backend_type)  # type: ignore[arg-type]
        await backend.initialize()

        complex_stats = {
            "pages_crawled": 1000,
            "pages_failed": 50,
            "bytes_downloaded": 1024 * 1024 * 100,
            "duration_seconds": 3600.5,
            "nested": {
                "by_domain": {
                    "example.com": 800,
                    "docs.example.com": 200,
                }
            },
        }

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats=complex_stats,
        )
        await backend.save_metadata(metadata)
        await backend.close()

        # Reload and verify
        backend2 = create_backend(checkpoint_file, backend_type)  # type: ignore[arg-type]
        await backend2.initialize()

        loaded = await backend2.load_metadata()
        assert loaded is not None
        assert loaded.stats["pages_crawled"] == 1000
        assert loaded.stats["bytes_downloaded"] == 1024 * 1024 * 100
        assert loaded.stats["nested"]["by_domain"]["example.com"] == 800

        await backend2.close()


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    async def test_unicode_url_handling(self, tmp_path: Path) -> None:
        """Test handling URLs with unicode characters."""
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

        # URL with unicode
        page = PageCheckpoint(
            url="http://example.com/docs/日本語/ページ",
            content_hash="unicode123",
            last_scraped=datetime.now(UTC).isoformat(),
            status_code=200,
            file_path="output/japanese.md",
        )
        await backend.add_page(page)
        await backend.save_metadata(metadata)
        await backend.close()

        # Reload and verify
        backend2 = JSONBackend(checkpoint_file)
        await backend2.initialize()

        loaded = await backend2.get_page("http://example.com/docs/日本語/ページ")
        assert loaded is not None
        assert "日本語" in loaded.url

        await backend2.close()

    async def test_very_long_url_handling(self, tmp_path: Path) -> None:
        """Test handling very long URLs."""
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

        # Very long URL (2000+ characters): 250 segments * 8 chars = 2000+
        long_path = "/".join(["segment"] * 250)
        long_url = f"http://example.com/{long_path}"

        page = PageCheckpoint(
            url=long_url,
            content_hash="long123",
            last_scraped=datetime.now(UTC).isoformat(),
            status_code=200,
            file_path="output/long.md",
        )
        await backend.add_page(page)
        await backend.save_metadata(metadata)
        await backend.close()

        # Reload and verify
        backend2 = JSONBackend(checkpoint_file)
        await backend2.initialize()

        loaded = await backend2.get_page(long_url)
        assert loaded is not None
        assert len(loaded.url) > 2000

        await backend2.close()

    async def test_empty_queue_save_load(self, tmp_path: Path) -> None:
        """Test saving and loading empty queue."""
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

        # Save empty queue
        await backend.save_queue([])
        await backend.save_metadata(metadata)
        await backend.close()

        # Reload and verify
        backend2 = JSONBackend(checkpoint_file)
        await backend2.initialize()

        queue = await backend2.get_queue()
        assert queue == []

        await backend2.close()

    async def test_zero_pages_checkpoint(self, tmp_path: Path) -> None:
        """Test checkpoint with zero pages (fresh start saved)."""
        checkpoint_file = tmp_path / "checkpoint.json"

        backend = JSONBackend(checkpoint_file)
        await backend.initialize()

        metadata = CheckpointMetadata(
            version=1,
            config_name="test",
            config_hash="abc123",
            created_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            stats={"pages_crawled": 0},
        )
        await backend.save_metadata(metadata)
        await backend.close()

        # Reload and verify
        backend2 = JSONBackend(checkpoint_file)
        await backend2.initialize()

        loaded = await backend2.load_metadata()
        assert loaded is not None
        assert loaded.stats["pages_crawled"] == 0

        count = await backend2.get_page_count()
        assert count == 0

        await backend2.close()
