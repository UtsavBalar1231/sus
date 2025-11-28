"""Benchmarks for crawler components.

Tests performance of:
- LinkExtractor - HTML link extraction
- URL deduplication - Set operations
- Queue operations - asyncio.Queue put/get
"""

import asyncio

from pytest_benchmark.fixture import BenchmarkFixture

from sus.rules import LinkExtractor


class TestLinkExtractorBenchmarks:
    """Benchmark link extraction from HTML."""

    def test_extract_links_small(
        self,
        benchmark: BenchmarkFixture,
        small_html: str,
    ) -> None:
        """Benchmark link extraction from small HTML."""
        extractor = LinkExtractor(["a[href]"])
        result = benchmark(
            extractor.extract_links,
            small_html,
            "http://example.com/",
        )
        assert len(result) >= 3  # Has 3 links

    def test_extract_links_medium(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
    ) -> None:
        """Benchmark link extraction from medium HTML with 100 links."""
        extractor = LinkExtractor(["a[href]"])
        result = benchmark(
            extractor.extract_links,
            medium_html,
            "http://example.com/docs/",
        )
        assert len(result) >= 100

    def test_extract_links_large(
        self,
        benchmark: BenchmarkFixture,
        large_html: str,
    ) -> None:
        """Benchmark link extraction from large HTML with 500 links."""
        extractor = LinkExtractor(["a[href]"])
        result = benchmark(
            extractor.extract_links,
            large_html,
            "http://example.com/docs/",
        )
        assert len(result) >= 500

    def test_extract_links_batch(
        self,
        benchmark: BenchmarkFixture,
        medium_html: str,
    ) -> None:
        """Benchmark extracting links from 10 pages."""
        extractor = LinkExtractor(["a[href]"])
        pages = [(medium_html, f"http://example.com/page{i}/") for i in range(10)]

        def extract_batch() -> list[set[str]]:
            return [extractor.extract_links(html, url) for html, url in pages]

        results = benchmark(extract_batch)
        assert len(results) == 10


class TestCrawlerComponentBenchmarks:
    """Benchmark individual crawler components."""

    def test_url_deduplication(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark URL deduplication via set operations."""
        urls = [f"http://example.com/page{i % 50}" for i in range(1000)]
        seen: set[str] = set()

        def deduplicate() -> int:
            nonlocal seen
            seen = set()
            new_count = 0
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    new_count += 1
            return new_count

        result = benchmark(deduplicate)
        assert result == 50  # 50 unique URLs

    def test_queue_operations(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark asyncio.Queue put/get operations."""

        async def queue_ops() -> int:
            queue: asyncio.Queue[str] = asyncio.Queue()
            # Add 100 items
            for i in range(100):
                await queue.put(f"http://example.com/page{i}")
            # Get 100 items
            count = 0
            for _ in range(100):
                await queue.get()
                count += 1
            return count

        result = benchmark(lambda: asyncio.run(queue_ops()))
        assert result == 100
