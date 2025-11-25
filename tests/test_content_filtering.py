"""Unit tests for Content Filtering in ContentConverter."""

from unittest.mock import patch

import pytest

from sus.config import ContentFilteringConfig, MarkdownConfig
from sus.converter import ContentConverter
from sus.exceptions import ConversionError


def test_content_filtering_disabled() -> None:
    """Test content filtering when disabled."""
    config = MarkdownConfig(content_filtering=ContentFilteringConfig(enabled=False))
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <nav>Navigation</nav>
            <main>Main content</main>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # All content should be present (no filtering)
    assert "Navigation" in result
    assert "Main content" in result
    assert "Footer" in result


def test_content_filtering_remove_selectors() -> None:
    """Test removing elements with CSS selectors (blacklist approach)."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["nav", "footer", ".ads"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <nav>Navigation</nav>
            <main>Main content</main>
            <div class="ads">Advertisement</div>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # Removed elements should not be present
    assert "Navigation" not in result
    assert "Footer" not in result
    assert "Advertisement" not in result

    # Main content should remain
    assert "Main content" in result


def test_content_filtering_keep_selectors() -> None:
    """Test keeping only specified elements (whitelist approach)."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            keep_selectors=["main", ".content"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <nav>Navigation</nav>
            <main>Main content</main>
            <div class="content">Additional content</div>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # Only kept elements should be present
    assert "Main content" in result
    assert "Additional content" in result

    # Other elements should be removed
    assert "Navigation" not in result
    assert "Footer" not in result


def test_content_filtering_keep_selectors_precedence() -> None:
    """Test keep_selectors takes precedence over remove_selectors."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            keep_selectors=["main"],
            remove_selectors=["nav", "footer"],  # Should be ignored
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <nav>Navigation</nav>
            <main>Main content</main>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # Only main should be present (keep_selectors wins)
    assert "Main content" in result
    assert "Navigation" not in result
    assert "Footer" not in result


def test_content_filtering_multiple_remove_selectors() -> None:
    """Test multiple remove selectors."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["nav", "aside", "footer", "#ads", ".sidebar"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <nav>Navigation</nav>
            <aside>Sidebar</aside>
            <main>Main content</main>
            <div id="ads">Advertisements</div>
            <div class="sidebar">Right sidebar</div>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # All removed elements should be gone
    assert "Navigation" not in result
    assert "Sidebar" not in result
    assert "Advertisements" not in result
    assert "Right sidebar" not in result
    assert "Footer" not in result

    # Main content should remain
    assert "Main content" in result


def test_content_filtering_complex_selectors() -> None:
    """Test complex CSS selectors."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["div.ad", "section#comments", "p.meta"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <article>
                <h1>Article Title</h1>
                <p class="meta">Posted on 2025-01-01</p>
                <p>Article content here.</p>
                <div class="ad">Advertisement banner</div>
            </article>
            <section id="comments">
                <h2>Comments</h2>
                <p>Comment 1</p>
            </section>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # Removed elements should be gone
    assert "Posted on 2025-01-01" not in result
    assert "Advertisement banner" not in result
    assert "Comments" not in result
    assert "Comment 1" not in result

    # Article content should remain
    assert "Article Title" in result
    assert "Article content here" in result


def test_content_filtering_keep_selectors_no_match() -> None:
    """Test keep_selectors with no matching elements returns empty body."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            keep_selectors=[".nonexistent"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <main>Main content</main>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # No content should be present (no matching selectors)
    assert "Main content" not in result


def test_content_filtering_preserve_nested_structure() -> None:
    """Test filtering preserves nested HTML structure."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            keep_selectors=["article"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <nav>Navigation</nav>
            <article>
                <h1>Title</h1>
                <p>First paragraph with <strong>bold text</strong>.</p>
                <ul>
                    <li>List item 1</li>
                    <li>List item 2</li>
                </ul>
            </article>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # Check nested structure is preserved
    assert "Title" in result
    assert "First paragraph" in result
    assert "bold text" in result
    assert "List item 1" in result
    assert "List item 2" in result

    # Filtered elements should be gone
    assert "Navigation" not in result
    assert "Footer" not in result


def test_content_filtering_malformed_html_graceful_fallback() -> None:
    """Test graceful fallback for malformed HTML."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["nav"],
        )
    )
    converter = ContentConverter(config)

    # Malformed HTML (unclosed tags, invalid structure)
    html = "<html><body><nav>Nav<main>Content</body>"

    # Should not raise error, should return some content
    result = converter.convert(html, "https://example.com", "Test")

    # Should contain something (fallback to original or partial conversion)
    assert len(result) > 0


def test_content_filtering_empty_html() -> None:
    """Test filtering on empty HTML raises ConversionError.

    Empty HTML cannot be safely processed since we cannot verify
    script/style removal occurred successfully.
    """
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["nav"],
        )
    )
    converter = ContentConverter(config)

    html = ""

    # Empty HTML should raise ConversionError (cannot safely process)
    with pytest.raises(ConversionError):
        converter.convert(html, "https://example.com", "Test")


def test_content_filtering_with_frontmatter() -> None:
    """Test filtering works correctly with frontmatter enabled."""
    config = MarkdownConfig(
        add_frontmatter=True,
        frontmatter_fields=["title", "url"],
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["nav", "footer"],
        ),
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <nav>Navigation</nav>
            <main>Main content</main>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com/test", "Test Page")

    # Check frontmatter is present
    assert result.startswith("---\n")
    assert "title: Test Page" in result
    assert "url: https://example.com/test" in result

    # Check filtering worked
    assert "Main content" in result
    assert "Navigation" not in result
    assert "Footer" not in result


def test_content_filtering_real_world_docs_page() -> None:
    """Test filtering on realistic documentation page structure."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            keep_selectors=["article.documentation"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <head><title>API Docs</title></head>
        <body>
            <header class="site-header">
                <nav>
                    <a href="/">Home</a>
                    <a href="/docs">Docs</a>
                </nav>
            </header>
            <aside class="sidebar">
                <ul>
                    <li><a href="/docs/intro">Introduction</a></li>
                    <li><a href="/docs/api">API Reference</a></li>
                </ul>
            </aside>
            <article class="documentation">
                <h1>API Reference</h1>
                <p>This is the API documentation.</p>
                <h2>Methods</h2>
                <ul>
                    <li><code>get()</code> - Fetch data</li>
                    <li><code>post()</code> - Create data</li>
                </ul>
            </article>
            <footer>
                <p>&copy; 2025 Example Inc.</p>
            </footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com/docs/api", "API Docs")

    # Only documentation article should be present
    assert "API Reference" in result
    assert "This is the API documentation" in result
    assert "get()" in result
    assert "post()" in result

    # All other elements should be filtered
    assert "Home" not in result
    assert "Introduction" not in result
    assert "2025 Example Inc" not in result


def test_content_filtering_id_and_class_selectors() -> None:
    """Test filtering with ID and class selectors."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["#header", ".advertisement", "#footer"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <div id="header">Header content</div>
            <main>
                <h1>Article</h1>
                <p>Paragraph 1</p>
                <div class="advertisement">Ad banner</div>
                <p>Paragraph 2</p>
            </main>
            <div id="footer">Footer content</div>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # Main content should remain
    assert "Article" in result
    assert "Paragraph 1" in result
    assert "Paragraph 2" in result

    # Filtered elements should be gone
    assert "Header content" not in result
    assert "Ad banner" not in result
    assert "Footer content" not in result


def test_content_filtering_descendant_selectors() -> None:
    """Test filtering with descendant selectors."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["aside p", "footer a"],
        )
    )
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <main>
                <p>Main paragraph</p>
                <a href="/link">Main link</a>
            </main>
            <aside>
                <p>Aside paragraph</p>
                <a href="/aside-link">Aside link</a>
            </aside>
            <footer>
                <p>Footer paragraph</p>
                <a href="/footer-link">Footer link</a>
            </footer>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # Main content should remain
    assert "Main paragraph" in result
    assert "Main link" in result

    # Filtered descendant elements should be gone
    assert "Aside paragraph" not in result
    assert "Footer link" not in result

    # Parent elements might remain (only descendants removed)
    # Note: This behavior depends on lxml's remove() implementation


def test_script_removal_removes_javascript_content() -> None:
    """Test that script tags and their content are removed from HTML."""
    config = MarkdownConfig()
    converter = ContentConverter(config)

    html = """
    <html>
        <head>
            <script>
                const API_KEY = "secret-key-12345";
                fetch('https://example.com/api');
            </script>
        </head>
        <body>
            <h1>Content</h1>
            <script type="text/javascript">
                document.write("injected");
            </script>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # JavaScript content should NOT appear in markdown
    assert "API_KEY" not in result
    assert "secret-key" not in result
    assert "fetch" not in result
    assert "injected" not in result
    assert "document.write" not in result

    # Real content should remain
    assert "Content" in result


def test_style_removal_removes_css_content() -> None:
    """Test that style tags and their content are removed from HTML."""
    config = MarkdownConfig()
    converter = ContentConverter(config)

    html = """
    <html>
        <head>
            <style>
                body { background: red; }
                .secret { display: none; }
            </style>
        </head>
        <body>
            <h1>Content</h1>
            <style>
                h1 { color: blue; }
            </style>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # CSS content should NOT appear in markdown
    assert "background: red" not in result
    assert ".secret" not in result
    assert "color: blue" not in result

    # Real content should remain
    assert "Content" in result


def test_script_removal_failure_raises_conversion_error() -> None:
    """Test that script removal failure raises ConversionError (security critical).

    This is a CRITICAL security test. If script removal fails, we must NOT
    return the original HTML because it could contain API keys, secrets,
    or tracking code that would leak into the markdown output.
    """
    config = MarkdownConfig()
    converter = ContentConverter(config)

    # Mock lxml.html.fromstring to raise an exception
    with patch("sus.converter.lxml_html.fromstring") as mock_fromstring:
        mock_fromstring.side_effect = Exception("Parsing failed")

        # Should raise ConversionError, NOT return original HTML
        with pytest.raises(ConversionError) as exc_info:
            converter._remove_scripts_and_styles("<html><script>secret</script></html>")

        assert "Script/style removal failed" in str(exc_info.value)


def test_noscript_removal() -> None:
    """Test that noscript tags are removed from HTML."""
    config = MarkdownConfig()
    converter = ContentConverter(config)

    html = """
    <html>
        <body>
            <h1>Content</h1>
            <noscript>
                <p>JavaScript is required for this site.</p>
                <img src="tracking.gif" alt="tracking pixel">
            </noscript>
        </body>
    </html>
    """

    result = converter.convert(html, "https://example.com", "Test")

    # noscript content should NOT appear in markdown
    assert "JavaScript is required" not in result
    assert "tracking" not in result

    # Real content should remain
    assert "Content" in result
