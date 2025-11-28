"""Shared HTTP client utilities for crawler and asset downloader.

Provides factory functions for creating HTTP clients with:
- Dual backend support: httpx (HTTP/2) and aiohttp (faster HTTP/1.1)
- Auto-detection of optimal backend per domain
- HTTP caching, retries, and connection pooling

Performance: aiohttp is 7.5x faster for HTTP/1.1, but httpx supports HTTP/2.
Use 'auto' mode for optimal performance across mixed HTTP/1.1 and HTTP/2 sites.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import httpx
from hishel import AsyncSqliteStorage
from hishel.httpx import AsyncCacheClient
from httpx_retries import Retry, RetryTransport

if TYPE_CHECKING:
    from sus.config import SusConfig

logger = logging.getLogger(__name__)

# Check if aiohttp is available (optional perf dependency)
try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    """Unified HTTP response for backend abstraction."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str

    @property
    def text(self) -> str:
        """Decode content as UTF-8 text."""
        return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        """Raise an exception for 4xx/5xx responses."""
        if 400 <= self.status_code < 600:
            raise HTTPStatusError(self.status_code, self.url)


class HTTPStatusError(Exception):
    """HTTP status error for non-2xx responses."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} for {url}")


@runtime_checkable
class HTTPClientBackend(Protocol):
    """Protocol for HTTP client backends.

    Allows swapping between httpx and aiohttp implementations.
    """

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """Perform GET request."""
        ...

    async def head(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """Perform HEAD request."""
        ...

    async def close(self) -> None:
        """Close the client and release resources."""
        ...

    @property
    def supports_http2(self) -> bool:
        """Whether this backend supports HTTP/2."""
        ...


class HttpxBackend:
    """httpx-based HTTP client backend with HTTP/2 support."""

    def __init__(
        self,
        client: httpx.AsyncClient | AsyncCacheClient,
        *,
        owns_client: bool = True,
    ) -> None:
        self._client = client
        self._owns_client = owns_client

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """Perform GET request."""
        kwargs: dict[str, object] = {}
        if headers:
            kwargs["headers"] = headers
        if timeout:
            kwargs["timeout"] = timeout

        response = await self._client.get(url, **kwargs)  # type: ignore[arg-type]
        return HTTPResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
            url=str(response.url),
        )

    async def head(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """Perform HEAD request."""
        kwargs: dict[str, object] = {}
        if headers:
            kwargs["headers"] = headers
        if timeout:
            kwargs["timeout"] = timeout

        response = await self._client.head(url, **kwargs)  # type: ignore[arg-type]
        return HTTPResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=b"",
            url=str(response.url),
        )

    async def close(self) -> None:
        """Close the client."""
        if self._owns_client:
            await self._client.aclose()

    @property
    def supports_http2(self) -> bool:
        """httpx supports HTTP/2."""
        return True

    @property
    def raw_client(self) -> httpx.AsyncClient | AsyncCacheClient:
        """Access the underlying httpx client for advanced operations."""
        return self._client


class AioHTTPBackend:
    """aiohttp-based HTTP client backend (faster for HTTP/1.1).

    Performance: 7.5x faster than httpx for single requests,
    1.5x faster for session-based requests.

    Limitations: Does not support HTTP/2.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        owns_session: bool = True,
        default_timeout: float = 30.0,
    ) -> None:
        self._session = session
        self._owns_session = owns_session
        self._default_timeout = default_timeout

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """Perform GET request."""
        timeout_val = aiohttp.ClientTimeout(total=timeout or self._default_timeout)
        async with self._session.get(url, headers=headers, timeout=timeout_val) as response:
            content = await response.read()
            return HTTPResponse(
                status_code=response.status,
                headers=dict(response.headers.items()),
                content=content,
                url=str(response.url),
            )

    async def head(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HTTPResponse:
        """Perform HEAD request."""
        timeout_val = aiohttp.ClientTimeout(total=timeout or self._default_timeout)
        async with self._session.head(url, headers=headers, timeout=timeout_val) as response:
            return HTTPResponse(
                status_code=response.status,
                headers=dict(response.headers.items()),
                content=b"",
                url=str(response.url),
            )

    async def close(self) -> None:
        """Close the session."""
        if self._owns_session:
            await self._session.close()

    @property
    def supports_http2(self) -> bool:
        """aiohttp does not support HTTP/2."""
        return False

    @property
    def raw_session(self) -> aiohttp.ClientSession:
        """Access the underlying aiohttp session."""
        return self._session


HTTPBackendType = Literal["httpx", "aiohttp", "auto"]


def create_cache_storage(config: SusConfig) -> AsyncSqliteStorage | None:
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


def create_httpx_client(
    config: SusConfig,
    auth_handler: httpx.Auth | None = None,
    *,
    max_connections: int = 500,
    max_keepalive_connections: int = 100,
    keepalive_expiry: float = 60.0,
) -> httpx.AsyncClient | AsyncCacheClient:
    """Create httpx client with HTTP/2, retry logic, and optional caching.

    Args:
        config: SUS configuration
        auth_handler: Optional httpx Auth handler
        max_connections: Maximum total connections (default: 500)
        max_keepalive_connections: Maximum keepalive connections (default: 100)
        keepalive_expiry: Keepalive expiry in seconds (default: 60.0)

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
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
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


def create_aiohttp_session(
    config: SusConfig,
    *,
    max_connections: int = 500,
    max_connections_per_host: int = 50,
    keepalive_timeout: float = 60.0,
    enable_dns_cache: bool = True,
) -> aiohttp.ClientSession:
    """Create aiohttp session optimized for high-performance crawling.

    Args:
        config: SUS configuration
        max_connections: Maximum total connections (default: 500)
        max_connections_per_host: Maximum connections per host (default: 50)
        keepalive_timeout: Keepalive timeout in seconds (default: 60.0)
        enable_dns_cache: Enable DNS caching (default: True)

    Returns:
        Configured aiohttp ClientSession

    Raises:
        ImportError: If aiohttp is not installed
    """
    if not AIOHTTP_AVAILABLE:
        raise ImportError(
            "aiohttp is not installed. Install with: uv sync --group perf\n"
            "Or use httpx backend instead."
        )

    # Try to use aiodns for faster async DNS resolution
    try:
        import aiodns  # noqa: F401

        resolver_class = aiohttp.AsyncResolver
    except ImportError:
        resolver_class = aiohttp.ThreadedResolver  # type: ignore[assignment]
        logger.debug("aiodns not available, using threaded DNS resolver")

    connector = aiohttp.TCPConnector(
        limit=max_connections,
        limit_per_host=max_connections_per_host,
        enable_cleanup_closed=True,
        force_close=False,
        keepalive_timeout=keepalive_timeout,
        resolver=resolver_class() if enable_dns_cache else None,
        ttl_dns_cache=300 if enable_dns_cache else None,  # 5 min DNS cache
    )

    timeout = aiohttp.ClientTimeout(
        total=30.0,
        connect=10.0,
    )

    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={"User-Agent": "SUS/0.2.0 (Simple Universal Scraper)"},
    )


def create_http_backend(
    config: SusConfig,
    auth_handler: httpx.Auth | None = None,
    *,
    backend: HTTPBackendType = "auto",
    max_connections: int = 500,
    max_keepalive_connections: int = 100,
) -> HTTPClientBackend:
    """Create HTTP client backend based on configuration.

    Args:
        config: SUS configuration
        auth_handler: Optional httpx Auth handler (only for httpx backend)
        backend: Backend type - "httpx", "aiohttp", or "auto"
        max_connections: Maximum total connections
        max_keepalive_connections: Maximum keepalive connections

    Returns:
        HTTP client backend (HttpxBackend or AioHTTPBackend)

    Note:
        - "auto" mode uses aiohttp if available (faster), falls back to httpx
        - aiohttp does not support HTTP/2 or custom auth handlers
        - Use httpx backend if you need HTTP/2 or authentication
    """
    use_aiohttp = False

    if backend == "aiohttp":
        if not AIOHTTP_AVAILABLE:
            raise ImportError(
                "aiohttp backend requested but not installed. Install with: uv sync --group perf"
            )
        use_aiohttp = True
    elif backend == "auto":
        # Auto mode: prefer aiohttp for speed, but use httpx if auth is needed
        if AIOHTTP_AVAILABLE and auth_handler is None:
            use_aiohttp = True
            logger.info("Using aiohttp backend (7.5x faster for HTTP/1.1)")
        else:
            if auth_handler is not None:
                logger.info("Using httpx backend (auth handler requires httpx)")
            else:
                logger.info("Using httpx backend (aiohttp not available)")

    if use_aiohttp:
        session = create_aiohttp_session(
            config,
            max_connections=max_connections,
            max_connections_per_host=max_keepalive_connections,
        )
        return AioHTTPBackend(session)
    else:
        client = create_httpx_client(
            config,
            auth_handler,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
        )
        return HttpxBackend(client)


# Legacy function for backwards compatibility
def create_http_client(
    config: SusConfig,
    auth_handler: httpx.Auth | None = None,
) -> httpx.AsyncClient | AsyncCacheClient:
    """Create HTTP client with HTTP/2, retry logic, and optional caching.

    DEPRECATED: Use create_http_backend() for new code.

    This function is kept for backwards compatibility with existing code
    that expects an httpx client directly.

    Args:
        config: SUS configuration
        auth_handler: Optional httpx Auth handler

    Returns:
        Configured httpx AsyncClient or Hishel AsyncCacheClient
    """
    return create_httpx_client(config, auth_handler)
