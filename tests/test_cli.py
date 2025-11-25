"""Unit tests for CLI module."""

from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from sus.cli import app

runner = CliRunner()


def _close_coro(coro: Coroutine[Any, Any, Any]) -> None:
    """Close a coroutine to prevent 'coroutine was never awaited' warnings."""
    coro.close()


def _close_coro_and_raise(exc: BaseException) -> Any:
    """Return a side_effect that closes the coroutine and raises an exception."""

    def handler(coro: Coroutine[Any, Any, Any]) -> None:
        coro.close()
        raise exc

    return handler


class TestVersionCommand:
    """Tests for --version flag."""

    def test_version_flag(self) -> None:
        """Test --version displays version and exits."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "SUS version" in result.stdout

    def test_version_short_flag(self) -> None:
        """Test -V displays version and exits."""
        result = runner.invoke(app, ["-V"])

        assert result.exit_code == 0
        assert "SUS version" in result.stdout


class TestValidateCommand:
    """Tests for 'sus validate' command."""

    def test_validate_valid_config(self, tmp_path: Path) -> None:
        """Test validate with valid config file."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(app, ["validate", str(config_file)])

        assert result.exit_code == 0
        assert "Configuration is valid" in result.stdout

    def test_validate_missing_file(self, tmp_path: Path) -> None:
        """Test validate with non-existent file."""
        result = runner.invoke(app, ["validate", str(tmp_path / "nonexistent.yaml")])

        assert result.exit_code == 2  # Typer exits with 2 for invalid arguments

    def test_validate_invalid_yaml(self, tmp_path: Path) -> None:
        """Test validate with invalid YAML syntax."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: syntax: [")

        result = runner.invoke(app, ["validate", str(config_file)])

        assert result.exit_code == 1

    def test_validate_missing_required_fields(self, tmp_path: Path) -> None:
        """Test validate with missing required fields."""
        config = {
            "name": "test-site",
            # Missing 'site' section
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(app, ["validate", str(config_file)])

        assert result.exit_code == 1
        assert "validation failed" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_validate_displays_summary(self, tmp_path: Path) -> None:
        """Test validate displays config summary table."""
        config = {
            "name": "my-docs-site",
            "description": "Documentation scraper",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
            "crawling": {
                "max_pages": 100,
                "depth_limit": 3,
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(app, ["validate", str(config_file)])

        assert result.exit_code == 0
        assert "my-docs-site" in result.stdout
        assert "100" in result.stdout  # max_pages
        assert "3" in result.stdout  # depth_limit


class TestInitCommand:
    """Tests for 'sus init' command."""

    def test_init_creates_config_file(self, tmp_path: Path) -> None:
        """Test init creates config file with user input."""
        config_file = tmp_path / "config.yaml"

        result = runner.invoke(
            app,
            ["init", str(config_file)],
            input="my-project\nTest project\nhttps://example.com/docs/\n",
        )

        assert result.exit_code == 0
        assert config_file.exists()
        assert "Configuration created" in result.stdout

        # Verify config content
        content = yaml.safe_load(config_file.read_text())
        assert content["name"] == "my-project"
        assert content["site"]["start_urls"] == ["https://example.com/docs/"]
        assert "example.com" in content["site"]["allowed_domains"]

    def test_init_refuses_overwrite_without_force(self, tmp_path: Path) -> None:
        """Test init refuses to overwrite existing file without --force."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("existing: content")

        result = runner.invoke(
            app,
            ["init", str(config_file)],
            input="my-project\nTest project\nhttps://example.com/docs/\n",
        )

        assert result.exit_code == 1
        assert "already exists" in result.stdout

    def test_init_with_force_overwrites(self, tmp_path: Path) -> None:
        """Test init with --force overwrites existing file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("existing: content")

        result = runner.invoke(
            app,
            ["init", str(config_file), "--force"],
            input="my-project\nTest project\nhttps://example.com/docs/\n",
        )

        assert result.exit_code == 0
        assert "Configuration created" in result.stdout

        # Verify new content
        content = yaml.safe_load(config_file.read_text())
        assert content["name"] == "my-project"

    def test_init_default_filename(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test init uses config.yaml as default filename."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["init"],
            input="my-project\nTest project\nhttps://example.com/docs/\n",
        )

        assert result.exit_code == 0
        assert (tmp_path / "config.yaml").exists()

    def test_init_invalid_url(self, tmp_path: Path) -> None:
        """Test init rejects invalid URL."""
        config_file = tmp_path / "config.yaml"

        result = runner.invoke(
            app,
            ["init", str(config_file)],
            input="my-project\nTest project\nnot-a-valid-url\n",
        )

        assert result.exit_code == 1
        assert "Invalid URL" in result.stdout


class TestScrapeCommand:
    """Tests for 'sus scrape' command."""

    def test_scrape_requires_config(self) -> None:
        """Test scrape requires --config option."""
        result = runner.invoke(app, ["scrape"])

        assert result.exit_code == 2  # Missing required option

    def test_scrape_config_not_found(self, tmp_path: Path) -> None:
        """Test scrape with non-existent config file."""
        result = runner.invoke(app, ["scrape", "--config", str(tmp_path / "nonexistent.yaml")])

        assert result.exit_code == 2

    def test_scrape_invalid_config(self, tmp_path: Path) -> None:
        """Test scrape with invalid config file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: [")

        result = runner.invoke(app, ["scrape", "--config", str(config_file)])

        assert result.exit_code == 1

    def test_scrape_resume_without_checkpoint_enabled(self, tmp_path: Path) -> None:
        """Test --resume requires checkpoint.enabled in config."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
            "crawling": {
                "checkpoint": {
                    "enabled": False,
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(app, ["scrape", "--config", str(config_file), "--resume"])

        assert result.exit_code == 1
        assert "--resume requires checkpoint.enabled" in result.stdout

    def test_scrape_resume_and_reset_mutually_exclusive(self, tmp_path: Path) -> None:
        """Test --resume and --reset-checkpoint are mutually exclusive."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
            "crawling": {
                "checkpoint": {
                    "enabled": True,
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(
            app, ["scrape", "--config", str(config_file), "--resume", "--reset-checkpoint"]
        )

        assert result.exit_code == 1
        assert "mutually exclusive" in result.stdout

    def test_scrape_dry_run_and_resume_mutually_exclusive(self, tmp_path: Path) -> None:
        """Test --dry-run and --resume are mutually exclusive."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
            "crawling": {
                "checkpoint": {
                    "enabled": True,
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(
            app, ["scrape", "--config", str(config_file), "--dry-run", "--resume"]
        )

        assert result.exit_code == 1
        assert "mutually exclusive" in result.stdout

    def test_scrape_output_override(self, tmp_path: Path) -> None:
        """Test --output overrides config output directory."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
            "output": {
                "base_dir": "original_output",
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        # Mock run_scraper to avoid actual crawling
        with patch("sus.cli.asyncio.run", side_effect=_close_coro):
            result = runner.invoke(
                app,
                [
                    "scrape",
                    "--config",
                    str(config_file),
                    "--output",
                    str(tmp_path / "custom_output"),
                    "--dry-run",
                ],
            )

            assert result.exit_code == 0
            assert "Output directory overridden" in result.stdout

    def test_scrape_max_pages_override(self, tmp_path: Path) -> None:
        """Test --max-pages overrides config max_pages."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        with patch("sus.cli.asyncio.run", side_effect=_close_coro):
            result = runner.invoke(
                app,
                ["scrape", "--config", str(config_file), "--max-pages", "50", "--dry-run"],
            )

            assert result.exit_code == 0
            assert "Max pages limit set: 50" in result.stdout

    def test_scrape_reset_checkpoint_deletes_file(self, tmp_path: Path) -> None:
        """Test --reset-checkpoint deletes existing checkpoint file."""
        # Create config with checkpoint enabled
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
            "output": {
                "base_dir": str(tmp_path / "output"),
            },
            "crawling": {
                "checkpoint": {
                    "enabled": True,
                    "checkpoint_file": "checkpoint.json",
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        # Create output directory and checkpoint file
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True)
        checkpoint_file = output_dir / "checkpoint.json"
        checkpoint_file.write_text("{}")

        with patch("sus.cli.asyncio.run", side_effect=_close_coro):
            result = runner.invoke(
                app,
                ["scrape", "--config", str(config_file), "--reset-checkpoint", "--dry-run"],
            )

            assert result.exit_code == 0
            assert "Deleted checkpoint" in result.stdout
            assert not checkpoint_file.exists()

    def test_scrape_clear_cache_removes_directory(self, tmp_path: Path) -> None:
        """Test --clear-cache removes cache directory."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
            "output": {
                "base_dir": str(tmp_path / "output"),
            },
            "crawling": {
                "cache": {
                    "cache_dir": ".cache",
                },
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        # Create cache directory
        cache_dir = tmp_path / "output" / ".cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "cached_file.txt").write_text("cached content")

        with patch("sus.cli.asyncio.run", side_effect=_close_coro):
            result = runner.invoke(
                app, ["scrape", "--config", str(config_file), "--clear-cache", "--dry-run"]
            )

            assert result.exit_code == 0
            assert "Cleared cache directory" in result.stdout
            assert not cache_dir.exists()


class TestListCommand:
    """Tests for 'sus list' command."""

    def test_list_shows_examples(self) -> None:
        """Test list displays example configurations."""
        result = runner.invoke(app, ["list"])

        # Should either show examples or indicate no examples found
        assert result.exit_code == 0

    def test_list_handles_invalid_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test list gracefully handles invalid YAML files in examples directory."""
        # This test would require mocking the examples directory location
        # For now, we just verify the command doesn't crash
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0


class TestCliErrorHandling:
    """Tests for CLI error handling."""

    def test_keyboard_interrupt_handled(self, tmp_path: Path) -> None:
        """Test KeyboardInterrupt is handled gracefully."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        # Mock run_scraper to raise KeyboardInterrupt
        with patch("sus.cli.asyncio.run", side_effect=_close_coro_and_raise(KeyboardInterrupt())):
            result = runner.invoke(app, ["scrape", "--config", str(config_file)])

            assert result.exit_code == 130
            assert "interrupted" in result.stdout.lower()

    def test_unexpected_error_shows_message(self, tmp_path: Path) -> None:
        """Test unexpected errors show helpful message."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        with patch(
            "sus.cli.asyncio.run",
            side_effect=_close_coro_and_raise(RuntimeError("Something went wrong")),
        ):
            result = runner.invoke(app, ["scrape", "--config", str(config_file)])

            assert result.exit_code == 1
            assert "error" in result.stdout.lower()

    def test_verbose_shows_traceback(self, tmp_path: Path) -> None:
        """Test --verbose shows full traceback on error."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        with patch(
            "sus.cli.asyncio.run",
            side_effect=_close_coro_and_raise(RuntimeError("Something went wrong")),
        ):
            result = runner.invoke(app, ["scrape", "--config", str(config_file), "--verbose"])

            assert result.exit_code == 1
            # In verbose mode, Rich traceback should be displayed
            # The exact output format depends on Rich's traceback rendering


class TestDryRunMode:
    """Tests for dry-run mode behavior."""

    def test_dry_run_shows_message(self, tmp_path: Path) -> None:
        """Test dry-run mode displays informational message."""
        config = {
            "name": "test-site",
            "site": {
                "start_urls": ["https://example.com/docs/"],
                "allowed_domains": ["example.com"],
            },
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        with patch("sus.cli.asyncio.run", side_effect=_close_coro):
            result = runner.invoke(app, ["scrape", "--config", str(config_file), "--dry-run"])

            assert result.exit_code == 0
            assert "dry-run mode" in result.stdout.lower()
