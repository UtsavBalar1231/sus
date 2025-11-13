"""Output path mapping and link rewriting.

Transforms web URLs to local file paths and rewrites absolute links to relative paths for
offline browsing. Provides OutputManager for all path operations and markdown link rewriting.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

from sus.config import SusConfig


class OutputManager:
    """Manages output paths and link rewriting.

    Handles:
    - URL to file path mapping
    - Directory structure creation
    - Relative link calculation
    - Link rewriting in markdown

    Examples:
        >>> config = SusConfig(...)
        >>> manager = OutputManager(config)
        >>> doc_path = manager.get_doc_path("https://example.com/doc/guide/")
        >>> asset_path = manager.get_asset_path("https://example.com/img/logo.png")
        >>> markdown = manager.rewrite_links(markdown, source_url)
    """

    def __init__(self, config: SusConfig, dry_run: bool = False) -> None:
        """Initialize output manager.

        Args:
            config: Validated SusConfig instance
            dry_run: If True, don't create directories or write files

        Raises:
            ValueError: If config is invalid or paths are malformed
        """
        self.config = config
        self.dry_run = dry_run

        # Build output paths
        self.base_dir = Path(config.output.base_dir)

        # Site directory (if configured, otherwise use base_dir)
        if config.output.site_dir:
            self.site_dir = self.base_dir / config.output.site_dir
        else:
            self.site_dir = self.base_dir

        # Docs and assets directories
        self.docs_dir = self.site_dir / config.output.docs_dir
        self.assets_dir = self.site_dir / config.output.assets_dir

        # Create directories (unless dry run)
        if not dry_run:
            self.docs_dir.mkdir(parents=True, exist_ok=True)
            self.assets_dir.mkdir(parents=True, exist_ok=True)

    def get_doc_path(self, url: str) -> Path:
        """Convert URL to markdown file path.

        Args:
            url: Source URL to convert

        Returns:
            Absolute path to markdown file

        Logic:
        1. Parse URL and extract path component
        2. Strip configured prefix (config.output.path_mapping.strip_prefix)
        3. Handle directory URLs (ending in /) → use index_file
        4. Convert path segments to file path
        5. Ensure .md extension
        6. Create parent directories (unless dry run)

        Examples:
            URL: https://example.com/doc/guide/install/
            strip_prefix: /doc
            → docs/guide/install/index.md

            URL: https://example.com/doc/overview
            strip_prefix: /doc
            → docs/overview.md

        Raises:
            ValueError: If URL cannot be parsed or path is invalid
        """
        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")

            # Strip configured prefix if set
            strip_prefix = self.config.output.path_mapping.strip_prefix
            if strip_prefix:
                # Normalize prefix (ensure it starts with / and doesn't end with /)
                if not strip_prefix.startswith("/"):
                    strip_prefix = "/" + strip_prefix
                strip_prefix = strip_prefix.rstrip("/")

                # Strip prefix from path
                if path.startswith(strip_prefix):
                    path = path[len(strip_prefix) :]

            # Always remove leading slash to ensure relative paths (even if no prefix to strip)
            path = path.lstrip("/")

            # Handle empty path (index page)
            if not path or path == "/":
                output_path = self.docs_dir / self.config.output.path_mapping.index_file
            # Handle directory URLs (ending in /)
            elif parsed.path.endswith("/"):
                # Path like "guide/install/" → "guide/install/index.md"
                if path:
                    output_path = self.docs_dir / path / self.config.output.path_mapping.index_file
                else:
                    output_path = self.docs_dir / self.config.output.path_mapping.index_file
            else:
                # Regular path → add .md extension
                output_path = self.docs_dir / f"{path}.md"

            # Resolve to absolute path
            output_path = output_path.resolve()

            # Create parent directories (unless dry run)
            if not self.dry_run:
                output_path.parent.mkdir(parents=True, exist_ok=True)

            return output_path

        except Exception as e:
            raise ValueError(f"Failed to convert URL to doc path: {url}") from e

    def get_asset_path(self, asset_url: str) -> Path:
        """Convert asset URL to file path.

        Args:
            asset_url: Asset URL (image, CSS, JS, etc.)

        Returns:
            Absolute path to asset file

        Logic:
        1. Parse URL and extract path
        2. Preserve original directory structure under assets_dir
        3. Example: https://example.com/img/logo.png → assets/img/logo.png

        Examples:
            >>> manager.get_asset_path("https://example.com/img/logo.png")
            Path("/path/to/output/site/assets/img/logo.png")

            >>> manager.get_asset_path("https://example.com/css/style.css")
            Path("/path/to/output/site/assets/css/style.css")

        Raises:
            ValueError: If URL cannot be parsed or path is invalid
        """
        try:
            parsed = urlparse(asset_url)
            path = parsed.path.lstrip("/")

            # Build output path preserving directory structure
            output_path = self.assets_dir / path

            # Resolve to absolute path
            output_path = output_path.resolve()

            # Create parent directories (unless dry run)
            if not self.dry_run:
                output_path.parent.mkdir(parents=True, exist_ok=True)

            return output_path

        except Exception as e:
            raise ValueError(f"Failed to convert URL to asset path: {asset_url}") from e

    def rewrite_links(self, markdown: str, source_url: str) -> str:
        """Rewrite links in markdown to relative paths.

        Args:
            markdown: Markdown content with absolute URLs
            source_url: URL of the source page (for calculating relative paths)

        Returns:
            Markdown with rewritten links

        Rewrites two types of links:
        1. Internal doc links: [text](https://example.com/doc/page) → [text](../page.md)
        2. Asset links: ![alt](https://example.com/img/pic.png) → ![alt](../../assets/img/pic.png)

        Logic:
        1. Calculate source file path from URL
        2. Find all markdown links: [text](url) and ![alt](url)
        3. For each link:
           - If internal doc link (same domain, under allowed paths):
             * Calculate target doc path
             * Calculate relative path from source to target
           - If asset link (image, css, js):
             * Calculate asset path
             * Calculate relative path from source to asset

        Examples:
            >>> markdown = "[Guide](https://example.com/doc/guide/)"
            >>> result = manager.rewrite_links(markdown, "https://example.com/doc/")
            >>> print(result)
            "[Guide](guide/index.md)"

        Raises:
            ValueError: If source_url is invalid
        """
        try:
            # Get source file path
            source_file = self.get_doc_path(source_url)

            # Rewrite markdown images: ![alt](url)
            markdown = self._rewrite_image_links(markdown, source_file)

            # Rewrite markdown links: [text](url)
            markdown = self._rewrite_doc_links(markdown, source_file)

            return markdown

        except Exception as e:
            raise ValueError(f"Failed to rewrite links for {source_url}") from e

    def _rewrite_doc_links(self, markdown: str, source_file: Path) -> str:
        """Rewrite internal documentation links to relative paths.

        Args:
            markdown: Markdown content
            source_file: Absolute path to source markdown file

        Returns:
            Markdown with rewritten doc links
        """

        def replace_link(match: re.Match[str]) -> str:
            """Replace a single link match."""
            link_text = match.group(1)
            link_url = match.group(2)

            # Skip if already a relative path (no scheme)
            if not link_url.startswith(("http://", "https://", "/")):
                return match.group(0)

            # Check if this is an internal doc link
            if self._is_internal_link(link_url):
                try:
                    # Get target file path
                    target_file = self.get_doc_path(link_url)

                    # Calculate relative path
                    relative_path = self._calculate_relative_path(source_file, target_file)

                    return f"[{link_text}]({relative_path})"
                except (ValueError, OSError):
                    # If conversion fails, keep original link
                    return match.group(0)

            # Not an internal doc link, keep original
            return match.group(0)

        # Replace markdown links: [text](url)
        # Negative lookbehind to exclude image links (which start with !)
        markdown = re.sub(r"(?<!!)\[([^\]]+)\]\(([^\)]+)\)", replace_link, markdown)

        return markdown

    def _rewrite_image_links(self, markdown: str, source_file: Path) -> str:
        """Rewrite image/asset links to relative paths pointing to assets directory.

        Args:
            markdown: Markdown content
            source_file: Absolute path to source markdown file

        Returns:
            Markdown with rewritten asset links
        """

        def replace_image(match: re.Match[str]) -> str:
            """Replace a single image match."""
            alt_text = match.group(1)
            img_url = match.group(2)

            # Skip if already a relative path to assets
            if img_url.startswith("../"):
                return match.group(0)

            # Check if this is an asset link
            if self._is_asset_link(img_url):
                try:
                    # Handle relative paths like ../../img/schema.png
                    # Extract from img/ onwards if present
                    if "img/" in img_url and not img_url.startswith(("http://", "https://")):
                        # Extract from img/ onwards
                        img_url = img_url[img_url.find("img/") :]
                        # Build full URL for processing (use first allowed domain)
                        if self.config.site.allowed_domains:
                            img_url = f"https://{self.config.site.allowed_domains[0]}/{img_url}"

                    # Get asset file path
                    asset_file = self.get_asset_path(img_url)

                    # Calculate relative path from source to asset
                    relative_path = self._calculate_relative_path_to_assets(source_file, asset_file)

                    return f"![{alt_text}]({relative_path})"
                except (ValueError, OSError):
                    # If conversion fails, keep original link
                    return match.group(0)

            # Not an asset link, keep original
            return match.group(0)

        # Replace markdown images: ![alt](url)
        markdown = re.sub(r"!\[([^\]]*)\]\(([^\)]+)\)", replace_image, markdown)

        return markdown

    def _calculate_relative_path(self, from_path: Path, to_path: Path) -> str:
        """Calculate relative path from one file to another.

        Args:
            from_path: Source file path (absolute)
            to_path: Target file path (absolute)

        Returns:
            Relative path (e.g., "../../other/page.md")

        Implementation:
        - Calculate depth difference between files
        - Add ../ for each level up needed
        - Append remaining path to target

        Examples:
            >>> from_path = Path("/output/docs/guide/install.md")
            >>> to_path = Path("/output/docs/overview.md")
            >>> result = _calculate_relative_path(from_path, to_path)
            >>> print(result)
            "../overview.md"

        Raises:
            ValueError: If paths cannot be resolved or are invalid
        """
        try:
            # Both paths should be absolute
            from_path = from_path.resolve()
            to_path = to_path.resolve()

            # Get the directory containing the source file
            from_dir = from_path.parent

            # Calculate relative path from source directory to target file
            # Use os.path.relpath for accurate cross-directory calculation
            import os

            rel_path = os.path.relpath(to_path, from_dir)

            # Convert to forward slashes for consistency (Path uses OS-specific separators)
            rel_path = rel_path.replace("\\", "/")

            return rel_path

        except Exception as e:
            raise ValueError(
                f"Failed to calculate relative path from {from_path} to {to_path}"
            ) from e

    def _calculate_relative_path_to_assets(self, from_path: Path, asset_path: Path) -> str:
        """Calculate relative path from doc file to asset file.

        Args:
            from_path: Source doc file path (absolute, within docs_dir)
            asset_path: Target asset file path (absolute, within assets_dir)

        Returns:
            Relative path (e.g., "../../../assets/img/logo.png")

        Logic:
        - Calculate depth from docs_dir
        - Add one extra level to escape docs/ directory into site_dir
        - Append "assets/" and remaining path

        Examples:
            >>> from_path = Path("/output/site/docs/guide/install.md")
            >>> asset_path = Path("/output/site/assets/img/logo.png")
            >>> result = _calculate_relative_path_to_assets(from_path, asset_path)
            >>> print(result)
            "../../assets/img/logo.png"

        Raises:
            ValueError: If paths cannot be resolved or are invalid
        """
        try:
            # Resolve to absolute paths
            from_path = from_path.resolve()
            asset_path = asset_path.resolve()

            # Get source file directory relative to docs_dir
            from_rel = from_path.relative_to(self.docs_dir)
            from_dir = from_rel.parent

            # Calculate depth (number of levels from source to docs_dir)
            depth = len(from_dir.parts) if from_dir != Path(".") else 0

            # Add one extra level to escape docs/ directory
            depth += 1

            # Get asset path relative to assets_dir
            asset_rel = asset_path.relative_to(self.assets_dir)

            # Build relative path: ../../../assets/path/to/asset
            prefix = "../" * depth
            return prefix + "assets/" + str(asset_rel)

        except Exception as e:
            raise ValueError(
                f"Failed to calculate relative path from {from_path} to {asset_path}"
            ) from e

    def _is_internal_link(self, url: str) -> bool:
        """Check if URL is an internal documentation link.

        Args:
            url: URL to check (can be absolute or root-relative)

        Returns:
            True if URL is internal (same allowed_domains)

        Examples:
            >>> manager._is_internal_link("https://example.com/doc/guide/")
            True
            >>> manager._is_internal_link("/doc/guide/")
            True
            >>> manager._is_internal_link("https://other-site.com/page")
            False
        """
        # Root-relative paths are always internal
        if url.startswith("/"):
            # Check if it matches the strip_prefix pattern
            strip_prefix = self.config.output.path_mapping.strip_prefix
            if strip_prefix:
                strip_prefix = strip_prefix.rstrip("/")
                return url.startswith(strip_prefix)
            return True

        # Parse URL to check domain
        try:
            parsed = urlparse(url)

            # No scheme/domain = relative = internal
            if not parsed.netloc:
                return True

            # Check if domain is in allowed_domains
            domain = parsed.netloc.lower()
            # Remove www. prefix for comparison
            domain_no_www = domain.replace("www.", "")

            for allowed_domain in self.config.site.allowed_domains:
                allowed = allowed_domain.lower().replace("www.", "")
                if domain == allowed or domain_no_www == allowed:
                    # Check if path matches strip_prefix pattern
                    strip_prefix = self.config.output.path_mapping.strip_prefix
                    if strip_prefix:
                        strip_prefix = strip_prefix.rstrip("/")
                        return parsed.path.startswith(strip_prefix)
                    return True

            return False

        except (ValueError, AttributeError):
            return False

    def _is_asset_link(self, url: str) -> bool:
        """Check if URL is an asset (image, css, js).

        Args:
            url: URL to check

        Returns:
            True if URL appears to be an asset

        Detection:
        - Check file extension (.png, .jpg, .svg, .css, .js, etc.)

        Examples:
            >>> manager._is_asset_link("https://example.com/img/logo.png")
            True
            >>> manager._is_asset_link("/css/style.css")
            True
            >>> manager._is_asset_link("https://example.com/doc/page")
            False
        """
        # Common asset extensions
        asset_extensions = {
            # Images
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".webp",
            ".ico",
            ".bmp",
            # Stylesheets
            ".css",
            ".scss",
            ".sass",
            ".less",
            # JavaScript
            ".js",
            ".mjs",
            ".ts",
            # Fonts
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".otf",
            # Other
            ".map",  # Source maps
        }

        # Parse URL to get path
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()

            # Check if path ends with any asset extension
            return any(path.endswith(ext) for ext in asset_extensions)

        except (ValueError, AttributeError):
            return False
