"""Async DNS resolution with caching and prefetching.

Provides high-performance DNS resolution for web crawling:
- Async DNS lookups via aiodns (50-200ms saved per new domain)
- In-memory caching with TTL expiration
- Batch prefetching for discovered domains
- Thread-safe for concurrent crawling

Performance: DNS lookups can add 50-200ms per new domain.
Caching and prefetching eliminate this overhead for repeated accesses.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Check if aiodns is available (optional perf dependency)
try:
    import aiodns

    AIODNS_AVAILABLE = True
except ImportError:
    AIODNS_AVAILABLE = False


@dataclass
class DNSCacheEntry:
    """Cached DNS resolution result."""

    ip_address: str
    expires_at: float
    resolved_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() > self.expires_at

    @property
    def ttl_remaining(self) -> float:
        """Remaining TTL in seconds."""
        return max(0.0, self.expires_at - time.time())


@dataclass
class DNSStats:
    """DNS resolver statistics."""

    cache_hits: int = 0
    cache_misses: int = 0
    prefetch_count: int = 0
    resolution_errors: int = 0
    total_resolution_time_ms: float = 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0

    @property
    def avg_resolution_time_ms(self) -> float:
        """Average resolution time in milliseconds."""
        if self.cache_misses == 0:
            return 0.0
        return self.total_resolution_time_ms / self.cache_misses


class AsyncDNSResolver:
    """High-performance async DNS resolver with caching.

    Features:
    - Async DNS resolution via aiodns
    - In-memory cache with configurable TTL
    - Batch prefetching for discovered domains
    - Concurrent resolution with semaphore limits
    - Fallback to socket.getaddrinfo if aiodns unavailable

    Example:
        resolver = AsyncDNSResolver(cache_ttl=300)
        ip = await resolver.resolve("example.com")

        # Prefetch multiple domains
        await resolver.prefetch({"example.com", "example.org"})
    """

    def __init__(
        self,
        cache_ttl: int = 300,
        max_concurrent: int = 50,
        use_aiodns: bool = True,
    ) -> None:
        """Initialize DNS resolver.

        Args:
            cache_ttl: Cache TTL in seconds (default: 300 = 5 minutes)
            max_concurrent: Maximum concurrent DNS lookups (default: 50)
            use_aiodns: Use aiodns if available (default: True)
        """
        self._cache: dict[str, DNSCacheEntry] = {}
        self._cache_ttl = cache_ttl
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[str]] = {}
        self.stats = DNSStats()

        # Initialize aiodns resolver if available and requested
        self._resolver: aiodns.DNSResolver | None = None
        if use_aiodns and AIODNS_AVAILABLE:
            try:
                self._resolver = aiodns.DNSResolver()
                logger.debug("Using aiodns for async DNS resolution")
            except Exception as e:
                logger.warning(f"Failed to initialize aiodns: {e}, using fallback")
                self._resolver = None
        elif use_aiodns and not AIODNS_AVAILABLE:
            logger.debug("aiodns not available, using socket fallback")

    async def resolve(self, hostname: str) -> str:
        """Resolve hostname to IP address.

        Args:
            hostname: Domain name to resolve

        Returns:
            IP address string

        Raises:
            DNSResolutionError: If resolution fails
        """
        # Check cache first (fast path)
        cached = self._get_cached(hostname)
        if cached is not None:
            self.stats.cache_hits += 1
            return cached

        # Check if resolution is already in progress
        async with self._lock:
            if hostname in self._pending:
                # Wait for existing resolution
                return await self._pending[hostname]

            # Create future for this resolution
            future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
            self._pending[hostname] = future

        try:
            # Perform resolution
            self.stats.cache_misses += 1
            start_time = time.perf_counter()

            async with self._semaphore:
                ip = await self._resolve_impl(hostname)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self.stats.total_resolution_time_ms += elapsed_ms

            # Cache the result
            self._cache[hostname] = DNSCacheEntry(
                ip_address=ip,
                expires_at=time.time() + self._cache_ttl,
            )

            # Complete the future
            future.set_result(ip)
            return ip

        except Exception as e:
            self.stats.resolution_errors += 1
            future.set_exception(DNSResolutionError(hostname, str(e)))
            raise DNSResolutionError(hostname, str(e)) from e

        finally:
            async with self._lock:
                self._pending.pop(hostname, None)

    async def _resolve_impl(self, hostname: str) -> str:
        """Internal resolution implementation."""
        if self._resolver is not None:
            # Use aiodns
            try:
                result = await self._resolver.query(hostname, "A")
                if result:
                    return str(result[0].host)
                raise DNSResolutionError(hostname, "No A records found")
            except aiodns.error.DNSError as e:
                raise DNSResolutionError(hostname, str(e)) from e
        else:
            # Fallback to socket.getaddrinfo in thread pool
            return await self._resolve_fallback(hostname)

    async def _resolve_fallback(self, hostname: str) -> str:
        """Fallback DNS resolution using socket.getaddrinfo."""
        import socket

        loop = asyncio.get_event_loop()

        def do_resolve() -> str:
            try:
                result = socket.getaddrinfo(hostname, None, socket.AF_INET)
                if result:
                    # result is list of (family, type, proto, canonname, sockaddr)
                    # sockaddr is (ip, port) for AF_INET
                    sockaddr = result[0][4]
                    return str(sockaddr[0])
                raise DNSResolutionError(hostname, "No addresses found")
            except socket.gaierror as e:
                raise DNSResolutionError(hostname, str(e)) from e

        try:
            return await loop.run_in_executor(None, do_resolve)
        except DNSResolutionError:
            raise
        except Exception as e:
            raise DNSResolutionError(hostname, str(e)) from e

    def _get_cached(self, hostname: str) -> str | None:
        """Get cached IP address if valid."""
        entry = self._cache.get(hostname)
        if entry is not None and not entry.is_expired:
            return entry.ip_address
        return None

    async def prefetch(self, hostnames: set[str]) -> dict[str, str | None]:
        """Prefetch DNS for multiple domains in parallel.

        Args:
            hostnames: Set of domain names to prefetch

        Returns:
            Dict mapping hostname to IP (or None if failed)
        """
        results: dict[str, str | None] = {}

        async def resolve_one(hostname: str) -> None:
            try:
                results[hostname] = await self.resolve(hostname)
                self.stats.prefetch_count += 1
            except DNSResolutionError:
                results[hostname] = None

        # Filter out already-cached hostnames
        to_resolve = {h for h in hostnames if self._get_cached(h) is None}

        if to_resolve:
            logger.debug(f"Prefetching DNS for {len(to_resolve)} domains")
            await asyncio.gather(*[resolve_one(h) for h in to_resolve])

        # Add cached results
        for hostname in hostnames - to_resolve:
            cached = self._get_cached(hostname)
            if cached:
                results[hostname] = cached

        return results

    def clear_cache(self) -> None:
        """Clear the DNS cache."""
        self._cache.clear()

    def remove_expired(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        now = time.time()
        expired = [h for h, e in self._cache.items() if e.expires_at < now]
        for hostname in expired:
            del self._cache[hostname]
        return len(expired)

    @property
    def cache_size(self) -> int:
        """Number of entries in cache."""
        return len(self._cache)

    def get_stats_summary(self) -> str:
        """Get human-readable stats summary."""
        return (
            f"DNS Stats: {self.stats.cache_hits} hits, {self.stats.cache_misses} misses "
            f"({self.stats.cache_hit_rate:.1f}% hit rate), "
            f"{self.stats.resolution_errors} errors, "
            f"avg {self.stats.avg_resolution_time_ms:.1f}ms resolution time"
        )


class DNSResolutionError(Exception):
    """DNS resolution failed."""

    def __init__(self, hostname: str, reason: str) -> None:
        self.hostname = hostname
        self.reason = reason
        super().__init__(f"DNS resolution failed for {hostname}: {reason}")


# Singleton resolver for global use
_default_resolver: AsyncDNSResolver | None = None


def get_default_resolver(
    cache_ttl: int = 300,
    max_concurrent: int = 50,
) -> AsyncDNSResolver:
    """Get or create the default DNS resolver.

    Args:
        cache_ttl: Cache TTL in seconds (only used on first call)
        max_concurrent: Max concurrent lookups (only used on first call)

    Returns:
        Singleton AsyncDNSResolver instance
    """
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = AsyncDNSResolver(
            cache_ttl=cache_ttl,
            max_concurrent=max_concurrent,
        )
    return _default_resolver


def reset_default_resolver() -> None:
    """Reset the default resolver (for testing)."""
    global _default_resolver
    _default_resolver = None
