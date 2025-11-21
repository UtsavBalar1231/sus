"""Example tests demonstrating usage of typed factory functions from conftest.py."""

from pathlib import Path

import pytest

from tests.conftest import (
    create_basic_config,
    create_checkpoint_metadata,
    create_config_with_auth,
    create_config_with_checkpoint,
    create_config_with_javascript,
    create_config_with_patterns,
    create_crawl_result,
    create_page_checkpoint,
)


def test_create_basic_config() -> None:
    """Test basic config factory function."""
    config = create_basic_config(
        name="test-site",
        start_urls=["https://example.com/docs"],
        allowed_domains=["example.com"],
    )

    assert config.name == "test-site"
    assert config.site.start_urls == ["https://example.com/docs"]
    assert config.site.allowed_domains == ["example.com"]
    assert config.crawling.respect_robots_txt is False
    assert config.crawling.max_retries == 1


def test_create_config_with_javascript() -> None:
    """Test JavaScript config factory function."""
    config = create_config_with_javascript(
        start_urls=["https://spa.example.com"],
        wait_for="domcontentloaded",
    )

    assert config.crawling.javascript.enabled is True
    assert config.crawling.javascript.wait_for == "domcontentloaded"


def test_create_config_with_checkpoint(tmp_path: Path) -> None:
    """Test checkpoint config factory function."""
    checkpoint_file = tmp_path / "checkpoint.json"

    config = create_config_with_checkpoint(
        checkpoint_file=checkpoint_file,
        backend="json",
    )

    assert config.crawling.checkpoint.enabled is True
    assert config.crawling.checkpoint.backend == "json"
    assert str(checkpoint_file) in config.crawling.checkpoint.checkpoint_file


def test_create_config_with_auth_basic() -> None:
    """Test auth config factory function with basic auth."""
    config = create_config_with_auth(
        auth_type="basic",
        username="testuser",
        password="testpass",
    )

    assert config.crawling.authentication.enabled is True
    assert config.crawling.authentication.auth_type == "basic"
    assert config.crawling.authentication.username == "testuser"
    assert config.crawling.authentication.password == "testpass"


def test_create_config_with_auth_cookie() -> None:
    """Test auth config factory function with cookie auth."""
    config = create_config_with_auth(auth_type="cookie")

    assert config.crawling.authentication.enabled is True
    assert config.crawling.authentication.auth_type == "cookie"
    assert "session" in config.crawling.authentication.cookies


def test_create_config_with_auth_header() -> None:
    """Test auth config factory function with header auth."""
    config = create_config_with_auth(auth_type="header")

    assert config.crawling.authentication.enabled is True
    assert config.crawling.authentication.auth_type == "header"
    assert "Authorization" in config.crawling.authentication.headers


def test_create_config_with_auth_oauth2() -> None:
    """Test auth config factory function with OAuth2."""
    config = create_config_with_auth(auth_type="oauth2")

    assert config.crawling.authentication.enabled is True
    assert config.crawling.authentication.auth_type == "oauth2"
    assert config.crawling.authentication.client_id == "test-client"
    assert config.crawling.authentication.token_url is not None


def test_create_config_with_auth_invalid() -> None:
    """Test auth config factory function with invalid auth type."""
    with pytest.raises(ValueError, match="Unknown auth_type"):
        create_config_with_auth(auth_type="invalid")


def test_create_config_with_patterns() -> None:
    """Test pattern config factory function."""
    config = create_config_with_patterns(
        include_patterns=["^/docs/", "/api/"],
        exclude_patterns=["*.pdf", "*/private/*"],
    )

    assert len(config.crawling.include_patterns) == 2
    assert len(config.crawling.exclude_patterns) == 2
    assert config.crawling.include_patterns[0].type == "regex"
    assert config.crawling.include_patterns[1].type == "prefix"
    assert config.crawling.exclude_patterns[0].type == "glob"
    assert config.crawling.exclude_patterns[1].type == "glob"


def test_create_crawl_result() -> None:
    """Test crawl result factory function."""
    result = create_crawl_result(
        url="https://example.com/docs",
        links=["https://example.com/docs/guide"],
        assets=["https://example.com/img/logo.png"],
    )

    assert result.url == "https://example.com/docs"
    assert result.status_code == 200
    assert len(result.links) == 1
    assert len(result.assets) == 1
    assert result.content_hash != ""


def test_create_crawl_result_with_custom_html() -> None:
    """Test crawl result factory with custom HTML."""
    html = "<html><body><h1>Test</h1></body></html>"
    result = create_crawl_result(html=html)

    assert result.html == html
    assert result.content_hash != ""


def test_create_page_checkpoint() -> None:
    """Test page checkpoint factory function."""
    checkpoint = create_page_checkpoint(
        url="https://example.com/docs",
        content_hash="abc123" + "0" * 58,
        status_code=200,
        file_path="output/docs.md",
    )

    assert checkpoint.url == "https://example.com/docs"
    assert checkpoint.content_hash == "abc123" + "0" * 58
    assert checkpoint.status_code == 200
    assert checkpoint.file_path == "output/docs.md"
    assert checkpoint.last_scraped is not None


def test_create_checkpoint_metadata() -> None:
    """Test checkpoint metadata factory function."""
    metadata = create_checkpoint_metadata(
        config_name="docs-site",
        stats={"pages_crawled": 100, "pages_failed": 2},
    )

    assert metadata.config_name == "docs-site"
    assert metadata.version == 1
    assert metadata.stats["pages_crawled"] == 100
    assert metadata.stats["pages_failed"] == 2
    assert metadata.created_at is not None
    assert metadata.last_updated is not None
