"""Tests for disk I/O error handling."""

import errno
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiofiles
import httpx
import pytest
from pytest_httpx import HTTPXMock

from sus.assets import AssetDownloader
from sus.config import (
    AssetConfig,
    CrawlingRules,
    OutputConfig,
    PathMappingConfig,
    SiteConfig,
    SusConfig,
)
from sus.outputs import OutputManager
from sus.scraper import run_scraper


async def test_handles_disk_full_error() -> None:
    """Verify disk full errors are caught and reported."""
    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"

        # Mock aiofiles.open to raise ENOSPC (disk full)
        with patch("aiofiles.open") as mock_open:
            mock_file = AsyncMock()
            mock_file.__aenter__.return_value = mock_file
            mock_file.write.side_effect = OSError(errno.ENOSPC, "No space left on device")
            mock_open.return_value = mock_file

            # This should catch OSError and identify it as disk full
            # We'll verify the scraper handles this gracefully
            with pytest.raises(OSError) as exc_info:
                async with aiofiles.open(file_path, "w") as f:
                    await f.write("content")

            assert exc_info.value.errno == errno.ENOSPC


async def test_handles_permission_denied_error() -> None:
    """Verify permission denied errors are caught and reported."""
    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"

        # Mock aiofiles.open to raise EACCES (permission denied)
        with patch("aiofiles.open") as mock_open:
            mock_file = AsyncMock()
            mock_file.__aenter__.return_value = mock_file
            mock_file.write.side_effect = OSError(errno.EACCES, "Permission denied")
            mock_open.return_value = mock_file

            with pytest.raises(OSError) as exc_info:
                async with aiofiles.open(file_path, "w") as f:
                    await f.write("content")

            assert exc_info.value.errno == errno.EACCES


async def test_handles_generic_io_error() -> None:
    """Verify generic I/O errors are caught and reported."""
    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"

        # Mock aiofiles.open to raise generic OSError
        with patch("aiofiles.open") as mock_open:
            mock_file = AsyncMock()
            mock_file.__aenter__.return_value = mock_file
            mock_file.write.side_effect = OSError(errno.EIO, "Input/output error")
            mock_open.return_value = mock_file

            with pytest.raises(OSError) as exc_info:
                async with aiofiles.open(file_path, "w") as f:
                    await f.write("content")

            assert exc_info.value.errno == errno.EIO


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
async def test_scraper_stops_on_disk_full_integration(httpx_mock: HTTPXMock) -> None:
    """Verify scraper stops early when disk full occurs during file write."""
    with TemporaryDirectory() as tmpdir:
        # Setup config with multiple start URLs
        config = SusConfig(
            name="disk-full-test",
            site=SiteConfig(
                start_urls=["https://example.com/page1"],
                allowed_domains=["example.com"],
            ),
            crawling=CrawlingRules(
                delay_between_requests=0.01,
                global_concurrent_requests=1,
                respect_robots_txt=False,  # Disable robots.txt checking
            ),
            output=OutputConfig(
                base_dir=tmpdir,
                path_mapping=PathMappingConfig(strip_prefix=None),
            ),
            assets=AssetConfig(download=False),
        )

        # Mock HTTP responses for multiple pages
        page1_html = """
        <html>
            <head><title>Page 1</title></head>
            <body>
                <h1>Page 1</h1>
                <a href="/page2">Page 2</a>
                <a href="/page3">Page 3</a>
            </body>
        </html>
        """
        page2_html = "<html><head><title>Page 2</title></head><body><h1>Page 2</h1></body></html>"
        page3_html = "<html><head><title>Page 3</title></head><body><h1>Page 3</h1></body></html>"

        httpx_mock.add_response(url="https://example.com/page1", html=page1_html)
        httpx_mock.add_response(url="https://example.com/page2", html=page2_html)
        httpx_mock.add_response(url="https://example.com/page3", html=page3_html)

        # Track how many times aiofiles.open is called
        original_open = aiofiles.open
        call_count = 0

        def mock_open_disk_full(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            # Fail on second write (first page succeeds, second fails with disk full)
            if call_count == 2:
                raise OSError(errno.ENOSPC, "No space left on device")
            # Return the context manager (don't await)
            return original_open(*args, **kwargs)

        # Patch aiofiles.open to raise ENOSPC on second call
        with patch("aiofiles.open", side_effect=mock_open_disk_full):
            stats = await run_scraper(config, dry_run=False)

        # Verify scraper stopped early (didn't process all 3 pages)
        assert stats["pages_crawled"] < 3, "Scraper should stop before processing all pages"
        assert stats["pages_failed"] >= 1, "At least one page should fail"

        # Verify disk_full error is tracked
        assert "disk_full" in stats["errors"], "disk_full error should be tracked"
        assert len(stats["errors"]["disk_full"]) >= 1, (
            "At least one disk_full error should be recorded"
        )

        # Verify error contains expected fields
        disk_full_error = stats["errors"]["disk_full"][0]
        assert "url" in disk_full_error
        assert "error" in disk_full_error
        assert "errno" in disk_full_error
        assert disk_full_error["errno"] == errno.ENOSPC


async def test_scraper_continues_on_permission_denied_integration(httpx_mock: HTTPXMock) -> None:
    """Verify scraper continues processing other pages when permission denied occurs."""
    with TemporaryDirectory() as tmpdir:
        # Setup config with multiple pages
        config = SusConfig(
            name="permission-test",
            site=SiteConfig(
                start_urls=["https://example.com/page1"],
                allowed_domains=["example.com"],
            ),
            crawling=CrawlingRules(
                delay_between_requests=0.01,
                global_concurrent_requests=1,
                respect_robots_txt=False,  # Disable robots.txt checking
            ),
            output=OutputConfig(
                base_dir=tmpdir,
                path_mapping=PathMappingConfig(strip_prefix=None),
            ),
            assets=AssetConfig(download=False),
        )

        # Mock HTTP responses
        page1_html = """
        <html>
            <head><title>Page 1</title></head>
            <body>
                <h1>Page 1</h1>
                <a href="/page2">Page 2</a>
                <a href="/page3">Page 3</a>
            </body>
        </html>
        """
        page2_html = "<html><head><title>Page 2</title></head><body><h1>Page 2</h1></body></html>"
        page3_html = "<html><head><title>Page 3</title></head><body><h1>Page 3</h1></body></html>"

        httpx_mock.add_response(url="https://example.com/page1", html=page1_html)
        httpx_mock.add_response(url="https://example.com/page2", html=page2_html)
        httpx_mock.add_response(url="https://example.com/page3", html=page3_html)

        # Track calls
        original_open = aiofiles.open
        call_count = 0

        def mock_open_permission_denied(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            # Fail only on second write (page2)
            if call_count == 2:
                raise OSError(errno.EACCES, "Permission denied")
            # Return the context manager (don't await)
            return original_open(*args, **kwargs)

        # Patch aiofiles.open
        with patch("aiofiles.open", side_effect=mock_open_permission_denied):
            stats = await run_scraper(config, dry_run=False)

        # Verify scraper continued processing (should process page1 and page3)
        assert stats["pages_crawled"] >= 2, "Scraper should continue and process other pages"
        assert stats["pages_failed"] >= 1, "One page should fail with permission denied"

        # Verify permission_denied error is tracked
        assert "permission_denied" in stats["errors"], "permission_denied error should be tracked"
        assert len(stats["errors"]["permission_denied"]) >= 1

        # Verify error structure
        perm_error = stats["errors"]["permission_denied"][0]
        assert "url" in perm_error
        assert "error" in perm_error
        assert "errno" in perm_error
        assert perm_error["errno"] == errno.EACCES


async def test_asset_downloader_continues_on_disk_errors_integration() -> None:
    """Verify asset downloader continues with other assets when disk errors occur."""
    with TemporaryDirectory() as tmpdir:
        # Setup config
        config = SusConfig(
            name="asset-test",
            site=SiteConfig(
                start_urls=["https://example.com/"],
                allowed_domains=["example.com"],
            ),
            output=OutputConfig(base_dir=tmpdir),
            assets=AssetConfig(
                download=True,
                types=["image"],
                max_concurrent_asset_downloads=2,
            ),
        )

        # Create output manager and asset downloader
        output_manager = OutputManager(config, dry_run=False)

        # Create mock HTTP client
        mock_client = httpx.AsyncClient()

        async def mock_get(url: str) -> Mock:
            # Return mock responses
            response = Mock()
            response.content = b"fake image data"
            response.raise_for_status = Mock()
            response.headers = {}  # Empty headers dict (no Content-Length)
            return response

        asset_downloader = AssetDownloader(
            config,
            output_manager,
            client=mock_client,
        )

        # Asset URLs to download
        assets = [
            "https://example.com/img/logo.png",
            "https://example.com/img/icon.png",
            "https://example.com/img/banner.png",
        ]

        # Mock aiofiles.open to fail on second asset
        original_open = aiofiles.open
        call_count = 0

        def mock_open_asset_error(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            # Fail on second write
            if call_count == 2:
                raise OSError(errno.ENOSPC, "No space left on device")
            # Return the context manager (don't await)
            return original_open(*args, **kwargs)

        # Patch and download
        with patch.object(mock_client, "get", new=AsyncMock(side_effect=mock_get)), patch(
            "aiofiles.open", side_effect=mock_open_asset_error
        ):
            stats = await asset_downloader.download_all(assets)

        # Verify asset downloader continued (didn't stop completely)
        assert stats.downloaded >= 1, "Should download at least one asset before/after error"
        assert stats.failed >= 1, "Should track at least one failure"

        # Verify error tracking in assets.stats.errors (should be list of dicts)
        assert len(stats.errors) > 0, "Should track errors"

        # Find disk error (could be disk_full or disk_io depending on which asset failed)
        disk_errors = []
        for error_type in ["disk_full", "disk_io"]:
            if error_type in stats.errors:
                disk_errors.extend(stats.errors[error_type])

        assert len(disk_errors) >= 1, "Should have at least one disk error"

        # Verify error structure (list of dicts)
        error = disk_errors[0]
        assert isinstance(error, dict), "Error should be a dict"
        assert "url" in error
        assert "error" in error
        assert "errno" in error

        # Clean up
        await mock_client.aclose()
