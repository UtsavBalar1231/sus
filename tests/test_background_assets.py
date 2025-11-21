"""Tests for background asset downloads (decoupled via asyncio.create_task)."""

import asyncio
import time
from pathlib import Path

import httpx
from pytest_httpx import HTTPXMock

from sus.config import (
    AssetConfig,
    CrawlingRules,
    OutputConfig,
    PathMappingConfig,
    SiteConfig,
    SusConfig,
)
from sus.scraper import run_scraper


async def test_asset_downloads_dont_block_crawling(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that slow asset downloads don't block page crawling.

    NOTE: This test uses timing assertions and may be sensitive to CI/system load.
    Timing threshold is set conservatively to reduce flakiness.
    """
    config = SusConfig(
        name="background-asset-test",
        site=SiteConfig(
            start_urls=[f"https://example.com/page{i}" for i in range(1, 6)],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            global_concurrent_requests=5,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(
            download=True,
            types=["images"],
        ),
    )

    # Mock pages with assets
    for i in range(1, 6):
        page_html = f'<html><head><title>Page {i}</title></head><body><img src="https://example.com/img{i}.png"></body></html>'
        httpx_mock.add_response(url=f"https://example.com/page{i}", html=page_html)

    # Mock asset downloads with 2 second delay each (total 10s if sequential)
    async def slow_asset_response(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(2.0)  # Simulate slow asset download
        return httpx.Response(200, content=b"fake-image-content")

    for i in range(1, 6):
        httpx_mock.add_callback(slow_asset_response, url=f"https://example.com/img{i}.png")

    # Measure crawling time
    start_time = time.time()
    stats = await run_scraper(config, dry_run=False)
    crawl_time = time.time() - start_time

    # Verify all pages were crawled
    assert stats["pages_crawled"] == 5

    # Verify crawling completed quickly (not waiting for slow assets)
    # If assets blocked crawling, this would take 10+ seconds (sequential)
    # With background tasks, should complete in <8 seconds (2s for assets in parallel + overhead)
    # Threshold set conservatively to account for slow CI runners
    assert crawl_time < 8.0, f"Crawling took {crawl_time:.2f}s - assets may be blocking"

    # Verify all assets were downloaded
    assert stats["assets_downloaded"] == 5


async def test_asset_tasks_are_awaited_at_end(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that all asset download tasks are awaited before returning stats."""
    config = SusConfig(
        name="asset-await-test",
        site=SiteConfig(
            start_urls=["https://example.com/page1", "https://example.com/page2"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(
            download=True,
            types=["images"],
        ),
    )

    # Mock pages with assets
    page1_html = '<html><body><img src="https://example.com/img1.png"></body></html>'
    page2_html = '<html><body><img src="https://example.com/img2.png"></body></html>'
    httpx_mock.add_response(url="https://example.com/page1", html=page1_html)
    httpx_mock.add_response(url="https://example.com/page2", html=page2_html)

    # Mock assets
    httpx_mock.add_response(url="https://example.com/img1.png", content=b"image1")
    httpx_mock.add_response(url="https://example.com/img2.png", content=b"image2")

    # Run scraper
    stats = await run_scraper(config, dry_run=False)

    # Verify all assets were downloaded (proves tasks were awaited)
    assert stats["assets_downloaded"] == 2
    assert stats["assets_failed"] == 0

    # Verify asset files exist on disk
    asset_files = list(Path(tmp_path).rglob("*.png"))
    assert len(asset_files) == 2


async def test_background_asset_failure_doesnt_stop_crawling(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    """Test that asset download failures don't prevent crawling from continuing."""
    config = SusConfig(
        name="asset-failure-test",
        site=SiteConfig(
            start_urls=[f"https://example.com/page{i}" for i in range(1, 4)],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(
            download=True,
            types=["images"],
        ),
    )

    # Mock pages with assets
    for i in range(1, 4):
        page_html = f'<html><body><img src="https://example.com/img{i}.png"></body></html>'
        httpx_mock.add_response(url=f"https://example.com/page{i}", html=page_html)

    # Mock asset downloads - first one fails, others succeed
    httpx_mock.add_response(url="https://example.com/img1.png", status_code=404)
    httpx_mock.add_response(url="https://example.com/img2.png", content=b"image2")
    httpx_mock.add_response(url="https://example.com/img3.png", content=b"image3")

    # Run scraper
    stats = await run_scraper(config, dry_run=False)

    # Verify all pages were crawled (asset failure didn't stop crawling)
    assert stats["pages_crawled"] == 3

    # Verify asset stats reflect partial success
    assert stats["assets_downloaded"] == 2
    assert stats["assets_failed"] == 1
