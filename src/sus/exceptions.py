"""Custom exceptions for SUS."""


class SusError(Exception):
    """Base exception for all SUS errors."""


class ConfigError(SusError):
    """Raised when configuration is invalid or cannot be loaded."""


class CrawlError(SusError):
    """Raised when crawling fails."""


class SitemapError(SusError):
    """Raised when sitemap parsing fails."""


class ConversionError(SusError):
    """Raised when HTML to Markdown conversion fails.

    This includes critical failures like script/style removal that could
    result in JavaScript code or sensitive data leaking into markdown output.
    """
