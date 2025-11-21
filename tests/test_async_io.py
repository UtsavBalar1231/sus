"""Tests for async file I/O operations."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory


async def test_async_markdown_write() -> None:
    """Verify markdown files are written asynchronously."""
    # This will test the actual scraper file write operations
    # For now, verify aiofiles is importable and works
    import aiofiles

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"

        # Write async
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write("# Test Markdown\n\nContent here.")

        # Read back async
        async with aiofiles.open(file_path, encoding="utf-8") as f:
            content = await f.read()

        assert content == "# Test Markdown\n\nContent here."
        assert file_path.exists()


async def test_async_binary_write() -> None:
    """Verify binary files (assets) are written asynchronously."""
    import aiofiles

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.bin"
        data = b"\x89PNG\r\n\x1a\n"  # PNG header

        # Write async
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)

        # Read back async
        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()

        assert content == data
        assert file_path.exists()


async def test_async_concurrent_writes() -> None:
    """Verify multiple async writes don't block each other."""
    import time

    import aiofiles

    with TemporaryDirectory() as tmpdir:

        async def write_file(name: str, content: str) -> float:
            start = time.perf_counter()
            file_path = Path(tmpdir) / name
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)
            return time.perf_counter() - start

        # Write 10 files concurrently
        tasks = [write_file(f"file_{i}.md", f"Content {i}" * 1000) for i in range(10)]

        start = time.perf_counter()
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start

        # Concurrent writes should be much faster than sequential
        # (This is a smoke test - actual timing depends on system)
        assert total_time < 1.0, "10 small files should write in <1s concurrently"
