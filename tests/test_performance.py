"""Performance regression tests.

Run with: pytest tests/test_performance.py --benchmark-only
Compare: pytest tests/test_performance.py --benchmark-compare
"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from sus.config import (
    AssetConfig,
    CrawlingRules,
    MarkdownConfig,
    OutputConfig,
    PathMappingConfig,
    SiteConfig,
    SusConfig,
)


@pytest.fixture
def perf_config() -> SusConfig:
    """Config optimized for performance testing."""
    return SusConfig(
        name="perf-test",
        description="Performance test configuration",
        site=SiteConfig(
            start_urls=["http://example.com/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.0,  # No rate limiting for benchmarks
            global_concurrent_requests=25,
            per_domain_concurrent_requests=5,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir="output",
            docs_dir="docs",
            assets_dir="assets",
            path_mapping=PathMappingConfig(),
            markdown=MarkdownConfig(),
        ),
        assets=AssetConfig(download=False),
    )


def test_url_normalization_10_urls(
    benchmark: BenchmarkFixture,
    perf_config: SusConfig,
) -> None:
    """Benchmark URL normalization performance with 10 URLs."""
    from sus.rules import URLNormalizer

    def normalize_10_urls() -> int:
        urls = [f"HTTP://Example.COM/page{i}.html#section" for i in range(10)]
        normalized = [URLNormalizer.normalize_url(url) for url in urls]
        return len(normalized)

    result = benchmark(normalize_10_urls)
    assert result == 10, "Should normalize 10 URLs"


def test_url_normalization_100_urls(
    benchmark: BenchmarkFixture,
    perf_config: SusConfig,
) -> None:
    """Benchmark URL normalization performance with 100 URLs."""
    from sus.rules import URLNormalizer

    def normalize_100_urls() -> int:
        urls = [f"HTTP://Example.COM/page{i}.html#section{j}" for i in range(100) for j in range(1)]
        normalized = [URLNormalizer.normalize_url(url) for url in urls]
        return len(normalized)

    result = benchmark(normalize_100_urls)
    assert result == 100, "Should normalize 100 URLs"


def test_async_file_write_performance(benchmark: BenchmarkFixture) -> None:
    """Benchmark async file write throughput."""
    import aiofiles

    async def write_100_files() -> int:
        with TemporaryDirectory() as tmpdir:

            async def write_file(i: int) -> None:
                file_path = Path(tmpdir) / f"file{i}.txt"
                async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                    await f.write(f"Content for file {i}\n" * 100)

            await asyncio.gather(*[write_file(i) for i in range(100)])
            return 100

    result = benchmark(lambda: asyncio.run(write_100_files()))
    assert result == 100, "Should write 100 files"


def test_token_bucket_rate_limiter_performance(
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark rate limiter overhead."""
    from sus.crawler import RateLimiter

    async def acquire_1000_tokens() -> int:
        limiter = RateLimiter(rate=1000.0, burst=50)  # Very high rate
        for _ in range(1000):
            await limiter.acquire()
        return 1000

    result = benchmark(lambda: asyncio.run(acquire_1000_tokens()))
    assert result == 1000, "Should acquire 1000 tokens"
