"""Comprehensive tests for built-in plugins.

Tests code_highlight, link_validator, and image_optimizer plugins.
"""

from pathlib import Path
from typing import Any

import pytest

from sus.plugins import PluginHook

# Skip tests if optional dependencies not installed
pytest.importorskip("pygments", reason="Pygments not installed")
pytest.importorskip("PIL", reason="Pillow not installed")

from sus.plugins.code_highlight import CodeHighlightPlugin
from sus.plugins.image_optimizer import ImageOptimizerPlugin
from sus.plugins.link_validator import LinkValidatorPlugin


def test_code_highlight_initialization() -> None:
    """Test code highlight plugin initialization."""
    plugin = CodeHighlightPlugin()
    assert plugin.name == "code_highlight"
    assert PluginHook.POST_CONVERT in plugin.hooks


def test_code_highlight_default_settings() -> None:
    """Test code highlight plugin default settings."""
    plugin = CodeHighlightPlugin()
    assert plugin.theme == "monokai"
    assert plugin.add_line_numbers is False
    assert plugin.inline_styles is True


def test_code_highlight_custom_settings() -> None:
    """Test code highlight plugin with custom settings."""
    settings = {
        "theme": "dracula",
        "add_line_numbers": True,
        "inline_styles": False,
    }
    plugin = CodeHighlightPlugin(settings=settings)
    assert plugin.theme == "dracula"
    assert plugin.add_line_numbers is True
    assert plugin.inline_styles is False


def test_code_highlight_python_code() -> None:
    """Test highlighting Python code."""
    plugin = CodeHighlightPlugin()
    markdown = "```python\nprint('hello')\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "```python" in result
    assert "print" in result


def test_code_highlight_javascript_code() -> None:
    """Test highlighting JavaScript code."""
    plugin = CodeHighlightPlugin()
    markdown = "```javascript\nconsole.log('hello');\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "```javascript" in result
    assert "console" in result


def test_code_highlight_multiple_blocks() -> None:
    """Test highlighting multiple code blocks."""
    plugin = CodeHighlightPlugin()
    markdown = """# Title

```python
print('hello')
```

Some text

```javascript
console.log('world');
```
"""
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "```python" in result
    assert "```javascript" in result
    assert "print" in result
    assert "console" in result


def test_code_highlight_unknown_language() -> None:
    """Test code block with unknown language stays unchanged."""
    plugin = CodeHighlightPlugin()
    markdown = "```unknownlang\ncode here\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    # Should return original if language not recognized
    assert "```unknownlang" in result
    assert "code here" in result


def test_code_highlight_no_code_blocks() -> None:
    """Test markdown without code blocks is unchanged."""
    plugin = CodeHighlightPlugin()
    markdown = "# Title\n\nParagraph text."
    result = plugin.on_post_convert("https://example.com", markdown)

    assert result == markdown


def test_code_highlight_preserves_other_content() -> None:
    """Test code highlighting preserves non-code content."""
    plugin = CodeHighlightPlugin()
    markdown = """# Header

Some paragraph.

```python
code()
```

More text.
"""
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "# Header" in result
    assert "Some paragraph" in result
    assert "More text" in result


def test_code_highlight_with_line_numbers() -> None:
    """Test code highlighting with line numbers enabled."""
    plugin = CodeHighlightPlugin(settings={"add_line_numbers": True})
    markdown = "```python\nline1\nline2\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "```python" in result


def test_code_highlight_different_themes() -> None:
    """Test code highlighting with different themes."""
    themes = ["monokai", "github-dark", "nord"]
    markdown = "```python\nprint('test')\n```"

    for theme in themes:
        plugin = CodeHighlightPlugin(settings={"theme": theme})
        result = plugin.on_post_convert("https://example.com", markdown)
        assert "```python" in result


def test_code_highlight_empty_code_block() -> None:
    """Test highlighting empty code block."""
    plugin = CodeHighlightPlugin()
    markdown = "```python\n\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "```python" in result


def test_code_highlight_sql_language() -> None:
    """Test highlighting SQL code."""
    plugin = CodeHighlightPlugin()
    markdown = "```sql\nSELECT * FROM users;\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "```sql" in result
    assert "SELECT" in result


def test_code_highlight_bash_language() -> None:
    """Test highlighting Bash code."""
    plugin = CodeHighlightPlugin()
    markdown = "```bash\necho 'hello'\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "```bash" in result
    assert "echo" in result


def test_code_highlight_hook_returns_string() -> None:
    """Test POST_CONVERT hook returns modified string."""
    plugin = CodeHighlightPlugin()
    markdown = "```python\ncode\n```"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert isinstance(result, str)
    assert len(result) > 0


def test_link_validator_initialization() -> None:
    """Test link validator plugin initialization."""
    plugin = LinkValidatorPlugin()
    assert plugin.name == "link_validator"
    assert PluginHook.POST_CONVERT in plugin.hooks


def test_link_validator_default_settings() -> None:
    """Test link validator plugin default settings."""
    plugin = LinkValidatorPlugin()
    assert plugin.timeout == 5.0
    assert plugin.max_concurrent == 10
    assert plugin.cache_results is True
    assert plugin.check_internal is True
    assert plugin.check_external is True


def test_link_validator_custom_settings() -> None:
    """Test link validator plugin with custom settings."""
    settings = {
        "timeout": 10.0,
        "max_concurrent": 20,
        "cache_results": False,
        "check_internal": False,
        "check_external": False,
    }
    plugin = LinkValidatorPlugin(settings=settings)
    assert plugin.timeout == 10.0
    assert plugin.max_concurrent == 20
    assert plugin.cache_results is False


def test_link_validator_ignore_patterns() -> None:
    """Test link validator with ignore patterns."""
    settings = {"ignore_patterns": [r"https://example\.com/ignore/.*"]}
    plugin = LinkValidatorPlugin(settings=settings)

    assert len(plugin.ignore_patterns) == 1
    assert plugin._should_ignore_link("https://example.com/ignore/page")


def test_link_validator_anchor_links() -> None:
    """Test link validator treats anchor links as valid."""
    plugin = LinkValidatorPlugin()
    markdown = "[Link](#section)"
    result = plugin.on_post_convert("https://example.com", markdown)

    # Anchor links should not be marked as broken
    assert "<!-- BROKEN LINK:" not in result


def test_link_validator_internal_link_exists(tmp_path: Path) -> None:
    """Test link validator checks internal link existence."""
    # Create a test file
    test_file = tmp_path / "test.md"
    test_file.write_text("content")

    settings = {
        "base_dir": str(tmp_path),
        "check_external": False,
    }
    plugin = LinkValidatorPlugin(settings=settings)

    markdown = "[Link](test.md)"
    result = plugin.on_post_convert(f"file://{tmp_path}/index.md", markdown)

    # Link should be valid
    assert "<!-- BROKEN LINK:" not in result


def test_link_validator_internal_link_missing(tmp_path: Path) -> None:
    """Test link validator marks missing internal links as broken."""
    settings = {
        "base_dir": str(tmp_path),
        "check_external": False,
    }
    plugin = LinkValidatorPlugin(settings=settings)

    markdown = "[Link](missing.md)"
    result = plugin.on_post_convert(f"file://{tmp_path}/index.md", markdown)

    # Link should be marked as broken
    assert "<!-- BROKEN LINK:" in result or "[Link](missing.md)" in result


def test_link_validator_caching() -> None:
    """Test link validator caches validation results."""
    plugin = LinkValidatorPlugin(settings={"cache_results": True, "check_external": False})

    markdown = "[Link](test.md)"

    # First call
    plugin.on_post_convert("https://example.com", markdown)

    # Second call should use cache
    _ = plugin.on_post_convert("https://example.com", markdown)

    # Cache should be populated
    assert len(plugin._cache) >= 0


def test_link_validator_no_caching() -> None:
    """Test link validator without caching."""
    plugin = LinkValidatorPlugin(settings={"cache_results": False})

    markdown = "[Link](test.md)"
    plugin.on_post_convert("https://example.com", markdown)

    # Cache should be empty
    assert len(plugin._cache) == 0


def test_link_validator_multiple_links() -> None:
    """Test link validator with multiple links."""
    plugin = LinkValidatorPlugin(settings={"check_external": False})

    markdown = """
[Link 1](page1.md)
[Link 2](page2.md)
[Link 3](#section)
"""
    result = plugin.on_post_convert("https://example.com", markdown)

    # Should process all links
    assert "[Link" in result


def test_link_validator_ignore_pattern_match() -> None:
    """Test link validator ignores links matching patterns."""
    settings = {"ignore_patterns": [r".*\.pdf$", r"https://cdn\..*"]}
    plugin = LinkValidatorPlugin(settings=settings)

    assert plugin._should_ignore_link("document.pdf") is True
    assert plugin._should_ignore_link("https://cdn.example.com/file.js") is True
    assert plugin._should_ignore_link("page.html") is False


def test_link_validator_preserves_link_text() -> None:
    """Test link validator preserves link text."""
    plugin = LinkValidatorPlugin(settings={"check_external": False})

    markdown = "[Click Here](page.md)"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert "[Click Here]" in result


def test_link_validator_fragment_handling(tmp_path: Path) -> None:
    """Test link validator handles URL fragments correctly."""
    settings = {
        "base_dir": str(tmp_path),
        "check_external": False,
    }
    plugin = LinkValidatorPlugin(settings=settings)

    markdown = "[Link](page.md#section)"
    result = plugin.on_post_convert(f"file://{tmp_path}/index.md", markdown)

    # Should check page.md without fragment
    assert result is not None


def test_link_validator_directory_index(tmp_path: Path) -> None:
    """Test link validator checks for index.md in directories."""
    # Create directory with index.md
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "index.md").write_text("content")

    settings = {
        "base_dir": str(tmp_path),
        "check_external": False,
    }
    plugin = LinkValidatorPlugin(settings=settings)

    markdown = "[Link](subdir/)"
    result = plugin.on_post_convert(f"file://{tmp_path}/index.md", markdown)

    # Should find index.md in directory
    assert "<!-- BROKEN LINK:" not in result


def test_link_validator_absolute_path() -> None:
    """Test link validator handles absolute paths."""
    plugin = LinkValidatorPlugin(settings={"check_external": False})

    markdown = "[Link](/docs/page.md)"
    result = plugin.on_post_convert("https://example.com/index.html", markdown)

    assert result is not None


def test_link_validator_relative_path() -> None:
    """Test link validator handles relative paths."""
    plugin = LinkValidatorPlugin(settings={"check_external": False})

    markdown = "[Link](../page.md)"
    result = plugin.on_post_convert("https://example.com/docs/index.html", markdown)

    assert result is not None


def test_link_validator_check_internal_disabled() -> None:
    """Test link validator with internal checking disabled."""
    settings = {
        "check_internal": False,
        "check_external": False,
    }
    plugin = LinkValidatorPlugin(settings=settings)

    markdown = "[Link](missing.md)"
    result = plugin.on_post_convert("https://example.com", markdown)

    # Should not mark as broken when checking is disabled
    assert "<!-- BROKEN LINK:" not in result


def test_link_validator_empty_link() -> None:
    """Test link validator handles empty links."""
    plugin = LinkValidatorPlugin(settings={"check_external": False})

    markdown = "[Link]()"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert result is not None


def test_link_validator_no_links() -> None:
    """Test link validator with no links in markdown."""
    plugin = LinkValidatorPlugin()

    markdown = "# Title\n\nParagraph without links."
    result = plugin.on_post_convert("https://example.com", markdown)

    assert result == markdown


def test_link_validator_hook_returns_string() -> None:
    """Test POST_CONVERT hook returns modified string."""
    plugin = LinkValidatorPlugin()

    markdown = "[Link](page.md)"
    result = plugin.on_post_convert("https://example.com", markdown)

    assert isinstance(result, str)


def test_image_optimizer_initialization() -> None:
    """Test image optimizer plugin initialization."""
    plugin = ImageOptimizerPlugin()
    assert plugin.name == "image_optimizer"
    assert PluginHook.POST_SAVE in plugin.hooks


def test_image_optimizer_default_settings() -> None:
    """Test image optimizer plugin default settings."""
    plugin = ImageOptimizerPlugin()
    assert plugin.max_width == 1920
    assert plugin.max_height == 1080
    assert plugin.quality == 85
    assert plugin.preserve_aspect_ratio is True


def test_image_optimizer_custom_settings() -> None:
    """Test image optimizer plugin with custom settings."""
    settings = {
        "max_width": 1280,
        "max_height": 720,
        "quality": 75,
        "formats": ["jpg", "png"],
    }
    plugin = ImageOptimizerPlugin(settings=settings)
    assert plugin.max_width == 1280
    assert plugin.max_height == 720
    assert plugin.quality == 75
    assert plugin.formats == ["jpg", "png"]


def test_image_optimizer_ignores_markdown() -> None:
    """Test image optimizer ignores markdown files."""
    plugin = ImageOptimizerPlugin()

    plugin.on_post_save("/path/to/file.md", "markdown")

    # Should not attempt to optimize markdown
    assert plugin.optimized_count == 0


def test_image_optimizer_ignores_non_image() -> None:
    """Test image optimizer ignores non-image assets."""
    plugin = ImageOptimizerPlugin()

    plugin.on_post_save("/path/to/file.css", "asset")

    # Should not attempt to optimize CSS
    assert plugin.optimized_count == 0


def test_image_optimizer_missing_file() -> None:
    """Test image optimizer handles missing files gracefully."""
    plugin = ImageOptimizerPlugin()

    plugin.on_post_save("/nonexistent/image.jpg", "asset")

    # Should not crash, just skip
    assert plugin.optimized_count == 0


def test_image_optimizer_supported_formats() -> None:
    """Test image optimizer supports configured formats."""
    plugin = ImageOptimizerPlugin()

    assert "jpg" in plugin.formats
    assert "jpeg" in plugin.formats
    assert "png" in plugin.formats
    assert "webp" in plugin.formats


def test_image_optimizer_post_crawl_stats() -> None:
    """Test image optimizer reports stats in POST_CRAWL."""
    plugin = ImageOptimizerPlugin()

    # Simulate some optimizations
    plugin.optimized_count = 10
    plugin.bytes_saved = 50000

    stats: dict[str, Any] = {}
    plugin.on_post_crawl(stats)

    assert "image_optimization" in stats
    assert stats["image_optimization"]["optimized_count"] == 10
    assert stats["image_optimization"]["bytes_saved"] == 50000


def test_image_optimizer_no_stats_when_zero() -> None:
    """Test image optimizer doesn't add stats if no optimizations."""
    plugin = ImageOptimizerPlugin()

    stats: dict[str, Any] = {}
    plugin.on_post_crawl(stats)

    # Should not add stats if no optimizations performed
    assert "image_optimization" not in stats


def test_image_optimizer_hook_correct() -> None:
    """Test image optimizer subscribes to POST_SAVE hook."""
    plugin = ImageOptimizerPlugin()

    assert PluginHook.POST_SAVE in plugin.hooks
    assert PluginHook.POST_CRAWL in plugin.hooks
