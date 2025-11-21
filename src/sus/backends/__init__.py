"""Backend factory for checkpoint state persistence.

Factory for creating checkpoint backends based on configuration.
Supports JSON (default) and SQLite backends.
"""

import hashlib
import json
from pathlib import Path
from typing import Literal

from sus.backends.base import CheckpointMetadata, PageCheckpoint, StateBackend
from sus.backends.json_backend import JSONBackend
from sus.backends.sqlite_backend import SQLiteBackend
from sus.config import SusConfig

# Re-export for convenience
__all__ = [
    "CheckpointMetadata",
    "PageCheckpoint",
    "StateBackend",
    "JSONBackend",
    "SQLiteBackend",
    "create_backend",
    "compute_content_hash",
    "compute_config_hash",
]


def create_backend(
    path: Path, backend_type: Literal["json", "sqlite"] | None = None
) -> StateBackend:
    """Create appropriate backend based on path and optional type hint.

    Args:
        path: Path to checkpoint file (.json or .db)
        backend_type: Explicit backend type, or None to auto-detect from path

    Returns:
        StateBackend instance (JSONBackend or SQLiteBackend)

    Examples:
        >>> backend = create_backend(Path("checkpoint.json"))  # Auto-detects JSON
        >>> backend = create_backend(Path("checkpoint.db"))     # Auto-detects SQLite
        >>> backend = create_backend(Path("data.txt"), "sqlite")  # Force SQLite
    """
    # Determine backend type
    if backend_type is None:
        # Auto-detect from file extension
        backend_type = "sqlite" if path.suffix in (".db", ".sqlite", ".sqlite3") else "json"

    # Create backend
    if backend_type == "sqlite":
        return SQLiteBackend(path)
    else:
        return JSONBackend(path)


def compute_content_hash(html: str) -> str:
    """Compute SHA-256 hash of HTML content.

    Used for change detection - if hash differs from checkpoint,
    page content has changed and should be re-scraped.

    Args:
        html: HTML content string

    Returns:
        SHA-256 hex digest

    Examples:
        >>> compute_content_hash("<html>...</html>")
        'abc123...'
    """
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def compute_config_hash(config: SusConfig) -> str:
    """Compute hash of config fields relevant to scraping.

    Only hashes fields that affect scraping behavior (not output paths).
    Changes to these fields invalidate the checkpoint.

    Args:
        config: SUS configuration

    Returns:
        SHA-256 hex digest of relevant config fields

    Examples:
        >>> compute_config_hash(config)
        'def456...'
    """
    # Extract only fields that affect crawl behavior
    relevant_fields = {
        "name": config.name,
        "start_urls": sorted(config.site.start_urls),
        "allowed_domains": sorted(config.site.allowed_domains),
        "include_patterns": [
            {"pattern": p.pattern, "type": p.type} for p in config.crawling.include_patterns
        ],
        "exclude_patterns": [
            {"pattern": p.pattern, "type": p.type} for p in config.crawling.exclude_patterns
        ],
        "depth_limit": config.crawling.depth_limit,
        "link_selectors": config.crawling.link_selectors,
    }

    # Serialize to JSON (sorted keys for deterministic hash)
    config_json = json.dumps(relevant_fields, sort_keys=True)

    # Compute SHA-256 hash
    return hashlib.sha256(config_json.encode("utf-8")).hexdigest()
