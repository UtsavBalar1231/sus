"""Shared HTTP client utilities for crawler and asset downloader.

Provides factory functions for creating httpx clients with HTTP/2, caching,
retries, and connection pooling configured according to SusConfig.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from hishel import AsyncSqliteStorage
from hishel.httpx import AsyncCacheClient
from httpx_retries import Retry, RetryTransport

if TYPE_CHECKING:
    from sus.config import SusConfig


def create_cache_storage(config: "SusConfig") -> AsyncSqliteStorage | None:
    """Create cache storage based on configuration.

    Args:
        config: SUS configuration

    Returns:
        Cache storage instance or None if disabled or using memory backend
    """
    if not config.crawling.cache.enabled:
        return None

    cache_config = config.crawling.cache
    cache_dir = Path(config.output.base_dir) / cache_config.cache_dir

    if cache_config.backend == "sqlite":
        cache_db = cache_dir / "http_cache.db"
        cache_db.parent.mkdir(parents=True, exist_ok=True)
        return AsyncSqliteStorage(
            database_path=str(cache_db),
            default_ttl=float(cache_config.ttl_seconds) if cache_config.ttl_seconds else None,
        )
    elif cache_config.backend == "memory":
        return None
    return None


def create_http_client(
    config: "SusConfig",
    auth_handler: httpx.Auth | None = None,
) -> httpx.AsyncClient | AsyncCacheClient:
    """Create HTTP client with HTTP/2, retry logic, and optional caching.

    Args:
        config: SUS configuration
        auth_handler: Optional httpx Auth handler

    Returns:
        Configured httpx AsyncClient or Hishel AsyncCacheClient
    """
    retry_policy = Retry(
        total=config.crawling.max_retries,
        backoff_factor=config.crawling.retry_backoff - 1.0,
        backoff_jitter=config.crawling.retry_jitter,
        status_forcelist=[429, 500, 502, 503, 504],
        respect_retry_after_header=True,
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"],
    )

    base_transport = httpx.AsyncHTTPTransport(
        http2=True,
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
        retries=0,
    )

    transport = RetryTransport(transport=base_transport, retry=retry_policy)

    base_client = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        max_redirects=config.crawling.max_redirects,
        headers={"User-Agent": "SUS/0.2.0 (Simple Universal Scraper)"},
        auth=auth_handler,
    )

    if config.crawling.cache.enabled:
        storage = create_cache_storage(config)
        return AsyncCacheClient(
            storage=storage,
            transport=transport,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            max_redirects=config.crawling.max_redirects,
            headers={"User-Agent": "SUS/0.2.0 (Simple Universal Scraper)"},
            auth=auth_handler,
        )
    else:
        return base_client
