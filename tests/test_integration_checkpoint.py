"""Integration tests for checkpoint system.

Tests the complete checkpoint workflow including:
- Checkpoint creation and resumption
- Config validation
- Crawler integration
- CLI integration
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from sus.checkpoint import PageCheckpoint
from sus.checkpoint_manager import CheckpointManager, compute_config_hash
from sus.config import SusConfig, load_config
from sus.crawler import Crawler


class TestCheckpointWorkflow:
    """Integration tests for complete checkpoint workflow."""

    async def test_checkpoint_save_and_load_workflow(self, tmp_path: Path) -> None:
        """Test complete checkpoint save and load workflow."""
        config_content = """
name: test-config
description: Test configuration
site:
  start_urls:
    - https://example.com/
  allowed_domains:
    - example.com
crawling:
  checkpoint:
    enabled: true
    backend: json
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        config: SusConfig = load_config(config_file)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        await checkpoint.add_page(
            url="https://example.com/page1",
            content_hash="hash1",
            status_code=200,
            file_path=str(tmp_path / "page1.md"),
        )
        await checkpoint.add_page(
            url="https://example.com/page2",
            content_hash="hash2",
            status_code=200,
            file_path=str(tmp_path / "page2.md"),
        )

        checkpoint.queue = [
            ("https://example.com/page3", None),
            ("https://example.com/page4", "https://example.com/page1"),
        ]

        # Save queue first, then metadata to ensure queue is persisted
        await checkpoint.backend.save_queue(checkpoint.queue)
        await checkpoint.save(checkpoint_file)
        await checkpoint.close()

        loaded = await CheckpointManager.load(checkpoint_file, config)

        assert loaded is not None
        assert loaded.config_name == "test-config"
        assert loaded.config_hash == checkpoint.config_hash
        page_count = await loaded.get_page_count()
        assert page_count == 2
        assert await loaded.has_page("https://example.com/page1")
        assert await loaded.has_page("https://example.com/page2")
        assert len(loaded.queue) == 2
        await loaded.close()

    async def test_checkpoint_with_config_validation(
        self, tmp_path: Path, mock_config_file: Path
    ) -> None:
        """Test checkpoint validates config hash."""
        config: SusConfig = load_config(mock_config_file)
        config_hash: str = compute_config_hash(config)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        await checkpoint.save(checkpoint_file)
        await checkpoint.close()

        loaded = await CheckpointManager.load(checkpoint_file, config)
        assert loaded is not None
        assert loaded.config_hash == config_hash

        config.name = "different-name"
        new_hash: str = compute_config_hash(config)

        assert new_hash != config_hash
        assert loaded.config_hash != new_hash
        await loaded.close()

    async def test_crawler_with_checkpoint(self, tmp_path: Path, mock_config_file: Path) -> None:
        """Test crawler integrates with checkpoint."""
        config: SusConfig = load_config(mock_config_file)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)
        await checkpoint.add_page(
            url="https://example.com/page1",
            content_hash="hash1",
            status_code=200,
            file_path="/output/page1.md",
        )

        crawler: Crawler = Crawler(config, checkpoint=checkpoint)

        assert crawler.checkpoint is checkpoint
        await checkpoint.close()

        # Note: visited set is restored in crawl() method

    async def test_checkpoint_periodic_save(self, tmp_path: Path) -> None:
        """Test periodic checkpoint saving logic."""
        config_content = """
name: test-config
description: Test configuration
site:
  start_urls:
    - https://example.com/
  allowed_domains:
    - example.com
crawling:
  checkpoint:
    enabled: true
    backend: json
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        config: SusConfig = load_config(config_file)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        # Simulate adding pages and periodic saves
        for i in range(15):
            await checkpoint.add_page(
                url=f"https://example.com/page{i}",
                content_hash=f"hash{i}",
                status_code=200,
                file_path=f"/output/page{i}.md",
            )

            # Save every 5 pages (simulating checkpoint_interval_pages=5)
            if (i + 1) % 5 == 0:
                await checkpoint.save(checkpoint_file)

        await checkpoint.close()

        # Load final checkpoint
        loaded = await CheckpointManager.load(checkpoint_file, config)
        assert loaded is not None
        page_count = await loaded.get_page_count()
        assert page_count == 15
        await loaded.close()

    async def test_checkpoint_resume_workflow(self, tmp_path: Path, mock_config_file: Path) -> None:
        """Test resume workflow with checkpoint."""
        config: SusConfig = load_config(mock_config_file)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        visited_urls: list[str] = [
            "https://example.com/page1",
            "https://example.com/page2",
        ]
        for url in visited_urls:
            await checkpoint.add_page(
                url=url,
                content_hash=f"hash_{url}",
                status_code=200,
                file_path=f"/output/{url.split('/')[-1]}.md",
            )

        checkpoint.queue = [
            ("https://example.com/page3", None),
            ("https://example.com/page4", "https://example.com/page1"),
        ]

        # Save queue first, then metadata to ensure queue is persisted
        await checkpoint.backend.save_queue(checkpoint.queue)
        await checkpoint.save(checkpoint_file)
        await checkpoint.close()

        loaded = await CheckpointManager.load(checkpoint_file, config)
        assert loaded is not None

        Crawler(config, checkpoint=loaded)

        # Verify visited pages are restored (happens in crawl())
        page_urls = await loaded.get_all_page_urls()
        assert page_urls == set(visited_urls)
        assert len(loaded.queue) == 2
        await loaded.close()

    async def test_checkpoint_age_based_revalidation(self, tmp_path: Path) -> None:
        """Test age-based revalidation in checkpoint."""
        config_content = """
name: test-config
description: Test configuration
site:
  start_urls:
    - https://example.com/
  allowed_domains:
    - example.com
crawling:
  checkpoint:
    enabled: true
    backend: json
    force_redownload_after_days: 7
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        config: SusConfig = load_config(config_file)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        await checkpoint.add_page(
            url="https://example.com/fresh",
            content_hash="hash_fresh",
            status_code=200,
            file_path="/output/fresh.md",
        )

        old_timestamp: str = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        old_page = PageCheckpoint(
            url="https://example.com/old",
            content_hash="hash_old",
            last_scraped=old_timestamp,
            status_code=200,
            file_path="/output/old.md",
        )
        await checkpoint.backend.add_page(old_page)

        # Check revalidation with 7-day limit
        assert not await checkpoint.should_redownload("https://example.com/fresh", 7)
        assert await checkpoint.should_redownload("https://example.com/old", 7)
        await checkpoint.close()

    async def test_checkpoint_with_empty_queue(self, tmp_path: Path) -> None:
        """Test checkpoint works with empty queue."""
        config_content = """
name: test-config
description: Test configuration
site:
  start_urls:
    - https://example.com/
  allowed_domains:
    - example.com
crawling:
  checkpoint:
    enabled: true
    backend: json
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        config: SusConfig = load_config(config_file)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        await checkpoint.add_page(
            url="https://example.com/page",
            content_hash="hash",
            status_code=200,
            file_path="/output/page.md",
        )

        await checkpoint.save(checkpoint_file)
        await checkpoint.close()

        loaded = await CheckpointManager.load(checkpoint_file, config)
        assert loaded is not None
        assert len(loaded.queue) == 0
        page_count = await loaded.get_page_count()
        assert page_count == 1
        await loaded.close()

    async def test_checkpoint_atomic_write(self, tmp_path: Path) -> None:
        """Test checkpoint uses atomic write (temp file + rename)."""
        config_content = """
name: test-config
description: Test configuration
site:
  start_urls:
    - https://example.com/
  allowed_domains:
    - example.com
crawling:
  checkpoint:
    enabled: true
    backend: json
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        config: SusConfig = load_config(config_file)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        await checkpoint.save(checkpoint_file)
        await checkpoint.close()

        # Verify no temp files left behind
        temp_files: list[Path] = list(tmp_path.glob(".sus_checkpoint_*.tmp"))
        assert len(temp_files) == 0

        assert checkpoint_file.exists()

    async def test_checkpoint_with_config_change(
        self, tmp_path: Path, mock_config_file: Path
    ) -> None:
        """Test checkpoint invalidation when config changes."""
        config: SusConfig = load_config(mock_config_file)
        original_hash: str = compute_config_hash(config)

        checkpoint_file = tmp_path / "checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        await checkpoint.save(checkpoint_file)
        await checkpoint.close()

        config.site.start_urls = ["https://different.com/"]
        new_hash: str = compute_config_hash(config)

        loaded = await CheckpointManager.load(checkpoint_file, config)
        assert loaded is not None

        assert loaded.config_hash != new_hash
        assert loaded.config_hash == original_hash
        await loaded.close()

    async def test_checkpoint_creation_on_initial_scrape(
        self, tmp_path: Path, httpx_mock: HTTPXMock
    ) -> None:
        """Test checkpoint file is created on initial scrape (not resume).

        Regression test for Bug #2: start URLs should be added to queue
        when checkpoint exists but is empty (initial scrape scenario).
        """
        # Mock HTTP responses
        httpx_mock.add_response(
            url="https://example.com/robots.txt",
            status_code=404,
        )
        httpx_mock.add_response(
            url="https://example.com/",
            html="<html><body><a href='/page1'>Page 1</a></body></html>",
        )
        httpx_mock.add_response(
            url="https://example.com/page1",
            html="<html><body>Content</body></html>",
        )

        # Create config with checkpoint enabled
        config_content = f"""
name: test-initial-checkpoint
description: Test checkpoint creation on initial scrape
site:
  start_urls:
    - https://example.com/
  allowed_domains:
    - example.com
crawling:
  max_pages: 2
  checkpoint:
    enabled: true
    checkpoint_file: .sus_checkpoint.json
    checkpoint_interval_pages: 1
    backend: json
output:
  base_dir: {tmp_path}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        config: SusConfig = load_config(config_file)

        # Create empty checkpoint (simulating initial scrape with checkpoint enabled)
        checkpoint_file = tmp_path / ".sus_checkpoint.json"
        checkpoint = await CheckpointManager.create_new(checkpoint_file, config)

        # Create crawler with empty checkpoint
        crawler: Crawler = Crawler(config, checkpoint=checkpoint)

        # Start crawl
        pages: list[str] = []
        async for result in crawler.crawl():
            pages.append(result.url)
            # Add page to checkpoint
            await checkpoint.add_page(
                url=result.url,
                content_hash="test_hash",
                status_code=result.status_code,
                file_path=f"{tmp_path}/{result.url.split('/')[-1]}.md",
            )
            if len(pages) >= 2:
                break

        # Verify pages were crawled (Bug #2 fix: start URLs should be added even with empty checkpoint)
        assert len(pages) > 0, "No pages crawled - Bug #2 not fixed!"
        assert "https://example.com/" in pages

        # Save checkpoint
        await checkpoint.save(checkpoint_file)

        # Verify checkpoint file was created
        assert checkpoint_file.exists(), "Checkpoint file not created!"

        # Load and verify checkpoint content
        loaded = await CheckpointManager.load(checkpoint_file, config)
        assert loaded is not None
        page_count = await loaded.get_page_count()
        assert page_count > 0
        assert loaded.config_name == "test-initial-checkpoint"
        await loaded.close()
        await checkpoint.close()


@pytest.fixture
def mock_config_file(tmp_path: Path) -> Path:
    """Create a mock config file for testing."""
    config_content = """
name: test-config
description: Test configuration
site:
  start_urls:
    - https://example.com/
  allowed_domains:
    - example.com
crawling:
  checkpoint:
    enabled: true
    checkpoint_interval_pages: 5
    force_redownload_after_days: 7
    backend: json
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return config_file
