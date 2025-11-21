"""Type definitions and protocols for sus.

Common type definitions used across the sus package, including protocols for
lxml types which have incomplete type stubs.
"""

from typing import Any, Protocol


# Protocols for lxml type safety (lxml has incomplete type stubs)
class LxmlElement(Protocol):
    """Protocol for lxml Element objects."""

    def get(self, key: str) -> str | None:
        """Get attribute value."""
        ...


class LxmlDocument(Protocol):
    """Protocol for lxml document objects (HtmlElement)."""

    def make_links_absolute(self, base_url: str) -> None:
        """Convert all relative URLs to absolute."""
        ...

    def xpath(self, expr: str) -> list[Any]:
        """Execute XPath query."""
        ...
