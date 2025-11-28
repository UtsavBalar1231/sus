"""HTML to Markdown conversion.

HTML documentation converted to Markdown with YAML frontmatter using
html-to-markdown (Rust-powered, 150-210 MB/s) and ContentConverter (orchestrator).
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any, Protocol, cast, runtime_checkable

import yaml
from lxml import etree as lxml_etree
from lxml import html as lxml_html
from lxml.html import HtmlElement

from sus.config import MarkdownConfig
from sus.exceptions import ConversionError

logger = logging.getLogger(__name__)

# Check if html-to-markdown is available (Rust-powered, 60-80x faster)
try:
    from html_to_markdown import convert as html_to_md_convert

    HTML_TO_MD_AVAILABLE = True
except ImportError:
    HTML_TO_MD_AVAILABLE = False
    html_to_md_convert = None  # type: ignore[assignment]


@runtime_checkable
class MarkdownBackend(Protocol):
    """Protocol for HTML to Markdown converter backends.

    Implementations must provide a convert() method that transforms
    HTML content into Markdown format.
    """

    def convert(self, html: str) -> str:
        """Convert HTML to Markdown.

        Args:
            html: HTML content to convert

        Returns:
            Markdown content
        """
        ...


class HtmlToMarkdownBackend:
    """html-to-markdown backend (Rust-powered, high performance).

    Uses the html-to-markdown library for 60-80x faster conversion.
    CommonMark compliant output.

    Performance: 150-210 MB/s
    """

    def convert(self, html: str) -> str:
        """Convert HTML to Markdown using html-to-markdown (Rust).

        Args:
            html: HTML content to convert

        Returns:
            Markdown content

        Raises:
            RuntimeError: If html-to-markdown is not installed
        """
        if not HTML_TO_MD_AVAILABLE or html_to_md_convert is None:
            raise RuntimeError(
                "html-to-markdown package not installed. Install with: pip install html-to-markdown"
            )
        return html_to_md_convert(html)


def create_markdown_backend() -> MarkdownBackend:
    """Create the html-to-markdown backend (Rust-powered).

    Returns:
        HtmlToMarkdownBackend instance

    Raises:
        RuntimeError: If html-to-markdown is not installed

    Examples:
        >>> backend = create_markdown_backend()
        >>> markdown = backend.convert("<h1>Hello</h1>")
        >>> "# Hello" in markdown
        True
    """
    if not HTML_TO_MD_AVAILABLE:
        raise RuntimeError(
            "html-to-markdown package not installed. Install with: uv add html-to-markdown"
        )
    logger.info("Using html-to-markdown backend (Rust-powered)")
    return HtmlToMarkdownBackend()


class ContentConverter:
    """Converts HTML to Markdown with frontmatter.

    Handles HTML cleaning, markdown conversion, frontmatter generation,
    and markdown post-processing.

    Attributes:
        config: MarkdownConfig containing conversion options
        backend: HtmlToMarkdownBackend for HTML→Markdown conversion
    """

    def __init__(self, config: MarkdownConfig) -> None:
        """Initialize converter with markdown config.

        Args:
            config: MarkdownConfig from SusConfig
        """
        self.config = config
        self.backend = create_markdown_backend()

    def convert(
        self,
        html: str,
        url: str,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Convert HTML to Markdown with frontmatter.

        Args:
            html: HTML content to convert
            url: Source URL (for frontmatter)
            title: Page title (extracted from <title> or provided)
            metadata: Additional metadata for frontmatter

        Returns:
            Markdown content with YAML frontmatter

        Examples:
            >>> converter = ContentConverter(MarkdownConfig())
            >>> html = '<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>'
            >>> result = converter.convert(html, "https://example.com/test")
            >>> "# Hello" in result
            True
            >>> "title: Test" in result
            True

        Steps:
        1. Extract title from HTML if not provided (from <title> tag)
        2. Remove script/style elements completely (defensive - always done)
        3. Apply content filtering if configured
        4. Convert HTML to Markdown using SusMarkdownConverter
        5. Clean markdown (remove excessive blank lines, fix spacing)
        6. Add frontmatter if configured
        7. Return final markdown
        """
        if title is None:
            title = self._extract_title(html)

        # Always remove script/style elements completely before conversion
        # This prevents JavaScript and CSS from appearing as text in markdown
        html = self._remove_scripts_and_styles(html)

        if self.config.content_filtering.enabled:
            html = self._filter_content(html, url)

        markdown = self.backend.convert(html)

        markdown = self._clean_markdown(markdown)

        if self.config.add_frontmatter:
            markdown = self._add_frontmatter(markdown, url, title, metadata)

        return markdown

    def _extract_title(self, html: str) -> str:
        """Extract title from HTML <title> tag.

        Args:
            html: HTML content

        Returns:
            Page title or "Untitled" if not found

        Examples:
            >>> converter = ContentConverter(MarkdownConfig())
            >>> converter._extract_title("<html><head><title>My Page</title></head></html>")
            'My Page'
            >>> converter._extract_title("<html><body>No title</body></html>")
            'Untitled'
        """
        try:
            doc = lxml_html.fromstring(html)

            title_elements = cast("list[Any]", doc.xpath("//title"))
            if title_elements and isinstance(title_elements[0], HtmlElement):
                title_text = cast("str", title_elements[0].text_content().strip())
                if title_text:
                    return title_text
        except Exception:
            # If parsing fails, fall through to default
            pass

        return "Untitled"

    def _remove_scripts_and_styles(self, html: str) -> str:
        """Remove script and style elements completely from HTML.

        This is a defensive measure that ensures JavaScript and CSS code
        never appears as text in the markdown output. Removes both the
        elements and their content completely.

        Args:
            html: HTML content

        Returns:
            HTML with script/style elements removed

        Examples:
            >>> converter = ContentConverter(MarkdownConfig())
            >>> html = '<html><body><script>alert("hi")</script><p>Content</p></body></html>'
            >>> result = converter._remove_scripts_and_styles(html)
            >>> 'alert' not in result
            True
            >>> 'Content' in result
            True
        """
        try:
            doc = lxml_html.fromstring(html)

            # Remove all script elements (including inline and external)
            # Using cssselect instead of xpath for better type safety
            for script in doc.cssselect("script"):
                parent = script.getparent()
                if parent is not None:
                    parent.remove(script)

            # Remove all style elements (including inline CSS)
            for style in doc.cssselect("style"):
                parent = style.getparent()
                if parent is not None:
                    parent.remove(style)

            # Remove noscript elements as well (no value in markdown)
            for noscript in doc.cssselect("noscript"):
                parent = noscript.getparent()
                if parent is not None:
                    parent.remove(noscript)

            result = lxml_html.tostring(doc, encoding="unicode")
            return cast("str", result)

        except Exception as e:
            # CRITICAL: Never return original HTML - it may contain scripts with
            # API keys, secrets, or tracking code that would leak into markdown
            logger.error(f"Failed to remove script/style elements: {e}")
            raise ConversionError(
                f"Script/style removal failed: {e}. "
                "Cannot safely convert HTML to markdown without removing scripts."
            ) from e

    def _clean_markdown(self, markdown: str) -> str:
        """Clean markdown output.

        - Remove excessive blank lines (max 2 consecutive)
        - Remove trailing whitespace from lines
        - Ensure single newline at end of file

        Args:
            markdown: Raw markdown

        Returns:
            Cleaned markdown

        Examples:
            >>> converter = ContentConverter(MarkdownConfig())
            >>> converter._clean_markdown("# Title\\n\\n\\n\\n\\nContent")
            '# Title\\n\\nContent\\n'
            >>> converter._clean_markdown("Line with spaces   \\n")
            'Line with spaces\\n'
        """
        lines = [line.rstrip() for line in markdown.splitlines()]

        markdown = "\n".join(lines)

        # This preserves paragraph breaks but removes excessive spacing
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        markdown = markdown.rstrip("\n") + "\n"

        return markdown

    def _add_frontmatter(
        self,
        markdown: str,
        url: str,
        title: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add YAML frontmatter to markdown.

        Args:
            markdown: Markdown content
            url: Source URL
            title: Page title
            metadata: Additional metadata fields

        Returns:
            Markdown with frontmatter

        Examples:
            >>> converter = ContentConverter(MarkdownConfig())
            >>> result = converter._add_frontmatter("# Content", "https://example.com", "Test")
            >>> result.startswith("---\\n")
            True
            >>> "title: Test" in result
            True
            >>> "url: https://example.com" in result
            True

        Frontmatter format:
        ---
        title: Page Title
        url: https://example.com/page
        scraped_at: 2025-01-14T12:00:00Z
        ---

        [markdown content]
        """
        frontmatter_dict: dict[str, Any] = {}

        if "title" in self.config.frontmatter_fields:
            frontmatter_dict["title"] = title

        if "url" in self.config.frontmatter_fields:
            frontmatter_dict["url"] = url

        if "scraped_at" in self.config.frontmatter_fields:
            # Use UTC time in ISO 8601 format
            frontmatter_dict["scraped_at"] = datetime.now(UTC).isoformat()

        if metadata:
            for key, value in metadata.items():
                if key in self.config.frontmatter_fields:
                    frontmatter_dict[key] = value

        # Sort fields alphabetically for deterministic output
        frontmatter_dict = dict(sorted(frontmatter_dict.items()))

        # default_flow_style=False ensures block style (not inline)
        # allow_unicode=True preserves unicode characters
        # sort_keys=False because we already sorted above
        yaml_content = yaml.dump(
            frontmatter_dict,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        return f"---\n{yaml_content}---\n\n{markdown}"

    def _filter_content(self, html: str, url: str) -> str:
        """Filter HTML content using CSS selectors.

        Applies content filtering based on configuration:
        - If keep_selectors is specified, extract only those elements
        - If remove_selectors is specified, remove those elements from the result
        - Both can be used together: keep_selectors first, then remove_selectors

        Args:
            html: HTML content to filter
            url: Source URL (for error reporting)

        Returns:
            Filtered HTML content

        Examples:
            >>> config = MarkdownConfig(content_filtering=ContentFilteringConfig(
            ...     enabled=True,
            ...     remove_selectors=["nav", "footer"]
            ... ))
            >>> converter = ContentConverter(config)
            >>> html = (
            ...     "<html><body><nav>Nav</nav><main>Content</main>"
            ...     "<footer>Footer</footer></body></html>"
            ... )
            >>> filtered = converter._filter_content(html, "https://example.com")
            >>> "Nav" not in filtered
            True
            >>> "Content" in filtered
            True
            >>> "Footer" not in filtered
            True
        """
        try:
            doc = lxml_html.fromstring(html)

            # Strategy 1: Keep only specified elements (whitelist approach)
            if self.config.content_filtering.keep_selectors:
                kept_elements = []
                seen_ids = set()
                for selector in self.config.content_filtering.keep_selectors:
                    elements = doc.cssselect(selector)
                    for elem in elements:
                        elem_id = id(elem)
                        if elem_id not in seen_ids:
                            seen_ids.add(elem_id)
                            kept_elements.append(elem)

                if not kept_elements:
                    # No elements matched - return empty doc
                    return "<html><body></body></html>"

                # Preserve document order by using tree iteration
                kept_elements_set = set(kept_elements)
                kept_elements = [elem for elem in doc.iter() if elem in kept_elements_set]

                new_doc = lxml_html.Element("html")
                body = lxml_etree.SubElement(new_doc, "body")
                for elem in kept_elements:
                    body.append(elem)

                # Update doc to the filtered version for potential remove_selectors
                doc = new_doc

            # Strategy 2: Remove specified elements (blacklist approach)
            # This now works on the keep_selectors result if both are specified
            if self.config.content_filtering.remove_selectors:
                for selector in self.config.content_filtering.remove_selectors:
                    elements = doc.cssselect(selector)
                    for elem in elements:
                        parent = elem.getparent()
                        if parent is not None:
                            parent.remove(elem)

            # Return the filtered document (or original if no filters applied)
            if (
                self.config.content_filtering.keep_selectors
                or self.config.content_filtering.remove_selectors
            ):
                result = lxml_html.tostring(doc, encoding="unicode")
                return cast("str", result)

            return html

        except Exception as e:
            logger.warning(f"Content filtering failed for {url}: {e}. Returning original HTML.")
            return html
