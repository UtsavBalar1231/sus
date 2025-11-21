"""Plugin manager for loading and invoking plugins."""

import importlib
import importlib.util
import inspect
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sus.plugins import Plugin, PluginHook


class PluginManager:
    """Manages plugin lifecycle: loading, initialization, and hook invocation.

    Loads plugins from module paths, tracks them by hook, and provides
    error-isolated invocation with comprehensive error handling.
    """

    def __init__(self, config: Any) -> None:
        """Initialize plugin manager with configuration.

        Args:
            config: PluginConfig instance containing plugin paths and settings
        """
        self.config = config
        self.plugins: list[Plugin] = []
        self.plugins_by_hook: dict[PluginHook, list[Plugin]] = defaultdict(list)
        self.errors: list[dict[str, Any]] = []

        if config.enabled and config.plugins:
            self._load_plugins(config.plugins)

    def _load_plugins(self, plugin_paths: list[str]) -> None:
        """Load plugins from module paths.

        Supports:
        - Built-in plugins: "sus.plugins.code_highlight"
        - Custom plugins: "/path/to/my_plugin.py"
        - Module names: "my_package.my_plugin"

        Args:
            plugin_paths: List of plugin module paths or file paths
        """
        for plugin_path in plugin_paths:
            try:
                plugin = self._load_single_plugin(plugin_path)
                if plugin:
                    self.plugins.append(plugin)
                    for hook in plugin.hooks:
                        self.plugins_by_hook[hook].append(plugin)
            except Exception as e:
                error_info = {
                    "plugin_path": plugin_path,
                    "error": str(e),
                    "type": type(e).__name__,
                }
                self.errors.append(error_info)

    def _load_single_plugin(self, plugin_path: str) -> Plugin | None:
        """Load a single plugin from path.

        Args:
            plugin_path: Module path or file path to plugin

        Returns:
            Initialized Plugin instance or None if loading failed

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If module doesn't have a Plugin subclass
            TypeError: If Plugin class is invalid
        """
        plugin_settings = self.config.plugin_settings.get(plugin_path, {})

        if plugin_path.endswith(".py"):
            module = self._load_plugin_from_file(plugin_path)
        else:
            module = importlib.import_module(plugin_path)

        plugin_class = self._find_plugin_class(module, plugin_path)

        plugin_instance: Plugin = plugin_class(settings=plugin_settings)
        return plugin_instance

    def _find_plugin_class(self, module: Any, plugin_path: str) -> type[Plugin]:
        """Find the plugin class in a module.

        Looks for a class that inherits from Plugin by:
        1. Checking __all__ for exported classes
        2. Scanning module for Plugin subclasses

        Args:
            module: Loaded plugin module
            plugin_path: Original plugin path (for error messages)

        Returns:
            Plugin class

        Raises:
            AttributeError: If no Plugin subclass found
            TypeError: If found class doesn't inherit from Plugin
        """
        # Try __all__ first
        if hasattr(module, "__all__"):
            for name in module.__all__:
                if hasattr(module, name):
                    obj = getattr(module, name)
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, Plugin)
                        and obj is not Plugin
                    ):
                        return obj

        # Fallback: scan module for Plugin subclasses
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Plugin) and obj is not Plugin and obj.__module__ == module.__name__:
                return obj

        raise AttributeError(
            f"Plugin module {plugin_path} must define a class that inherits from sus.plugins.Plugin"
        )

    def _load_plugin_from_file(self, file_path: str) -> Any:
        """Load plugin from Python file path.

        Args:
            file_path: Absolute or relative path to .py file

        Returns:
            Loaded module

        Raises:
            FileNotFoundError: If file doesn't exist
            ImportError: If module cannot be imported
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Plugin file not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Plugin path is not a file: {file_path}")

        module_name = f"sus_custom_plugin_{path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin from {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        return module

    async def invoke_hook(self, hook: PluginHook, **kwargs: Any) -> str | None:
        """Invoke all plugins for a specific hook.

        Plugins are invoked in order they were loaded. Each plugin invocation
        is wrapped in try/except to isolate errors. Failed plugins are logged
        but don't stop other plugins from running.

        Args:
            hook: Hook to invoke
            **kwargs: Arguments to pass to plugin hook methods

        Returns:
            For POST_CONVERT: Modified markdown (chained through all plugins)
            For other hooks: None (notification-only)

        Examples:
            # Notification hook
            await manager.invoke_hook(PluginHook.PRE_CRAWL, config=config)

            # Content modification hook
            markdown = await manager.invoke_hook(
                PluginHook.POST_CONVERT,
                url="https://example.com/page",
                markdown="# Content"
            )
        """
        plugins = self.plugins_by_hook.get(hook, [])
        if not plugins:
            return kwargs.get("markdown") if hook == PluginHook.POST_CONVERT else None

        result: str | None = None

        for plugin in plugins:
            try:
                if hook == PluginHook.PRE_CRAWL:
                    plugin.on_pre_crawl(config=kwargs["config"])

                elif hook == PluginHook.POST_FETCH:
                    plugin.on_post_fetch(
                        url=kwargs["url"],
                        html=kwargs["html"],
                        status_code=kwargs["status_code"],
                    )

                elif hook == PluginHook.POST_CONVERT:
                    markdown = kwargs["markdown"]
                    modified_markdown = plugin.on_post_convert(
                        url=kwargs["url"],
                        markdown=markdown,
                    )
                    kwargs["markdown"] = modified_markdown
                    result = modified_markdown

                elif hook == PluginHook.POST_SAVE:
                    plugin.on_post_save(
                        file_path=kwargs["file_path"],
                        content_type=kwargs["content_type"],
                    )

                elif hook == PluginHook.POST_CRAWL:
                    plugin.on_post_crawl(stats=kwargs["stats"])

            except Exception as e:
                error_info = {
                    "plugin": plugin.name,
                    "hook": hook.value,
                    "error": str(e),
                    "type": type(e).__name__,
                }
                if "url" in kwargs:
                    error_info["url"] = kwargs["url"]
                self.errors.append(error_info)

        return result


__all__ = ["PluginManager"]
