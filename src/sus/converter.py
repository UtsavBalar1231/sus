"""HTML to Markdown conversion.

HTML documentation converted to Markdown with YAML frontmatter using SusMarkdownConverter
(markdownify extension with alt text preservation) and ContentConverter (orchestrator).
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any, cast

import yaml
from lxml import etree as lxml_etree
from lxml import html as lxml_html
from lxml.html import HtmlElement
from markdownify import MarkdownConverter

from sus.config import MarkdownConfig

logger = logging.getLogger(__name__)


class SusMarkdownConverter(MarkdownConverter):
    """Custom Markdown converter with better handling for docs.

    Overrides specific conversion methods for improved output quality.
    """

    def convert_img(self, el: Any, text: str, **kwargs: Any) -> str:
        """Override image conversion for better alt text handling.

        Preserves alt text when present; uses empty string when absent to
        avoid None formatting issues in markdown output.

        Args:
            el: HTML image element
            text: Converted text content (unused for images)
            **kwargs: Additional arguments from parent class (e.g., convert_as_inline)

        Returns:
            Markdown image syntax: `![alt](src)`

        Examples:
            ```
            <img src="logo.png" alt="Company Logo"> → ![Company Logo](logo.png)
            <img src="icon.png"> → ![](icon.png)
            ```
        """
        src = el.get("src", "")
        alt = el.get("alt", "")

        # Always include alt text brackets even if empty
        return f"![{alt}]({src})"

    def convert_pre(self, el: Any, text: str, **kwargs: Any) -> str:
        """Override code block conversion with language detection.

        Detects language from class attribute (e.g., class="language-python")
        and formats as fenced code blocks with language specifier.

        Args:
            el: HTML pre element
            text: Converted text content
            **kwargs: Additional arguments from parent class (e.g., parent_tags)

        Returns:
            Markdown fenced code block with language

        Examples:
            <pre><code class="language-python">print("hello")</code></pre>
            → ```python
            → print("hello")
            → ```

            <pre><code>plain text</code></pre>
            → ```
            → plain text
            → ```
        """
        # markdownify uses BeautifulSoup, so we need to use BeautifulSoup's API
        language = ""
        code_el = None
        if hasattr(el, "find"):
            code_el = el.find("code")

        if code_el is not None:
            # Look for patterns like "language-python", "lang-python", or just "python"
            classes = code_el.get("class", "")

            if isinstance(classes, list):
                classes = " ".join(classes)

            if classes:
                for class_name in classes.split():
                    # Match "language-X" or "lang-X"
                    if class_name.startswith("language-"):
                        language = class_name[9:]  # Remove "language-" prefix
                        break
                    elif class_name.startswith("lang-"):
                        language = class_name[5:]  # Remove "lang-" prefix
                        break
                    # Some sites just use the language name as class
                    elif class_name in {
                        "python",
                        "javascript",
                        "java",
                        "cpp",
                        "c",
                        "ruby",
                        "go",
                        "rust",
                        "php",
                        "swift",
                        "kotlin",
                        "typescript",
                        "bash",
                        "sh",
                        "shell",
                        "json",
                        "xml",
                        "yaml",
                        "html",
                        "css",
                        "sql",
                    }:
                        language = class_name
                        break

            if hasattr(code_el, "get_text"):
                text = code_el.get_text()
            elif hasattr(code_el, "text_content"):
                text = code_el.text_content()

        return f"\n```{language}\n{text}\n```\n"


class ContentConverter:
    """Converts HTML to Markdown with frontmatter.

    Handles HTML cleaning, markdown conversion, frontmatter generation,
    and markdown post-processing.

    Attributes:
        config: MarkdownConfig containing conversion options
        converter: SusMarkdownConverter instance for HTML→Markdown conversion
    """

    def __init__(self, config: MarkdownConfig) -> None:
        """Initialize converter with markdown config.

        Args:
            config: MarkdownConfig from SusConfig
        """
        self.config = config

        # strip: Remove non-content elements that shouldn't be in markdown
        self.converter = SusMarkdownConverter(
            heading_style="atx",  # Use # style headers
            bullets="-",  # Use - for unordered lists
            strip=["nav", "header", "footer", "aside", "script", "style"],
        )

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
        2. Convert HTML to Markdown using SusMarkdownConverter
        3. Clean markdown (remove excessive blank lines, fix spacing)
        4. Add frontmatter if configured
        5. Return final markdown
        """
        if title is None:
            title = self._extract_title(html)

        if self.config.content_filtering.enabled:
            html = self._filter_content(html)

        markdown = self.converter.convert(html)

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

    def _filter_content(self, html: str) -> str:
        """Filter HTML content using CSS selectors.

        Applies content filtering based on configuration:
        - If keep_selectors is specified, extract only those elements
        - If remove_selectors is specified, remove those elements
        - keep_selectors takes precedence over remove_selectors

        Args:
            html: HTML content to filter

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
            >>> filtered = converter._filter_content(html)
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

                result = lxml_html.tostring(new_doc, encoding="unicode")
                return cast("str", result)

            # Strategy 2: Remove specified elements (blacklist approach)
            if self.config.content_filtering.remove_selectors:
                for selector in self.config.content_filtering.remove_selectors:
                    elements = doc.cssselect(selector)
                    for elem in elements:
                        parent = elem.getparent()
                        if parent is not None:
                            parent.remove(elem)

                result = lxml_html.tostring(doc, encoding="unicode")
                return cast("str", result)

            return html

        except Exception as e:
            logger.warning(f"Content filtering failed: {e}. Returning original HTML.")
            return html
