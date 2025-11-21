"""Valid test plugin for testing plugin system."""

from typing import Any

from sus.plugins import Plugin as BasePlugin
from sus.plugins import PluginHook


class Plugin(BasePlugin):
    """Valid test plugin."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self.pre_crawl_called = False
        self.post_fetch_calls: list[dict[str, Any]] = []
        self.post_convert_calls: list[dict[str, Any]] = []
        self.post_save_calls: list[dict[str, Any]] = []
        self.post_crawl_called = False

    @property
    def name(self) -> str:
        return "valid_test_plugin"

    @property
    def hooks(self) -> list[PluginHook]:
        return [
            PluginHook.PRE_CRAWL,
            PluginHook.POST_FETCH,
            PluginHook.POST_CONVERT,
            PluginHook.POST_SAVE,
            PluginHook.POST_CRAWL,
        ]

    def on_pre_crawl(self, config: Any) -> None:
        self.pre_crawl_called = True

    def on_post_fetch(self, url: str, html: str, status_code: int) -> None:
        self.post_fetch_calls.append({"url": url, "html": html, "status_code": status_code})

    def on_post_convert(self, url: str, markdown: str) -> str:
        self.post_convert_calls.append({"url": url, "markdown": markdown})
        return markdown + "\n\n<!-- Modified by valid_test_plugin -->"

    def on_post_save(self, file_path: str, content_type: str) -> None:
        self.post_save_calls.append({"file_path": file_path, "content_type": content_type})

    def on_post_crawl(self, stats: dict[str, Any]) -> None:
        self.post_crawl_called = True
