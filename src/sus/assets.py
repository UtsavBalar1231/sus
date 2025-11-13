"""Asset downloading and management.

Handles concurrent downloading of web assets (images, CSS, JavaScript) with progress
tracking and SHA-256 content deduplication. Provides AssetDownloader for async downloads
with configurable concurrency limits.
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import httpx

from sus.config import AssetConfig

if TYPE_CHECKING:
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
    errors: dict[str, int] = field(default_factory=dict)  # error_type -> count


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
        config: AssetConfig,
        output_manager: "OutputManager",
        client: httpx.AsyncClient | None = None,
    ):
        """Initialize asset downloader.

        Args:
            config: AssetConfig from SusConfig
            output_manager: OutputManager instance (for path resolution)
            client: Optional HTTP client (for testing with mocks)
        """
        self.config = config
        self.output_manager = output_manager
        self.client = client
        self.downloaded: set[str] = set()  # Track downloaded URLs
        self.stats = AssetStats()

        # Semaphore for concurrent downloads (limit to avoid overwhelming)
        self.semaphore = asyncio.Semaphore(config.max_concurrent_asset_downloads)

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
        # Skip if downloads disabled
        if not self.config.download:
            return self.stats

        # Filter duplicates
        unique_assets = [url for url in assets if url not in self.downloaded]

        # Nothing to download
        if not unique_assets:
            return self.stats

        # Create client if needed
        client_created = False
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "SUS/0.1.0 (Simple Universal Scraper)"},
            )
            client_created = True

        try:
            # Download concurrently
            tasks = [self._download_asset(url) for url in unique_assets]
            await asyncio.gather(*tasks, return_exceptions=True)

            return self.stats
        finally:
            # Only close if we created the client
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
                # Get file path from output manager
                file_path = self.output_manager.get_asset_path(url)

                # Skip if file exists
                if file_path.exists():
                    self.stats.skipped += 1
                    return

                # Download
                if self.client is None:
                    # This should not happen, but handle gracefully
                    self.stats.failed += 1
                    self.stats.errors["ClientNotInitialized"] = (
                        self.stats.errors.get("ClientNotInitialized", 0) + 1
                    )
                    return

                response = await self.client.get(url)
                response.raise_for_status()

                # Write to file
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(response.content)

                # Update stats
                self.downloaded.add(url)
                self.stats.downloaded += 1
                self.stats.total_bytes += len(response.content)

            except httpx.HTTPError as e:
                # Track error
                self.stats.failed += 1
                error_type = type(e).__name__
                self.stats.errors[error_type] = self.stats.errors.get(error_type, 0) + 1

            except Exception as e:
                # Track unexpected error
                self.stats.failed += 1
                error_type = type(e).__name__
                self.stats.errors[error_type] = self.stats.errors.get(error_type, 0) + 1
