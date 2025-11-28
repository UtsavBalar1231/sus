"""Benchmarks for pipeline queue operations.

Tests performance of:
- MemoryAwareQueue.put() / get() - Queue operations
- MemoryAwareQueue._estimate_size() - Memory estimation
- PipelineStats - Statistics tracking
"""

import asyncio

from pytest_benchmark.fixture import BenchmarkFixture

from sus.crawler import CrawlResult
from sus.pipeline import MemoryAwareQueue, PipelineStats


class TestMemoryAwareQueueBenchmarks:
    """Benchmark MemoryAwareQueue operations."""

    def test_queue_put_get_sync(self, benchmark: BenchmarkFixture, small_html: str) -> None:
        """Benchmark single put/get cycle (sync wrapper)."""
        small_result = CrawlResult(
            url="http://example.com/small",
            html=small_html,
            status_code=200,
            content_type="text/html",
            links=[],
            assets=[],
            content_hash="small123",
            queue_size=0,
        )

        async def put_get() -> CrawlResult | None:
            queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(maxsize=100)
            await queue.put(small_result)
            return await queue.get()

        result = benchmark(lambda: asyncio.run(put_get()))
        assert result is not None
        assert result.url == "http://example.com/small"

    def test_queue_throughput_10(self, benchmark: BenchmarkFixture, small_html: str) -> None:
        """Benchmark 10 items through queue."""
        small_result = CrawlResult(
            url="http://example.com/small",
            html=small_html,
            status_code=200,
            content_type="text/html",
            links=[],
            assets=[],
            content_hash="small123",
            queue_size=0,
        )

        async def throughput_test() -> int:
            queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(maxsize=20)
            # Producer
            for _ in range(10):
                await queue.put(small_result)
            # Consumer
            count = 0
            for _ in range(10):
                item = await queue.get()
                if item is not None:
                    count += 1
                queue.task_done()
            return count

        result = benchmark(lambda: asyncio.run(throughput_test()))
        assert result == 10

    def test_queue_throughput_100(self, benchmark: BenchmarkFixture, small_html: str) -> None:
        """Benchmark 100 items through queue."""
        small_result = CrawlResult(
            url="http://example.com/small",
            html=small_html,
            status_code=200,
            content_type="text/html",
            links=[],
            assets=[],
            content_hash="small123",
            queue_size=0,
        )

        async def throughput_test() -> int:
            queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(maxsize=200)
            # Producer
            for _ in range(100):
                await queue.put(small_result)
            # Consumer
            count = 0
            for _ in range(100):
                item = await queue.get()
                if item is not None:
                    count += 1
                queue.task_done()
            return count

        result = benchmark(lambda: asyncio.run(throughput_test()))
        assert result == 100

    def test_memory_estimation_small(self, benchmark: BenchmarkFixture, small_html: str) -> None:
        """Benchmark memory size estimation for small result."""
        small_result = CrawlResult(
            url="http://example.com/small",
            html=small_html,
            status_code=200,
            content_type="text/html",
            links=[],
            assets=[],
            content_hash="small123",
            queue_size=0,
        )
        queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue()
        result = benchmark(queue._estimate_size, small_result)
        assert result > 0
        assert result < 10000  # Small HTML < 10KB

    def test_memory_estimation_medium(self, benchmark: BenchmarkFixture, medium_html: str) -> None:
        """Benchmark memory size estimation for medium result."""
        sample_result = CrawlResult(
            url="http://example.com/page",
            html=medium_html,
            status_code=200,
            content_type="text/html; charset=utf-8",
            links=[f"http://example.com/page{i}" for i in range(10)],
            assets=[f"http://example.com/img/{i}.png" for i in range(5)],
            content_hash="abc123def456",
            queue_size=0,
        )
        queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue()
        result = benchmark(queue._estimate_size, sample_result)
        assert result > 1000  # Medium HTML > 1KB

    def test_memory_tracking_overhead(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark memory tracking getter overhead."""
        queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(max_memory_mb=500)
        result = benchmark(queue.get_memory_usage_mb)
        assert result >= 0.0

    def test_queue_qsize(self, benchmark: BenchmarkFixture, small_html: str) -> None:
        """Benchmark queue size query."""
        small_result = CrawlResult(
            url="http://example.com/small",
            html=small_html,
            status_code=200,
            content_type="text/html",
            links=[],
            assets=[],
            content_hash="small123",
            queue_size=0,
        )
        # Setup queue outside benchmark
        queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(maxsize=100)
        asyncio.run(_fill_queue(queue, small_result, 50))

        result = benchmark(queue.qsize)
        assert result == 50

    def test_queue_empty_check(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark empty queue check."""
        queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(maxsize=100)
        result = benchmark(queue.empty)
        assert result is True


async def _fill_queue(queue: MemoryAwareQueue[CrawlResult], item: CrawlResult, count: int) -> None:
    """Helper to fill queue with items."""
    for _ in range(count):
        await queue.put(item)


class TestPipelineStatsBenchmarks:
    """Benchmark PipelineStats operations."""

    def test_stats_creation(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark PipelineStats instantiation."""
        result = benchmark(PipelineStats)
        assert result.items_queued == 0
        assert result.items_processed == 0

    def test_stats_field_access(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark stats field access."""
        stats = PipelineStats(
            items_queued=1000,
            items_processed=950,
            items_failed=10,
            max_queue_depth=100,
            current_queue_depth=50,
            current_memory_mb=256.5,
            max_memory_mb=512.0,
        )

        def access_fields() -> tuple[int, int, int, float]:
            return (
                stats.items_queued,
                stats.items_processed,
                stats.items_failed,
                stats.current_memory_mb,
            )

        result = benchmark(access_fields)
        assert result == (1000, 950, 10, 256.5)

    def test_stats_update_pattern(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark typical stats update pattern."""
        stats = PipelineStats()

        def update_stats() -> None:
            stats.items_queued += 1
            stats.current_queue_depth += 1
            if stats.current_queue_depth > stats.max_queue_depth:
                stats.max_queue_depth = stats.current_queue_depth

        benchmark(update_stats)
        assert stats.items_queued > 0
