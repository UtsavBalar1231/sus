"""Configuration system.

YAML configuration files validated by Pydantic models. Provides type-safe configuration
with validation, sensible defaults, and clear error messages. Main function: load_config().
"""

import fnmatch
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from sus.exceptions import ConfigError


class PathPattern(BaseModel):
    """URL pattern matching configuration.

    Supports three pattern types:
    - regex: Regular expression matching
    - glob: Shell-style glob patterns (e.g., "*.html")
    - prefix: Simple prefix matching (e.g., "/docs/")
    """

    pattern: str = Field(..., description="The pattern string to match against URLs")
    type: Literal["regex", "glob", "prefix"] = Field(..., description="Pattern matching type")

    def matches(self, path: str) -> bool:
        """Check if URL path matches this pattern.

        Args:
            path: URL path component (e.g., "/docs/guide/")

        Returns:
            True if path matches the pattern

        Examples:
            >>> pattern = PathPattern(pattern="/docs/", type="prefix")
            >>> pattern.matches("/docs/guide/")
            True
            >>> pattern.matches("/blog/")
            False

            >>> pattern = PathPattern(pattern="*.html", type="glob")
            >>> pattern.matches("/page.html")
            True

            >>> pattern = PathPattern(pattern=r"^/api/v\\d+/", type="regex")
            >>> pattern.matches("/api/v2/users")
            True
        """
        if self.type == "regex":
            # Use re.match() which matches from the beginning
            return bool(re.match(self.pattern, path))
        elif self.type == "glob":
            # Convert glob to regex using fnmatch.translate()
            regex_pattern = fnmatch.translate(self.pattern)
            # fnmatch.translate() adds \Z at the end for full match
            # We want to match if the pattern matches anywhere in the path
            return bool(re.match(regex_pattern, path))
        elif self.type == "prefix":
            # Simple startswith() check
            return path.startswith(self.pattern)
        return False


class SiteConfig(BaseModel):
    """Website configuration for crawling."""

    start_urls: list[str] = Field(..., min_length=1, description="Starting URLs for the crawler")
    allowed_domains: list[str] = Field(
        ..., min_length=1, description="Domains allowed for crawling"
    )


class CrawlingRules(BaseModel):
    """Crawling behavior configuration.

    Controls which URLs to follow, concurrency limits, rate limiting,
    and retry behavior.
    """

    include_patterns: list[PathPattern] = Field(
        default_factory=list,
        description="URL patterns to include (whitelist)",
    )
    exclude_patterns: list[PathPattern] = Field(
        default_factory=list,
        description="URL patterns to exclude (blacklist)",
    )
    depth_limit: int | None = Field(
        default=None,
        ge=0,
        description="Maximum crawl depth from start URLs (None = unlimited)",
    )
    max_pages: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of pages to crawl (None = unlimited)",
    )
    delay_between_requests: float = Field(
        default=0.5,
        ge=0.0,
        description="Delay between requests in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retries for failed requests",
    )
    retry_backoff: float = Field(
        default=2.0,
        ge=1.0,
        description="Exponential backoff multiplier for retries",
    )
    global_concurrent_requests: int = Field(
        default=10,
        ge=1,
        description="Global concurrency limit across all domains",
    )
    per_domain_concurrent_requests: int = Field(
        default=2,
        ge=1,
        description="Per-domain concurrency limit",
    )
    rate_limiter_burst_size: int = Field(
        default=5,
        ge=1,
        description="Token bucket burst size for rate limiting",
    )
    link_selectors: list[str] = Field(
        default_factory=lambda: ["a[href]"],
        description="CSS selectors for extracting links",
    )
    respect_robots_txt: bool = Field(
        default=True,
        description="Whether to respect robots.txt rules",
    )


class PathMappingConfig(BaseModel):
    """URL to file path mapping configuration."""

    mode: Literal["auto"] = Field(
        default="auto",
        description="Path mapping mode (currently only 'auto' is supported)",
    )
    strip_prefix: str | None = Field(
        default=None,
        description="URL path prefix to strip when generating file paths",
    )
    index_file: str = Field(
        default="index.md",
        description="Filename for directory index pages",
    )


class MarkdownConfig(BaseModel):
    """Markdown conversion options."""

    add_frontmatter: bool = Field(
        default=True,
        description="Whether to add YAML frontmatter to markdown files",
    )
    frontmatter_fields: list[str] = Field(
        default_factory=lambda: ["title", "url", "scraped_at"],
        description="Fields to include in frontmatter",
    )


class OutputConfig(BaseModel):
    """Output directory structure configuration."""

    base_dir: str = Field(
        default="output",
        description="Base output directory",
    )
    site_dir: str | None = Field(
        default=None,
        description="Site-specific subdirectory (defaults to config name)",
    )
    docs_dir: str = Field(
        default="docs",
        description="Subdirectory for markdown documentation files",
    )
    assets_dir: str = Field(
        default="assets",
        description="Subdirectory for downloaded assets",
    )
    path_mapping: PathMappingConfig = Field(
        default_factory=PathMappingConfig,
        description="URL to file path mapping configuration",
    )
    markdown: MarkdownConfig = Field(
        default_factory=MarkdownConfig,
        description="Markdown conversion configuration",
    )


class AssetConfig(BaseModel):
    """Asset download configuration."""

    download: bool = Field(
        default=True,
        description="Whether to download assets",
    )
    types: list[str] = Field(
        default_factory=lambda: ["image", "css", "javascript"],
        description="Asset types to download",
    )
    rewrite_paths: bool = Field(
        default=True,
        description="Whether to rewrite asset paths in markdown to local paths",
    )
    max_concurrent_asset_downloads: int = Field(
        default=10,
        ge=1,
        description="Maximum concurrent asset downloads",
    )


class SusConfig(BaseModel):
    """Main configuration model for SUS scraper.

    This is the root configuration object that contains all settings
    for a scraping project.
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Site/config name (used as default site_dir)",
    )
    description: str = Field(
        default="",
        description="Human-readable description of this configuration",
    )
    site: SiteConfig = Field(
        ...,
        description="Website configuration",
    )
    crawling: CrawlingRules = Field(
        default_factory=CrawlingRules,
        description="Crawling behavior rules",
    )
    output: OutputConfig = Field(
        default_factory=OutputConfig,
        description="Output directory structure",
    )
    assets: AssetConfig = Field(
        default_factory=AssetConfig,
        description="Asset download configuration",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate that name is a valid directory name.

        The name must not contain path separators or special characters
        that would be invalid in directory names.
        """
        if not v:
            raise ValueError("name cannot be empty")

        # Check for invalid characters in directory names
        invalid_chars = set('/\\:*?"<>|')
        if any(char in v for char in invalid_chars):
            raise ValueError(f"name contains invalid characters for a directory name: {v!r}")

        # Check for dangerous names
        if v in (".", ".."):
            raise ValueError(f"name cannot be '.' or '..': {v!r}")

        # Check for leading/trailing whitespace
        if v != v.strip():
            raise ValueError(f"name cannot have leading/trailing whitespace: {v!r}")

        return v


def load_config(path: Path) -> SusConfig:
    """Load and validate YAML configuration file.

    Args:
        path: Path to YAML configuration file

    Returns:
        Validated SusConfig instance

    Raises:
        ConfigError: If config file is not found, invalid YAML, or validation fails
    """
    try:
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        if not path.is_file():
            raise ValueError(f"Configuration path is not a file: {path}")

        with path.open("r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)

        if config_dict is None:
            raise ValueError(f"Configuration file is empty: {path}")

        if not isinstance(config_dict, dict):
            raise ValueError(
                f"Configuration file must contain a YAML object/dict, "
                f"got {type(config_dict).__name__}"
            )

        return SusConfig(**config_dict)
    except FileNotFoundError as e:
        raise ConfigError(f"Configuration file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e
    except ValidationError as e:
        raise ConfigError(f"Configuration validation failed for {path}:\n{e}") from e
