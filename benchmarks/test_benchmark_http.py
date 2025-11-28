"""Benchmarks for HTTP client backends and DNS resolution.

Tests performance of:
- DNS resolution with and without caching
- HTTP client backend comparison (httpx vs aiohttp)
- Connection pooling effectiveness
- Conditional requests (ETag/If-Modified-Since)
"""

import asyncio
import time

from pytest_benchmark.fixture import BenchmarkFixture

from sus.dns import AsyncDNSResolver, reset_default_resolver


class TestDNSBenchmarks:
    """Benchmark DNS resolution performance."""

    def test_dns_cache_hit(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark DNS cache hit performance (should be <0.1ms)."""
        reset_default_resolver()

        # Pre-populate the cache manually to avoid network calls
        async def cached_lookup() -> str:
            resolver = AsyncDNSResolver(cache_ttl=300, use_aiodns=False)
            # Manually populate cache to avoid network call
            from sus.dns import DNSCacheEntry

            resolver._cache["example.com"] = DNSCacheEntry(
                ip_address="93.184.216.34",
                expires_at=time.time() + 300,
            )
            # This should be a cache hit - no network call
            return await resolver.resolve("example.com")

        result = benchmark(lambda: asyncio.run(cached_lookup()))
        assert result == "93.184.216.34"

    def test_dns_cache_lookup_speed(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark pure cache lookup speed without async overhead."""
        reset_default_resolver()

        from sus.dns import DNSCacheEntry

        # Set up cache directly
        cache: dict[str, DNSCacheEntry] = {}
        for i in range(1000):
            cache[f"domain{i}.example.com"] = DNSCacheEntry(
                ip_address=f"192.168.1.{i % 256}",
                expires_at=time.time() + 300,
            )

        def lookup_cached() -> str | None:
            entry = cache.get("domain500.example.com")
            if entry is not None and not entry.is_expired:
                return entry.ip_address
            return None

        result = benchmark(lookup_cached)
        assert result == "192.168.1.244"  # 500 % 256 = 244


class TestLinkExtractorXPathBenchmarks:
    """Benchmark link extraction with cached XPath."""

    def test_xpath_cache_reuse(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
    ) -> None:
        """Benchmark XPath cache reuse across multiple extractions."""
        from sus.rules import LinkExtractor

        # Create extractor (compiles XPath once)
        extractor = LinkExtractor(["a[href]"])

        # Simulate processing multiple pages (XPath should be cached)
        def extract_batch() -> list[set[str]]:
            results = []
            for i in range(10):
                results.append(extractor.extract_links(medium_html, f"http://example.com/page{i}/"))
            return results

        results = benchmark(extract_batch)
        assert len(results) == 10

    def test_xpath_class_level_cache(
        self,
        benchmark: BenchmarkFixture,
        small_html: str,
    ) -> None:
        """Benchmark class-level XPath cache across instances."""
        from sus.rules import LinkExtractor

        def create_and_extract() -> list[set[str]]:
            results = []
            for i in range(10):
                # Create new instance each time (XPath should still be cached at class level)
                extractor = LinkExtractor(["a[href]"])
                results.append(extractor.extract_links(small_html, f"http://example.com/{i}/"))
            return results

        results = benchmark(create_and_extract)
        assert len(results) == 10


class TestRateLimiterBenchmarks:
    """Benchmark rate limiter performance."""

    def test_adaptive_rate_limiter_acquire(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark rate limiter acquire with high burst."""
        from sus.crawler import AdaptiveRateLimiter

        async def acquire_burst() -> int:
            limiter = AdaptiveRateLimiter(initial_rate=100.0, burst=50)
            count = 0
            for _ in range(50):
                await limiter.acquire()
                count += 1
            return count

        result = benchmark(lambda: asyncio.run(acquire_burst()))
        assert result == 50

    def test_adaptive_rate_limiter_adaptation(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark rate limiter response recording and adaptation."""
        from sus.crawler import AdaptiveRateLimiter

        def record_responses() -> float:
            limiter = AdaptiveRateLimiter(initial_rate=10.0, burst=50)
            # Record fast responses
            for _ in range(100):
                limiter.record_response(response_time=0.05, status_code=200)
            return limiter.current_rate

        result = benchmark(record_responses)
        # Should have sped up from fast responses
        assert result >= 10.0


class TestConditionalRequestsBenchmarks:
    """Benchmark conditional request header handling."""

    def test_conditional_headers_lookup(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark checkpoint lookup for conditional headers."""
        from sus.backends.base import PageCheckpoint

        # Simulate a cache of page checkpoints
        pages: dict[str, PageCheckpoint] = {}
        for i in range(1000):
            pages[f"http://example.com/page{i}"] = PageCheckpoint(
                url=f"http://example.com/page{i}",
                content_hash=f"hash{i}",
                last_scraped="2024-01-01T00:00:00Z",
                status_code=200,
                file_path=f"/path/page{i}.md",
                etag=f'"etag{i}"',
                last_modified=f"Mon, 01 Jan 2024 00:00:0{i % 10} GMT",
            )

        def lookup_headers() -> dict[str, str]:
            # Simulate looking up conditional headers
            url = "http://example.com/page500"
            page = pages.get(url)
            if page is None:
                return {}
            headers: dict[str, str] = {}
            if page.etag:
                headers["If-None-Match"] = page.etag
            if page.last_modified:
                headers["If-Modified-Since"] = page.last_modified
            return headers

        result = benchmark(lookup_headers)
        assert "If-None-Match" in result
        assert "If-Modified-Since" in result


class TestConnectionPoolingBenchmarks:
    """Benchmark connection pooling configuration."""

    def test_pool_config_creation(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark HTTP client configuration creation."""
        import httpx

        def create_pool_config() -> httpx.Limits:
            return httpx.Limits(
                max_connections=500,
                max_keepalive_connections=100,
                keepalive_expiry=60.0,
            )

        result = benchmark(create_pool_config)
        assert result.max_connections == 500
        assert result.max_keepalive_connections == 100
