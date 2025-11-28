"""Tests for LinkExtractor base tag detection and link extraction."""

from sus.rules import LinkExtractor


def test_detect_base_url_with_absolute_base() -> None:
    """Test base tag detection with absolute URL."""
    html = '<html><head><base href="https://example.com/docs/"></head></html>'
    result = LinkExtractor.detect_base_url(html, "https://example.com/")
    assert result == "https://example.com/docs/"


def test_detect_base_url_with_relative_base() -> None:
    """Test base tag detection with relative URL."""
    html = '<html><head><base href="/docs/"></head></html>'
    result = LinkExtractor.detect_base_url(html, "https://example.com/")
    assert result == "https://example.com/docs/"


def test_detect_base_url_no_base_tag() -> None:
    """Test fallback when no base tag present."""
    html = "<html><head></head></html>"
    result = LinkExtractor.detect_base_url(html, "https://example.com/fallback")
    assert result == "https://example.com/fallback"


def test_detect_base_url_empty_base() -> None:
    """Test fallback when base tag has empty href."""
    html = '<html><head><base href=""></head></html>'
    result = LinkExtractor.detect_base_url(html, "https://example.com/fallback")
    assert result == "https://example.com/fallback"


def test_detect_base_url_multiple_bases() -> None:
    """Test that first base tag is used when multiple exist (per HTML spec)."""
    html = """<html><head>
        <base href="https://first.com/">
        <base href="https://second.com/">
    </head></html>"""
    result = LinkExtractor.detect_base_url(html, "https://example.com/")
    assert result == "https://first.com/"


def test_detect_base_url_invalid_html() -> None:
    """Test fallback when HTML is malformed."""
    html = "<invalid><<>>"
    result = LinkExtractor.detect_base_url(html, "https://example.com/fallback")
    assert result == "https://example.com/fallback"


def test_detect_base_url_empty_string() -> None:
    """Test fallback with empty HTML."""
    result = LinkExtractor.detect_base_url("", "https://example.com/fallback")
    assert result == "https://example.com/fallback"


def test_detect_base_url_whitespace_only() -> None:
    """Test fallback with whitespace-only HTML."""
    result = LinkExtractor.detect_base_url("   \n  ", "https://example.com/fallback")
    assert result == "https://example.com/fallback"


def test_extract_links_uses_base_tag() -> None:
    """Test that link extraction respects base tags."""
    html = """<html>
        <head><base href="https://cdn.example.com/"></head>
        <body><a href="page">Page</a></body>
    </html>"""

    extractor = LinkExtractor(selectors=["a[href]"])
    links = extractor.extract_links(html, "https://example.com/")

    assert "https://cdn.example.com/page" in links


def test_extract_links_without_base_tag() -> None:
    """Test link extraction without base tag uses provided base_url."""
    html = """<html>
        <head></head>
        <body><a href="page">Page</a></body>
    </html>"""

    extractor = LinkExtractor(selectors=["a[href]"])
    links = extractor.extract_links(html, "https://example.com/")

    assert "https://example.com/page" in links


def test_extract_links_disable_base_tag() -> None:
    """Test that use_base_tag=False ignores base tags."""
    html = """<html>
        <head><base href="https://cdn.example.com/"></head>
        <body><a href="page">Page</a></body>
    </html>"""

    extractor = LinkExtractor(selectors=["a[href]"])
    links = extractor.extract_links(html, "https://example.com/", use_base_tag=False)

    # Should use provided base_url, not base tag
    assert "https://example.com/page" in links
    assert "https://cdn.example.com/page" not in links


def test_detect_base_url_with_query_and_fragment() -> None:
    """Test base tag with query params and fragments (should be preserved)."""
    html = '<html><head><base href="https://example.com/docs/?v=1#section"></head></html>'
    result = LinkExtractor.detect_base_url(html, "https://example.com/")
    assert result == "https://example.com/docs/?v=1#section"


def test_detect_base_url_relative_path() -> None:
    """Test base tag with relative path."""
    html = '<html><head><base href="docs/api/"></head></html>'
    result = LinkExtractor.detect_base_url(html, "https://example.com/v1/")
    assert result == "https://example.com/v1/docs/api/"
