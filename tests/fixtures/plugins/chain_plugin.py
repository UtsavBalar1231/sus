"""Plugin for testing plugin chaining."""

from sus.plugins import Plugin as BasePlugin
from sus.plugins import PluginHook


class Plugin(BasePlugin):
    """Plugin that modifies content for chaining tests."""

    @property
    def name(self) -> str:
        return "chain_test_plugin"

    @property
    def hooks(self) -> list[PluginHook]:
        return [PluginHook.POST_CONVERT]

    def on_post_convert(self, url: str, markdown: str) -> str:
        prefix = self.settings.get("prefix", "CHAIN:")
        return f"{prefix} {markdown}"
