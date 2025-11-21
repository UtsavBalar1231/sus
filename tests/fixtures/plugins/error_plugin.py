"""Plugin that raises errors for testing error handling."""

from sus.plugins import Plugin as BasePlugin
from sus.plugins import PluginHook


class Plugin(BasePlugin):
    """Plugin that raises errors in hooks."""

    @property
    def name(self) -> str:
        return "error_test_plugin"

    @property
    def hooks(self) -> list[PluginHook]:
        return [PluginHook.POST_CONVERT]

    def on_post_convert(self, url: str, markdown: str) -> str:
        raise RuntimeError("Intentional error for testing")
