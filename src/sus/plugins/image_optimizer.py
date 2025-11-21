"""Image optimization plugin using Pillow.

Resizes and compresses images to reduce file size while maintaining quality.
Processes images after they are saved (POST_SAVE hook).
"""

from pathlib import Path
from typing import Any

from sus.plugins import Plugin, PluginHook

try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


class ImageOptimizerPlugin(Plugin):
    """Image optimization plugin.

    Optimizes images after saving by:
    - Resizing images above maximum dimensions
    - Compressing with configurable quality
    - Converting to optimal formats

    Settings:
        max_width: Maximum image width in pixels (default: 1920)
        max_height: Maximum image height in pixels (default: 1080)
        quality: JPEG/WebP quality 1-100 (default: 85)
        formats: List of formats to optimize (default: ["jpg", "jpeg", "png", "webp"])
        preserve_aspect_ratio: Maintain aspect ratio when resizing (default: True)
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        """Initialize image optimizer plugin.

        Args:
            settings: Plugin settings

        Raises:
            ImportError: If Pillow is not installed
        """
        super().__init__(settings)

        if not PILLOW_AVAILABLE:
            raise ImportError("Pillow is not installed. Install with: uv sync --group plugins")

        self.max_width = self.settings.get("max_width", 1920)
        self.max_height = self.settings.get("max_height", 1080)
        self.quality = self.settings.get("quality", 85)
        self.formats = self.settings.get("formats", ["jpg", "jpeg", "png", "webp"])
        self.preserve_aspect_ratio = self.settings.get("preserve_aspect_ratio", True)

        self.optimized_count = 0
        self.bytes_saved = 0

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "image_optimizer"

    @property
    def hooks(self) -> list[PluginHook]:
        """Subscribe to POST_SAVE and POST_CRAWL hooks."""
        return [PluginHook.POST_SAVE, PluginHook.POST_CRAWL]

    def on_post_save(self, file_path: str, content_type: str) -> None:
        """Optimize image after saving.

        Args:
            file_path: Path to saved file
            content_type: Type of content ("markdown" or "asset")
        """
        if content_type != "asset":
            return

        path = Path(file_path)
        if not path.exists():
            return

        extension = path.suffix.lower().lstrip(".")
        if extension not in self.formats:
            return

        self._optimize_image(path)

    def _optimize_image(self, path: Path) -> None:
        """Optimize a single image file.

        Args:
            path: Path to image file
        """
        try:
            original_size = path.stat().st_size

            with Image.open(path) as img:
                img_format = img.format
                original_width, original_height = img.size

                needs_resize = original_width > self.max_width or original_height > self.max_height

                if needs_resize:
                    if self.preserve_aspect_ratio:
                        img.thumbnail(
                            (self.max_width, self.max_height),
                            Image.Resampling.LANCZOS,
                        )
                    else:
                        img = img.resize(
                            (self.max_width, self.max_height),
                            Image.Resampling.LANCZOS,
                        )

                save_kwargs: dict[str, Any] = {}
                if img_format in ("JPEG", "JPG"):
                    save_kwargs["quality"] = self.quality
                    save_kwargs["optimize"] = True
                elif img_format == "PNG":
                    save_kwargs["optimize"] = True
                elif img_format == "WEBP":
                    save_kwargs["quality"] = self.quality

                img.save(path, format=img_format, **save_kwargs)

            new_size = path.stat().st_size
            if new_size < original_size:
                self.optimized_count += 1
                self.bytes_saved += original_size - new_size

        except Exception:
            pass

    def on_post_crawl(self, stats: dict[str, Any]) -> None:
        """Report optimization statistics.

        Args:
            stats: Scraping statistics
        """
        if self.optimized_count > 0:
            kb_saved = self.bytes_saved / 1024
            stats["image_optimization"] = {
                "optimized_count": self.optimized_count,
                "bytes_saved": self.bytes_saved,
                "kb_saved": round(kb_saved, 2),
            }


__all__ = ["ImageOptimizerPlugin"]
