"""Asset downloading and management.

Concurrent downloading of web assets (images, CSS, JavaScript) with progress tracking,
SHA-256 content deduplication, and configurable concurrency limits via AssetDownloader.
"""

import asyncio
import errno
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import aiofiles
import httpx

from sus.http_client import create_http_client

if TYPE_CHECKING:
    from sus.config import SusConfig
    from sus.outputs import OutputManager


@dataclass
class Asset:
    """Represents an asset to download.

    Attributes:
        url: Asset URL (absolute)
        type: Asset type (image, css, js, font)
        original_src: Original src attribute from HTML
    """

    url: str
    type: Literal["image", "css", "js", "font"]
    original_src: str


@dataclass
class AssetStats:
    """Statistics for asset downloads.

    Tracks download success/failure counts and total bytes.
    """

    downloaded: int = 0
    failed: int = 0
    skipped: int = 0  # Already exists
    total_bytes: int = 0
    # error_type -> list of error dicts
    errors: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


class AssetDownloader:
    """Downloads assets concurrently with error handling.

    Features:
    - Concurrent downloads with semaphore limiting
    - Skip existing files (idempotent)
    - Comprehensive error tracking
    - Progress tracking via stats
    """

    def __init__(
        self,
        config: "SusConfig",
        output_manager: "OutputManager",
        client: httpx.AsyncClient | None = None,
    ):
        """Initialize asset downloader.

        Args:
            config: Full SusConfig (for accessing asset and crawling settings)
            output_manager: OutputManager instance (for path resolution)
            client: Optional HTTP client (for testing with mocks)
        """
        self.config = config
        self.output_manager = output_manager
        self.client = client
        self.downloaded: set[str] = set()  # Track downloaded URLs
        self.stats = AssetStats()

        # Semaphore for concurrent downloads (limit to avoid overwhelming)
        self.semaphore = asyncio.Semaphore(config.assets.max_concurrent_asset_downloads)

    async def _ensure_client(self) -> None:
        """Ensure HTTP client is initialized."""
        if self.client is None:
            self.client = create_http_client(self.config)

    async def download_all(self, assets: list[str]) -> AssetStats:
        """Download all assets concurrently.

        Args:
            assets: List of asset URLs to download

        Returns:
            AssetStats with download results

        Logic:
        1. Filter out already downloaded assets
        2. Create HTTP client if not provided
        3. Create async tasks for each asset
        4. Gather all tasks (use asyncio.gather with return_exceptions=True)
        5. Update stats based on results
        6. Close client if we created it
        """
        if not self.config.assets.download:
            return self.stats

        unique_assets = [url for url in assets if url not in self.downloaded]

        if not unique_assets:
            return self.stats

        client_created = False
        if self.client is None:
            await self._ensure_client()
            client_created = True

        try:
            tasks = [self._download_asset(url) for url in unique_assets]
            await asyncio.gather(*tasks, return_exceptions=True)

            return self.stats
        finally:
            if client_created and self.client:
                await self.client.aclose()
                self.client = None

    async def _download_asset(self, url: str) -> None:
        """Download a single asset.

        Args:
            url: Asset URL to download

        Logic:
        1. Acquire semaphore
        2. Get file path from output_manager.get_asset_path()
        3. Check if file already exists (skip if it does)
        4. Make HTTP request
        5. Write to file (create parent dirs)
        6. Update stats (downloaded, total_bytes)
        7. Handle errors gracefully (log to stats.errors)
        """
        async with self.semaphore:
            try:
                file_path = self.output_manager.get_asset_path(url)

                if file_path.exists():
                    self.stats.skipped += 1
                    return

                if self.client is None:
                    # This should not happen, but handle gracefully
                    self.stats.failed += 1
                    if "ClientNotInitialized" not in self.stats.errors:
                        self.stats.errors["ClientNotInitialized"] = []
                    self.stats.errors["ClientNotInitialized"].append(
                        {"url": url, "error": "HTTP client not initialized"}
                    )
                    return

                response = await self.client.get(url)
                response.raise_for_status()

                content_length = response.headers.get("content-length")
                if content_length and self.output_manager.config.crawling.max_asset_size_mb:
                    try:
                        size_mb = int(content_length) / (1024 * 1024)
                        if size_mb > self.output_manager.config.crawling.max_asset_size_mb:
                            self.stats.failed += 1
                            if "FileTooLarge" not in self.stats.errors:
                                self.stats.errors["FileTooLarge"] = []
                            max_size_mb = self.output_manager.config.crawling.max_asset_size_mb
                            error_msg = (
                                f"Asset size {size_mb:.1f}MB exceeds limit of {max_size_mb}MB"
                            )
                            self.stats.errors["FileTooLarge"].append(
                                {"url": url, "error": error_msg}
                            )
                            # Skip this asset (best-effort)
                            return
                    except ValueError:
                        # Invalid Content-Length header - skip check, proceed with download
                        pass

                file_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(response.content)

                self.downloaded.add(url)
                self.stats.downloaded += 1
                self.stats.total_bytes += len(response.content)

            except httpx.HTTPError as e:
                self.stats.failed += 1
                error_type = type(e).__name__
                if error_type not in self.stats.errors:
                    self.stats.errors[error_type] = []
                self.stats.errors[error_type].append({"url": url, "error": str(e)})

            except OSError as e:
                self.stats.failed += 1

                if e.errno == errno.ENOSPC:
                    error_type = "disk_full"
                    # Log but don't stop (assets are best-effort)
                elif e.errno == errno.EACCES:
                    error_type = "permission_denied"
                else:
                    error_type = "disk_io"

                # Track as list of dicts (consistent with scraper.py)
                if error_type not in self.stats.errors:
                    self.stats.errors[error_type] = []
                self.stats.errors[error_type].append(
                    {"url": url, "error": str(e), "errno": e.errno}
                )

            except Exception as e:
                # Track other errors (HTTP, conversion, etc.)
                self.stats.failed += 1
                error_type = type(e).__name__
                if error_type not in self.stats.errors:
                    self.stats.errors[error_type] = []
                self.stats.errors[error_type].append({"url": url, "error": str(e)})
