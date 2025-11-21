"""SUS - Simple Universal Scraper."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("distiller-sdk")
except PackageNotFoundError:
    __version__ = "dev"
