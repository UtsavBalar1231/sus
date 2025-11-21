"""Plugin with slow operations for testing performance."""

from sus.plugins import Plugin as BasePlugin
from sus.plugins import PluginHook


class Plugin(BasePlugin):
    """Plugin with slow hooks for testing."""

    @property
    def name(self) -> str:
        return "slow_test_plugin"

    @property
    def hooks(self) -> list[PluginHook]:
        return [PluginHook.POST_FETCH]

    def on_post_fetch(self, url: str, html: str, status_code: int) -> None:
        delay = self.settings.get("delay", 0.1)
        import time

        time.sleep(delay)
