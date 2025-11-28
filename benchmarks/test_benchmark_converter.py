"""Benchmarks for HTML to Markdown conversion.

Tests performance of:
- ContentConverter.convert() - HTML to Markdown conversion
- ContentConverter.convert_with_frontmatter() - With YAML frontmatter
- HtmlToMarkdownBackend (Rust-powered) raw conversion
"""

from pytest_benchmark.fixture import BenchmarkFixture

from sus.config import MarkdownConfig
from sus.converter import (
    ContentConverter,
    HtmlToMarkdownBackend,
)


class TestContentConverterBenchmarks:
    """Benchmark ContentConverter methods."""

    def test_convert_small_html(
        self,
        benchmark: BenchmarkFixture,
        small_html: str,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark small (~1KB) page conversion."""
        converter = ContentConverter(markdown_config)
        result = benchmark(converter.convert, small_html, "http://example.com/page")
        assert "Title" in result
        assert len(result) > 0

    def test_convert_medium_html(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark medium (~10KB) documentation page conversion."""
        converter = ContentConverter(markdown_config)
        result = benchmark(converter.convert, medium_html, "http://example.com/docs")
        assert "Documentation" in result
        assert len(result) > 1000

    def test_convert_large_html(
        self,
        benchmark: BenchmarkFixture,
        large_html: str,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark large (~100KB) documentation page conversion."""
        converter = ContentConverter(markdown_config)
        result = benchmark(converter.convert, large_html, "http://example.com/docs/large")
        assert len(result) > 10000

    def test_convert_with_code_blocks(
        self,
        benchmark: BenchmarkFixture,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark conversion with multiple code blocks."""
        converter = ContentConverter(markdown_config)
        html = "\n".join(
            f"""<pre><code class="language-python">
def function_{i}(x: int) -> int:
    '''Function {i} docstring.'''
    return x * {i}
</code></pre>"""
            for i in range(20)
        )
        html = f"<html><body>{html}</body></html>"
        result = benchmark(converter.convert, html, "http://example.com/code")
        assert "```python" in result or "def function_" in result

    def test_convert_with_tables(
        self,
        benchmark: BenchmarkFixture,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark conversion with tables."""
        converter = ContentConverter(markdown_config)
        tables = "\n".join(
            f"""<table>
            <thead><tr><th>Col A</th><th>Col B</th><th>Col C</th></tr></thead>
            <tbody>
                <tr><td>Row {i}.1</td><td>Value A</td><td>100</td></tr>
                <tr><td>Row {i}.2</td><td>Value B</td><td>200</td></tr>
            </tbody>
        </table>"""
            for i in range(10)
        )
        html = f"<html><body>{tables}</body></html>"
        result = benchmark(converter.convert, html, "http://example.com/tables")
        assert "|" in result  # Markdown table syntax

    def test_convert_with_images(
        self,
        benchmark: BenchmarkFixture,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark conversion with images."""
        converter = ContentConverter(markdown_config)
        images = "\n".join(
            f'<img src="/img/image{i}.png" alt="Image {i} description">' for i in range(50)
        )
        html = f"<html><body>{images}</body></html>"
        result = benchmark(converter.convert, html, "http://example.com/images")
        assert "![" in result  # Markdown image syntax

    def test_convert_with_nested_lists(
        self,
        benchmark: BenchmarkFixture,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark conversion with deeply nested lists."""
        converter = ContentConverter(markdown_config)
        html = (
            """<html><body>
        <ul>
            <li>Level 1
                <ul>
                    <li>Level 2
                        <ul>
                            <li>Level 3
                                <ul>
                                    <li>Level 4 item 1</li>
                                    <li>Level 4 item 2</li>
                                </ul>
                            </li>
                        </ul>
                    </li>
                </ul>
            </li>
        </ul>
        </body></html>"""
            * 10
        )
        result = benchmark(converter.convert, html, "http://example.com/lists")
        assert "Level" in result

    def test_convert_batch_10(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark converting 10 pages (typical batch)."""
        converter = ContentConverter(markdown_config)
        pages = [(medium_html, f"http://example.com/page{i}") for i in range(10)]

        def convert_batch() -> list[str]:
            return [converter.convert(html, url) for html, url in pages]

        results = benchmark(convert_batch)
        assert len(results) == 10
        assert all(len(r) > 0 for r in results)


class TestFrontmatterBenchmarks:
    """Benchmark frontmatter generation."""

    def test_frontmatter_small(
        self,
        benchmark: BenchmarkFixture,
        small_html: str,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark conversion with frontmatter for small page."""
        converter = ContentConverter(markdown_config)
        metadata = {
            "scraped_at": "2024-01-15T10:30:00Z",
        }
        result = benchmark(
            converter.convert,
            small_html,
            "http://example.com/page",
            None,  # title extracted from HTML
            metadata,
        )
        assert "---" in result
        assert "title:" in result

    def test_frontmatter_medium(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark conversion with frontmatter for medium page."""
        converter = ContentConverter(markdown_config)
        metadata = {
            "scraped_at": "2024-01-15T10:30:00Z",
            "description": "A documentation page with extensive content",
        }
        result = benchmark(
            converter.convert,
            medium_html,
            "http://example.com/docs",
            None,  # title extracted from HTML
            metadata,
        )
        assert "---" in result
        assert len(result) > 1000

    def test_frontmatter_batch(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
        markdown_config: MarkdownConfig,
    ) -> None:
        """Benchmark conversion with frontmatter for batch of 10 pages."""
        converter = ContentConverter(markdown_config)
        pages = [
            (
                medium_html,
                f"http://example.com/page{i}",
                {
                    "scraped_at": "2024-01-15T10:30:00Z",
                },
            )
            for i in range(10)
        ]

        def convert_batch() -> list[str]:
            return [converter.convert(html, url, None, meta) for html, url, meta in pages]

        results = benchmark(convert_batch)
        assert len(results) == 10
        assert all("---" in r for r in results)


class TestBackendBenchmarks:
    """Benchmark raw html-to-markdown backend performance."""

    def test_backend_medium(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
    ) -> None:
        """Benchmark html-to-markdown backend on medium HTML (~10KB)."""
        backend = HtmlToMarkdownBackend()
        result = benchmark(backend.convert, medium_html)
        assert len(result) > 100

    def test_backend_large(
        self,
        benchmark: BenchmarkFixture,
        large_html: str,
    ) -> None:
        """Benchmark html-to-markdown backend on large HTML (~100KB)."""
        backend = HtmlToMarkdownBackend()
        result = benchmark(backend.convert, large_html)
        assert len(result) > 1000
