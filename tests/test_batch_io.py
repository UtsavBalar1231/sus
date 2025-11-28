"""Tests for batch I/O writer."""

from pathlib import Path

from sus.io import AsyncWritePool, BatchWriter


class TestBatchWriter:
    """Tests for BatchWriter class."""

    async def test_write_single_file(self, tmp_path: Path) -> None:
        """Test writing a single file."""
        async with BatchWriter(batch_size=5) as writer:
            await writer.write(tmp_path / "test.txt", "Hello, World!")

        assert (tmp_path / "test.txt").exists()
        assert (tmp_path / "test.txt").read_text() == "Hello, World!"

    async def test_batch_flush_on_size(self, tmp_path: Path) -> None:
        """Test automatic flush when batch size reached."""
        async with BatchWriter(batch_size=3) as writer:
            # Write 5 files - should auto-flush after 3
            for i in range(5):
                await writer.write(tmp_path / f"file{i}.txt", f"Content {i}")

            # First batch should have been flushed
            assert writer.stats.batches_flushed >= 1

        # All files should exist after context exit
        for i in range(5):
            assert (tmp_path / f"file{i}.txt").exists()

    async def test_manual_flush(self, tmp_path: Path) -> None:
        """Test manual flush."""
        writer = BatchWriter(batch_size=100, auto_flush=False)

        await writer.write(tmp_path / "test1.txt", "Content 1")
        await writer.write(tmp_path / "test2.txt", "Content 2")

        # Files shouldn't exist yet (no flush)
        assert not (tmp_path / "test1.txt").exists()
        assert not (tmp_path / "test2.txt").exists()

        # Manual flush
        count = await writer.flush()
        assert count == 2

        # Now files should exist
        assert (tmp_path / "test1.txt").exists()
        assert (tmp_path / "test2.txt").exists()

    async def test_stats_tracking(self, tmp_path: Path) -> None:
        """Test statistics tracking."""
        async with BatchWriter(batch_size=10) as writer:
            for i in range(5):
                await writer.write(tmp_path / f"file{i}.md", f"# Title {i}\n\nContent")

        assert writer.stats.files_written == 5
        assert writer.stats.bytes_written > 0
        assert writer.stats.batches_flushed >= 1

    async def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that parent directories are created."""
        async with BatchWriter(batch_size=5) as writer:
            await writer.write(tmp_path / "nested" / "deep" / "file.txt", "Content")

        assert (tmp_path / "nested" / "deep" / "file.txt").exists()

    async def test_pending_count(self, tmp_path: Path) -> None:
        """Test pending count tracking."""
        writer = BatchWriter(batch_size=10, auto_flush=False)

        assert writer.pending_count == 0
        assert writer.pending_bytes == 0

        await writer.write(tmp_path / "file1.txt", "Hello")
        assert writer.pending_count == 1
        assert writer.pending_bytes == 5

        await writer.write(tmp_path / "file2.txt", "World")
        assert writer.pending_count == 2
        assert writer.pending_bytes == 10

        await writer.flush()
        assert writer.pending_count == 0
        assert writer.pending_bytes == 0


class TestAsyncWritePool:
    """Tests for AsyncWritePool class."""

    async def test_distributed_writes(self, tmp_path: Path) -> None:
        """Test writes distributed across workers."""
        async with AsyncWritePool(workers=2, batch_size=5) as pool:
            for i in range(10):
                await pool.write(tmp_path / f"file{i}.txt", f"Content {i}")

        # All files should exist
        for i in range(10):
            assert (tmp_path / f"file{i}.txt").exists()

    async def test_combined_stats(self, tmp_path: Path) -> None:
        """Test combined statistics from all workers."""
        async with AsyncWritePool(workers=2, batch_size=5) as pool:
            for i in range(8):
                await pool.write(tmp_path / f"file{i}.txt", f"Content {i}")

            combined = pool.get_combined_stats()
            # Files written depends on auto-flush triggers
            assert combined.files_written <= 8

        # After exit, all should be flushed
        combined = pool.get_combined_stats()
        assert combined.files_written == 8
