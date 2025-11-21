"""Syntax highlighting plugin using Pygments.

Detects fenced code blocks with language tags and applies syntax highlighting
using Pygments HTML formatter, then converts to styled markdown.
"""

import re
from typing import Any

from sus.plugins import Plugin, PluginHook

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound

    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False


class CodeHighlightPlugin(Plugin):
    """Syntax highlighting plugin.

    Applies Pygments syntax highlighting to fenced code blocks in markdown.
    Preserves original code blocks if Pygments is not installed or if
    language is not recognized.

    Settings:
        theme: Pygments theme name (default: "monokai")
        add_line_numbers: Add line numbers to code blocks (default: False)
        inline_styles: Use inline CSS styles (default: True)
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        """Initialize code highlight plugin.

        Args:
            settings: Plugin settings

        Raises:
            ImportError: If Pygments is not installed
        """
        super().__init__(settings)

        if not PYGMENTS_AVAILABLE:
            raise ImportError("Pygments is not installed. Install with: uv sync --group plugins")

        self.theme = self.settings.get("theme", "monokai")
        self.add_line_numbers = self.settings.get("add_line_numbers", False)
        self.inline_styles = self.settings.get("inline_styles", True)

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "code_highlight"

    @property
    def hooks(self) -> list[PluginHook]:
        """Subscribe to POST_CONVERT hook."""
        return [PluginHook.POST_CONVERT]

    def on_post_convert(self, url: str, markdown: str) -> str:
        """Apply syntax highlighting to code blocks.

        Args:
            url: Page URL
            markdown: Markdown content with code blocks

        Returns:
            Markdown with syntax-highlighted code blocks
        """
        pattern = r"```(\w+)\n(.*?)```"

        def highlight_code(match: re.Match[str]) -> str:
            """Highlight a single code block.

            Args:
                match: Regex match for code block

            Returns:
                Highlighted code block or original if highlighting fails
            """
            language = match.group(1)
            code = match.group(2)

            try:
                lexer = get_lexer_by_name(language)
                formatter = HtmlFormatter(
                    style=self.theme,
                    linenos="inline" if self.add_line_numbers else False,
                    noclasses=self.inline_styles,
                    nowrap=False,
                )
                highlighted = highlight(code, lexer, formatter)

                return f"```{language}\n{highlighted}\n```"

            except ClassNotFound:
                return match.group(0)
            except Exception:
                return match.group(0)

        return re.sub(pattern, highlight_code, markdown, flags=re.DOTALL)


__all__ = ["CodeHighlightPlugin"]
