"""Integration tests for redirect loop fix using final URL."""

import pytest

from sus.rules import LinkExtractor


@pytest.mark.asyncio
async def test_link_extraction_respects_base_tag() -> None:
    """Verify link extraction respects HTML <base> tags."""
    html = """<html>
        <head><base href="https://cdn.example.com/"></head>
        <body><a href="assets/style.css">Stylesheet</a></body>
    </html>"""

    extractor = LinkExtractor(selectors=["a[href]"])
    links = extractor.extract_links(html, "https://example.com/page")

    # Link should be resolved using base tag, not fallback URL
    assert "https://cdn.example.com/assets/style.css" in links
    assert "https://example.com/assets/style.css" not in links


@pytest.mark.asyncio
async def test_link_extraction_uses_different_base_url() -> None:
    """Verify that link extraction uses the provided base URL correctly."""
    html = '<html><body><a href="overview">Overview</a></body></html>'

    extractor = LinkExtractor(selectors=["a[href]"])

    # Simulate what happens after a redirect:
    # requested URL != final URL, and we should use final URL as base
    final_url = "https://platform.claude.com/docs/en/agent-sdk/"

    links = extractor.extract_links(html, final_url)

    # Link should be resolved relative to final_url, not requested_url
    assert "https://platform.claude.com/docs/en/agent-sdk/overview" in links
    assert "https://docs.claude.com/en/api/agent-sdk/overview" not in links


@pytest.mark.asyncio
async def test_link_extraction_with_base_tag_after_redirect() -> None:
    """Verify base tag works correctly when combined with URL after redirect."""
    html = """<html>
        <head><base href="/cdn/"></head>
        <body><a href="assets/style.css">Stylesheet</a></body>
    </html>"""

    extractor = LinkExtractor(selectors=["a[href]"])

    # Base tag is relative, should be resolved against final_url
    final_url = "https://platform.claude.com/docs/en/agent-sdk/"

    links = extractor.extract_links(html, final_url)

    # Relative base tag "/cdn/" resolved against final_url
    assert "https://platform.claude.com/cdn/assets/style.css" in links


@pytest.mark.asyncio
async def test_final_url_field_added_to_crawl_result() -> None:
    """Verify that CrawlResult includes final_url field."""
    from sus.crawler import CrawlResult

    # Test that final_url is a required field
    result = CrawlResult(
        url="https://example.com/original",
        final_url="https://example.com/final",
        html="<html></html>",
        status_code=200,
        content_type="text/html",
        links=[],
        assets=[],
    )

    assert result.url == "https://example.com/original"
    assert result.final_url == "https://example.com/final"
