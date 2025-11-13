"""Custom exceptions for SUS."""


class SusError(Exception):
    """Base exception for all SUS errors."""


class ConfigError(SusError):
    """Raised when configuration is invalid or cannot be loaded."""


class CrawlError(SusError):
    """Raised when crawling fails."""
