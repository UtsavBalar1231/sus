"""Unit tests for Content Filtering in ContentConverter."""

from sus.config import ContentFilteringConfig, MarkdownConfig
from sus.converter import ContentConverter


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
    """Test filtering on empty HTML."""
    config = MarkdownConfig(
        content_filtering=ContentFilteringConfig(
            enabled=True,
            remove_selectors=["nav"],
        )
    )
    converter = ContentConverter(config)

    html = ""

    # Should not raise error
    result = converter.convert(html, "https://example.com", "Test")

    # Should handle gracefully
    assert isinstance(result, str)


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
