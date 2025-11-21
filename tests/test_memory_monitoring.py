"""Tests for memory monitoring."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import psutil
import pytest
from pydantic import ValidationError
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


def test_psutil_available() -> None:
    """Verify psutil is installed and working."""
    # Get current process memory
    process = psutil.Process()
    memory_info = process.memory_info()

    assert memory_info.rss > 0, "Should report RSS memory usage"
    assert memory_info.vms > 0, "Should report VMS memory usage"


def test_memory_percent_calculation() -> None:
    """Verify memory percentage calculation."""
    process = psutil.Process()
    memory_percent = process.memory_percent()

    assert 0.0 <= memory_percent <= 100.0, "Memory percent should be 0-100%"


def test_system_memory_info() -> None:
    """Verify system memory info is accessible."""
    memory = psutil.virtual_memory()

    assert memory.total > 0, "Should report total memory"
    assert memory.available > 0, "Should report available memory"
    assert 0.0 <= memory.percent <= 100.0, "Should report memory percent"


async def test_memory_monitoring_in_scraper() -> None:
    """Verify scraper tracks memory usage."""
    # This is a smoke test - just verify psutil integration works
    import psutil

    # Memory monitoring should not crash scraper
    process = psutil.Process()
    initial_memory = process.memory_info().rss / (1024 * 1024)

    assert initial_memory > 0, "Should measure memory before scraping"

    # Note: Full integration test would require running actual scraper
    # For now, verify psutil is working correctly


async def test_scraper_warns_at_80_percent_memory(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that scraper warns when memory exceeds 80%."""
    # Create config programmatically
    config = SusConfig(
        name="test-memory-warning",
        site=SiteConfig(
            start_urls=[f"https://example.com/page{i}" for i in range(1, 16)],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            global_concurrent_requests=1,
            max_pages=15,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(download=False),
    )

    # Mock HTTP responses for all pages
    page_html = "<html><head><title>Test</title></head><body><h1>Test</h1></body></html>"
    for i in range(1, 16):
        httpx_mock.add_response(url=f"https://example.com/page{i}", html=page_html)

    # Create memory_info mock
    memory_info_mock = Mock()
    memory_info_mock.rss = 500 * 1024 * 1024  # 500MB

    # Mock psutil to return 85% memory on 10th page check
    memory_percents = [50.0] * 9 + [85.0] * 10  # Low memory for 9 pages, then 85%

    mock_process = Mock()
    mock_process.memory_percent.side_effect = memory_percents
    mock_process.memory_info.return_value = memory_info_mock

    with patch("psutil.Process", return_value=mock_process):
        # Capture console output
        console_output: list[str] = []

        def capture_print(*args: Any, **kwargs: Any) -> None:
            if args:
                console_output.append(str(args[0]))

        with patch("rich.console.Console.print", side_effect=capture_print):
            stats = await run_scraper(config, dry_run=True)

    # Verify warning was printed
    warning_found = any(
        "High memory usage" in line or "warning" in line.lower() for line in console_output
    )
    assert warning_found, f"Expected memory warning at 80%, console output: {console_output}"

    # Verify scraper continued (not stopped)
    assert stats["pages_crawled"] > 10, (
        f"Scraper should continue after 80% warning, crawled {stats['pages_crawled']}"
    )
    assert stats.get("stopped_reason") != "high_memory", "Should not stop at 80%"


async def test_scraper_stops_at_95_percent_memory(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that scraper stops when memory exceeds 95%."""
    # Create config programmatically
    config = SusConfig(
        name="test-memory-stop",
        site=SiteConfig(
            start_urls=[f"https://example.com/page{i}" for i in range(1, 21)],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            global_concurrent_requests=1,
            max_pages=20,
            memory_check_interval=10,  # Check every 10 pages for this test
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(download=False),
    )

    # Mock HTTP responses for first 10 pages (scraper should stop at page 10 due to high memory)
    page_html = "<html><head><title>Test</title></head><body><h1>Test</h1></body></html>"
    for i in range(1, 11):
        httpx_mock.add_response(url=f"https://example.com/page{i}", html=page_html)

    # Create memory_info mock
    memory_info_mock = Mock()
    memory_info_mock.rss = 2000 * 1024 * 1024  # 2GB

    # Mock psutil to always return 96% critical memory
    mock_process = Mock()
    mock_process.memory_percent.return_value = 96.0  # Always return critical memory
    mock_process.memory_info.return_value = memory_info_mock

    with patch("psutil.Process", return_value=mock_process):
        # Capture console output
        console_output: list[str] = []

        def capture_print(*args: Any, **kwargs: Any) -> None:
            if args:
                console_output.append(str(args[0]))

        with patch("rich.console.Console.print", side_effect=capture_print):
            stats = await run_scraper(config, dry_run=True)

    # Verify critical memory message was printed
    critical_found = any(
        "CRITICAL MEMORY USAGE" in line or "prevent OOM crash" in line for line in console_output
    )
    assert critical_found, f"Expected critical memory message, console output: {console_output}"

    # Verify scraper stopped at page 10 (not all 20 pages)
    assert stats["pages_crawled"] == 10, (
        f"Expected scraper to stop at 10 pages, got {stats['pages_crawled']}"
    )

    # Verify stopped_reason is returned
    assert "stopped_reason" in stats, "Should include stopped_reason when scraper stops early"
    assert stats["stopped_reason"] == "high_memory", "stopped_reason should be high_memory"


async def test_memory_stats_in_final_report(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that memory statistics are included in final stats."""
    # Create config programmatically
    config = SusConfig(
        name="test-memory-stats",
        site=SiteConfig(
            start_urls=[f"https://example.com/page{i}" for i in range(1, 11)],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            global_concurrent_requests=1,
            max_pages=10,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(download=False),
    )

    # Mock HTTP responses for all pages
    page_html = "<html><head><title>Test</title></head><body><h1>Test</h1></body></html>"
    for i in range(1, 11):
        httpx_mock.add_response(url=f"https://example.com/page{i}", html=page_html)

    # Mock psutil with realistic memory values
    memory_info_mock = Mock()
    memory_info_mock.rss = 100 * 1024 * 1024  # 100MB

    mock_process = Mock()
    mock_process.memory_percent.return_value = 25.0  # 25% memory usage
    mock_process.memory_info.return_value = memory_info_mock

    with patch("psutil.Process", return_value=mock_process):
        stats = await run_scraper(config, dry_run=True)

    # Verify memory stats are present (flattened structure)
    assert "final_memory_mb" in stats, "Should include final_memory_mb"
    assert "final_memory_percent" in stats, "Should include final_memory_percent"

    # Verify values are reasonable
    assert stats["final_memory_mb"] > 0, "Memory usage should be positive"
    assert 0 <= stats["final_memory_percent"] <= 100, "Memory percent should be 0-100%"


async def test_memory_check_interval_default() -> None:
    """Test that memory_check_interval defaults to 1 (every page)."""
    config = SusConfig(
        name="interval-default-test",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
    )

    # Verify default is 1
    assert config.crawling.memory_check_interval == 1


async def test_memory_check_interval_validation() -> None:
    """Test that memory_check_interval validates correctly."""
    # Valid values
    config1 = SusConfig(
        name="interval-valid-1",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(memory_check_interval=1),
    )
    assert config1.crawling.memory_check_interval == 1

    config5 = SusConfig(
        name="interval-valid-5",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(memory_check_interval=5),
    )
    assert config5.crawling.memory_check_interval == 5

    # Invalid value (< 1) should raise ValidationError
    with pytest.raises(ValidationError):
        SusConfig(
            name="interval-invalid",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            crawling=CrawlingRules(memory_check_interval=0),
        )


async def test_memory_check_interval_behavior(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that memory checks happen at correct intervals."""
    config = SusConfig(
        name="interval-behavior-test",
        site=SiteConfig(
            start_urls=[f"https://example.com/page{i}" for i in range(1, 16)],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            global_concurrent_requests=1,  # Sequential to ensure order
            memory_check_interval=5,  # Check every 5 pages
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(download=False),
    )

    # Mock HTTP responses
    page_html = "<html><head><title>Test</title></head><body><h1>Test</h1></body></html>"
    for i in range(1, 16):
        httpx_mock.add_response(url=f"https://example.com/page{i}", html=page_html)

    # Track psutil.Process() calls
    call_count = 0

    def mock_process_factory() -> Mock:
        nonlocal call_count
        call_count += 1
        mock = Mock()
        mock.memory_percent.return_value = 25.0
        mock.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
        return mock

    with patch("psutil.Process", side_effect=mock_process_factory):
        stats = await run_scraper(config, dry_run=True)

    # Verify all pages crawled
    assert stats["pages_crawled"] == 15

    # Memory should be checked at pages: 5, 10, 15, plus final check = 4 total calls
    # (interval=5 means check at 5, 10, 15, not 1, 2, 3, 4, 6, 7...)
    assert call_count == 4, f"Expected 4 memory checks (pages 5, 10, 15 + final), got {call_count}"


async def test_memory_check_every_page(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    """Test that memory_check_interval=1 checks every page."""
    config = SusConfig(
        name="interval-every-page-test",
        site=SiteConfig(
            start_urls=[f"https://example.com/page{i}" for i in range(1, 6)],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.01,
            global_concurrent_requests=1,
            memory_check_interval=1,  # Check every page
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(strip_prefix=None),
        ),
        assets=AssetConfig(download=False),
    )

    # Mock HTTP responses
    page_html = "<html><head><title>Test</title></head><body><h1>Test</h1></body></html>"
    for i in range(1, 6):
        httpx_mock.add_response(url=f"https://example.com/page{i}", html=page_html)

    # Track psutil.Process() calls
    call_count = 0

    def mock_process_factory() -> Mock:
        nonlocal call_count
        call_count += 1
        mock = Mock()
        mock.memory_percent.return_value = 25.0
        mock.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
        return mock

    with patch("psutil.Process", side_effect=mock_process_factory):
        stats = await run_scraper(config, dry_run=True)

    # Verify all pages crawled
    assert stats["pages_crawled"] == 5

    # Memory should be checked at every page: 1, 2, 3, 4, 5, plus final check = 6 total calls
    assert call_count == 6, f"Expected 6 memory checks (every page + final), got {call_count}"
