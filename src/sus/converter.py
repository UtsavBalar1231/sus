"""HTML to Markdown conversion.

Converts HTML documentation to Markdown with YAML frontmatter. Provides SusMarkdownConverter
(custom markdownify with alt text preservation) and ContentConverter (high-level orchestrator).
"""

import re
from datetime import UTC, datetime
from typing import Any, cast

import yaml
from lxml import html as lxml_html
from lxml.html import HtmlElement
from markdownify import MarkdownConverter

from sus.config import MarkdownConfig


class SusMarkdownConverter(MarkdownConverter):  # type: ignore[misc]
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
            Markdown image syntax: ![alt](src)

        Examples:
            <img src="logo.png" alt="Company Logo"> → ![Company Logo](logo.png)
            <img src="icon.png"> → ![](icon.png)
        """
        # Extract attributes
        src = el.get("src", "")
        alt = el.get("alt", "")

        # Build markdown image syntax
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
        # Check if pre contains a code element with language class
        # markdownify uses BeautifulSoup, so we need to use BeautifulSoup's API
        language = ""

        # Try to find code element - el might be BeautifulSoup Tag
        code_el = None
        if hasattr(el, "find"):
            code_el = el.find("code")

        if code_el is not None:
            # Extract language from class attribute
            # Look for patterns like "language-python", "lang-python", or just "python"
            classes = code_el.get("class", "")

            # Handle both string and list formats for class attribute
            if isinstance(classes, list):
                classes = " ".join(classes)

            if classes:
                # Try to extract language from class names
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

            # Get text content from code element
            if hasattr(code_el, "get_text"):
                text = code_el.get_text()
            elif hasattr(code_el, "text_content"):
                text = code_el.text_content()

        # Return fenced code block
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

        # Configure markdownify converter with our custom class
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
        # Step 1: Extract title if not provided
        if title is None:
            title = self._extract_title(html)

        # Step 2: Convert HTML to Markdown
        markdown = self.converter.convert(html)

        # Step 3: Clean markdown
        markdown = self._clean_markdown(markdown)

        # Step 4: Add frontmatter if configured
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
            # Parse HTML
            doc = lxml_html.fromstring(html)

            # Find title element
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
        # Remove trailing whitespace from each line
        lines = [line.rstrip() for line in markdown.splitlines()]

        # Join lines back and handle excessive blank lines
        markdown = "\n".join(lines)

        # Replace 3+ consecutive newlines with exactly 2 newlines
        # This preserves paragraph breaks but removes excessive spacing
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        # Ensure file ends with single newline
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
        # Build frontmatter dictionary with configured fields
        frontmatter_dict: dict[str, Any] = {}

        # Add standard fields if they're in configured fields
        if "title" in self.config.frontmatter_fields:
            frontmatter_dict["title"] = title

        if "url" in self.config.frontmatter_fields:
            frontmatter_dict["url"] = url

        if "scraped_at" in self.config.frontmatter_fields:
            # Use UTC time in ISO 8601 format
            frontmatter_dict["scraped_at"] = datetime.now(UTC).isoformat()

        # Merge with additional metadata if provided
        if metadata:
            for key, value in metadata.items():
                if key in self.config.frontmatter_fields:
                    frontmatter_dict[key] = value

        # Sort fields alphabetically for deterministic output
        frontmatter_dict = dict(sorted(frontmatter_dict.items()))

        # Serialize to YAML
        # default_flow_style=False ensures block style (not inline)
        # allow_unicode=True preserves unicode characters
        # sort_keys=False because we already sorted above
        yaml_content = yaml.dump(
            frontmatter_dict,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        # Build final markdown with frontmatter
        return f"---\n{yaml_content}---\n\n{markdown}"
