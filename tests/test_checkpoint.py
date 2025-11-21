"""Unit tests for checkpoint system."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sus.checkpoint import (
    CHECKPOINT_VERSION,
    Checkpoint,
    PageCheckpoint,
    compute_config_hash,
    compute_content_hash,
)
from sus.config import SusConfig


class TestPageCheckpoint:
    """Tests for PageCheckpoint dataclass."""

    def test_create_page_checkpoint(self) -> None:
        """Test creating a PageCheckpoint instance."""
        page = PageCheckpoint(
            url="https://example.com/page",
            content_hash="abc123",
            last_scraped="2025-01-01T00:00:00+00:00",
            status_code=200,
            file_path="/output/page.md",
        )

        assert page.url == "https://example.com/page"
        assert page.content_hash == "abc123"
        assert page.last_scraped == "2025-01-01T00:00:00+00:00"
        assert page.status_code == 200
        assert page.file_path == "/output/page.md"

    def test_page_checkpoint_equality(self) -> None:
        """Test PageCheckpoint equality."""
        page1 = PageCheckpoint(
            url="https://example.com/page",
            content_hash="abc123",
            last_scraped="2025-01-01T00:00:00+00:00",
            status_code=200,
            file_path="/output/page.md",
        )
        page2 = PageCheckpoint(
            url="https://example.com/page",
            content_hash="abc123",
            last_scraped="2025-01-01T00:00:00+00:00",
            status_code=200,
            file_path="/output/page.md",
        )

        assert page1 == page2


class TestCheckpoint:
    """Tests for Checkpoint dataclass and methods."""

    def test_create_checkpoint(self) -> None:
        """Test creating a Checkpoint instance."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        assert checkpoint.version == CHECKPOINT_VERSION
        assert checkpoint.config_name == "test-config"
        assert checkpoint.config_hash == "hash123"
        assert len(checkpoint.pages) == 0
        assert len(checkpoint.queue) == 0
        assert len(checkpoint.stats) == 0

    def test_checkpoint_timestamps(self) -> None:
        """Test checkpoint has valid timestamps."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        # Verify timestamps are valid ISO 8601
        created_at = datetime.fromisoformat(checkpoint.created_at)
        last_updated = datetime.fromisoformat(checkpoint.last_updated)

        assert created_at.tzinfo is not None
        assert last_updated.tzinfo is not None

    def test_add_page(self) -> None:
        """Test adding a page to checkpoint."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        checkpoint.add_page(
            url="https://example.com/page",
            content_hash="abc123",
            status_code=200,
            file_path="/output/page.md",
        )

        assert "https://example.com/page" in checkpoint.pages
        page = checkpoint.pages["https://example.com/page"]
        assert page.content_hash == "abc123"
        assert page.status_code == 200
        assert page.file_path == "/output/page.md"

    def test_add_page_updates_existing(self) -> None:
        """Test adding a page updates existing entry."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        checkpoint.add_page(
            url="https://example.com/page",
            content_hash="abc123",
            status_code=200,
            file_path="/output/page.md",
        )

        checkpoint.add_page(
            url="https://example.com/page",
            content_hash="def456",
            status_code=200,
            file_path="/output/page.md",
        )

        # Should have only one entry with updated hash
        assert len(checkpoint.pages) == 1
        assert checkpoint.pages["https://example.com/page"].content_hash == "def456"

    async def test_save_checkpoint(self, tmp_path: Path) -> None:
        """Test saving checkpoint to file."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )
        checkpoint.add_page(
            url="https://example.com/page",
            content_hash="abc123",
            status_code=200,
            file_path="/output/page.md",
        )

        checkpoint_file = tmp_path / "checkpoint.json"
        await checkpoint.save(checkpoint_file)

        assert checkpoint_file.exists()

        # Verify JSON structure
        with open(checkpoint_file) as f:
            data = json.load(f)

        assert data["version"] == CHECKPOINT_VERSION
        assert data["config_name"] == "test-config"
        assert data["config_hash"] == "hash123"
        assert "https://example.com/page" in data["pages"]

    async def test_save_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test save creates parent directory if missing."""
        nested_dir = tmp_path / "nested" / "dir"
        checkpoint_file = nested_dir / "checkpoint.json"

        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        await checkpoint.save(checkpoint_file)

        assert checkpoint_file.exists()
        assert nested_dir.exists()

    async def test_save_updates_last_updated(self, tmp_path: Path) -> None:
        """Test save updates last_updated timestamp."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        original_last_updated = checkpoint.last_updated

        # Wait a tiny bit to ensure timestamp changes
        import asyncio

        await asyncio.sleep(0.01)

        checkpoint_file = tmp_path / "checkpoint.json"
        await checkpoint.save(checkpoint_file)

        # last_updated should be different
        assert checkpoint.last_updated != original_last_updated

    async def test_load_checkpoint(self, tmp_path: Path) -> None:
        """Test loading checkpoint from file."""
        original = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )
        original.add_page(
            url="https://example.com/page",
            content_hash="abc123",
            status_code=200,
            file_path="/output/page.md",
        )
        original.queue = [("https://example.com/next", None)]

        checkpoint_file = tmp_path / "checkpoint.json"
        await original.save(checkpoint_file)

        loaded = await Checkpoint.load(checkpoint_file)

        assert loaded is not None
        assert loaded.config_name == "test-config"
        assert loaded.config_hash == "hash123"
        assert "https://example.com/page" in loaded.pages
        assert loaded.queue == [("https://example.com/next", None)]

    async def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading nonexistent file returns None."""
        checkpoint_file = tmp_path / "nonexistent.json"
        loaded = await Checkpoint.load(checkpoint_file)

        assert loaded is None

    async def test_load_corrupted_json(self, tmp_path: Path) -> None:
        """Test loading corrupted JSON returns None."""
        checkpoint_file = tmp_path / "corrupted.json"
        checkpoint_file.write_text("{ invalid json }")

        loaded = await Checkpoint.load(checkpoint_file)

        assert loaded is None

    async def test_load_wrong_version(self, tmp_path: Path) -> None:
        """Test loading checkpoint with wrong version returns None."""
        checkpoint_file = tmp_path / "wrong_version.json"

        data = {
            "version": 999,  # Wrong version
            "config_name": "test",
            "config_hash": "hash",
            "created_at": "2025-01-01T00:00:00+00:00",
            "last_updated": "2025-01-01T00:00:00+00:00",
            "pages": {},
            "queue": [],
            "stats": {},
        }

        checkpoint_file.write_text(json.dumps(data))

        loaded = await Checkpoint.load(checkpoint_file)

        assert loaded is None

    async def test_load_missing_fields(self, tmp_path: Path) -> None:
        """Test loading checkpoint with missing fields returns None."""
        checkpoint_file = tmp_path / "missing_fields.json"

        data = {
            "version": CHECKPOINT_VERSION,
            # Missing other required fields
        }

        checkpoint_file.write_text(json.dumps(data))

        loaded = await Checkpoint.load(checkpoint_file)

        assert loaded is None


class TestShouldRedownload:
    """Tests for should_redownload logic."""

    def test_should_redownload_not_in_checkpoint(self) -> None:
        """Test URL not in checkpoint should be downloaded."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        assert checkpoint.should_redownload("https://example.com/new")

    def test_should_redownload_no_age_check(self) -> None:
        """Test URL in checkpoint with no age check."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )
        checkpoint.add_page(
            url="https://example.com/page",
            content_hash="abc123",
            status_code=200,
            file_path="/output/page.md",
        )

        # Without age check, should not redownload
        assert not checkpoint.should_redownload("https://example.com/page", None)

    def test_should_redownload_fresh_page(self) -> None:
        """Test URL in checkpoint that is fresh (within age limit)."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )
        checkpoint.add_page(
            url="https://example.com/page",
            content_hash="abc123",
            status_code=200,
            file_path="/output/page.md",
        )

        # Fresh page (just added) - should not redownload
        assert not checkpoint.should_redownload("https://example.com/page", 7)

    def test_should_redownload_old_page(self) -> None:
        """Test URL in checkpoint that is old (exceeds age limit)."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        # Add page with old timestamp
        old_timestamp = (datetime.now(UTC) - timedelta(days=10)).isoformat()

        page = PageCheckpoint(
            url="https://example.com/page",
            content_hash="abc123",
            last_scraped=old_timestamp,
            status_code=200,
            file_path="/output/page.md",
        )
        checkpoint.pages["https://example.com/page"] = page

        # Page is 10 days old, limit is 7 days - should redownload
        assert checkpoint.should_redownload("https://example.com/page", 7)

    def test_should_redownload_invalid_timestamp(self) -> None:
        """Test URL with invalid timestamp should be redownloaded."""
        checkpoint = Checkpoint(
            config_name="test-config",
            config_hash="hash123",
        )

        page = PageCheckpoint(
            url="https://example.com/page",
            content_hash="abc123",
            last_scraped="invalid timestamp",
            status_code=200,
            file_path="/output/page.md",
        )
        checkpoint.pages["https://example.com/page"] = page

        # Invalid timestamp - should redownload to be safe
        assert checkpoint.should_redownload("https://example.com/page", 7)


class TestComputeConfigHash:
    """Tests for compute_config_hash function."""

    def test_compute_config_hash(self, sample_config: SusConfig) -> None:
        """Test computing config hash."""
        hash1 = compute_config_hash(sample_config)

        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_config_hash_deterministic(self, sample_config: SusConfig) -> None:
        """Test config hash is deterministic."""
        hash1 = compute_config_hash(sample_config)
        hash2 = compute_config_hash(sample_config)

        assert hash1 == hash2

    def test_config_hash_changes_with_name(self, sample_config: SusConfig) -> None:
        """Test config hash changes when name changes."""
        hash1 = compute_config_hash(sample_config)

        sample_config.name = "different-name"
        hash2 = compute_config_hash(sample_config)

        assert hash1 != hash2

    def test_config_hash_changes_with_start_urls(self, sample_config: SusConfig) -> None:
        """Test config hash changes when start_urls change."""
        hash1 = compute_config_hash(sample_config)

        sample_config.site.start_urls = ["https://different.com/"]
        hash2 = compute_config_hash(sample_config)

        assert hash1 != hash2

    def test_config_hash_ignores_output_dir(self, sample_config: SusConfig) -> None:
        """Test config hash ignores output directory changes."""
        hash1 = compute_config_hash(sample_config)

        # Change output directory (should not affect hash)
        sample_config.output.base_dir = "/different/output"
        hash2 = compute_config_hash(sample_config)

        # Hash should remain the same
        assert hash1 == hash2


class TestComputeContentHash:
    """Tests for compute_content_hash function."""

    def test_compute_content_hash(self) -> None:
        """Test computing content hash."""
        html = "<html><body>Test content</body></html>"
        hash1 = compute_content_hash(html)

        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_content_hash_deterministic(self) -> None:
        """Test content hash is deterministic."""
        html = "<html><body>Test content</body></html>"
        hash1 = compute_content_hash(html)
        hash2 = compute_content_hash(html)

        assert hash1 == hash2

    def test_content_hash_changes_with_content(self) -> None:
        """Test content hash changes when content changes."""
        html1 = "<html><body>Test content</body></html>"
        html2 = "<html><body>Different content</body></html>"

        hash1 = compute_content_hash(html1)
        hash2 = compute_content_hash(html2)

        assert hash1 != hash2

    def test_content_hash_sensitive_to_whitespace(self) -> None:
        """Test content hash is sensitive to whitespace."""
        html1 = "<html><body>Test content</body></html>"
        html2 = "<html><body>Test  content</body></html>"  # Extra space

        hash1 = compute_content_hash(html1)
        hash2 = compute_content_hash(html2)

        assert hash1 != hash2

    def test_content_hash_empty_string(self) -> None:
        """Test content hash for empty string."""
        hash1 = compute_content_hash("")

        assert isinstance(hash1, str)
        assert len(hash1) == 64
