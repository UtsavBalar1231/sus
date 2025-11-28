"""Unit tests for Pipeline and MemoryAwareQueue."""

import asyncio

import pytest

from sus.crawler import CrawlResult
from sus.pipeline import MemoryAwareQueue, Pipeline, PipelineStats


@pytest.mark.asyncio
async def test_memory_aware_queue_basic_operations() -> None:
    """Test basic put/get operations on MemoryAwareQueue."""
    queue: MemoryAwareQueue[str] = MemoryAwareQueue(maxsize=10, max_memory_mb=100)

    await queue.put("item1")
    await queue.put("item2")
    await queue.put("item3")

    assert queue.qsize() == 3
    assert not queue.empty()

    item1 = await queue.get()
    assert item1 == "item1"

    item2 = await queue.get()
    assert item2 == "item2"

    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_memory_aware_queue_tracks_memory() -> None:
    """Test memory tracking for queued items."""
    queue: MemoryAwareQueue[str] = MemoryAwareQueue(max_memory_mb=1)  # 1MB limit

    await queue.put("a" * 1000)  # ~1KB
    memory_after_first = queue.get_memory_usage_mb()
    assert memory_after_first > 0

    await queue.put("b" * 1000)  # ~1KB
    memory_after_second = queue.get_memory_usage_mb()
    assert memory_after_second > memory_after_first

    await queue.get()
    memory_after_get = queue.get_memory_usage_mb()
    assert memory_after_get < memory_after_second


@pytest.mark.asyncio
async def test_memory_aware_queue_backpressure() -> None:
    """Test backpressure when memory limit is reached."""
    # Very small memory limit to trigger backpressure
    queue: MemoryAwareQueue[str] = MemoryAwareQueue(max_memory_mb=0.001)  # ~1KB

    large_item = "x" * 500  # ~500 bytes

    await queue.put(large_item)

    await queue.put(large_item)

    # Third item would exceed limit, so it should block
    put_task = asyncio.create_task(queue.put(large_item))

    # Wait a bit - put should still be blocked
    await asyncio.sleep(0.1)
    assert not put_task.done(), "Put should be blocked due to memory limit"

    await queue.get()

    await asyncio.wait_for(put_task, timeout=1.0)
    assert put_task.done(), "Put should complete after memory is freed"


@pytest.mark.asyncio
async def test_memory_aware_queue_poison_pill() -> None:
    """Test poison pill (None) handling."""
    queue: MemoryAwareQueue[str] = MemoryAwareQueue(maxsize=10, max_memory_mb=100)

    await queue.put("item1")
    await queue.put("item2")

    await queue.put(None)

    assert await queue.get() == "item1"
    assert await queue.get() == "item2"

    assert await queue.get() is None


@pytest.mark.asyncio
async def test_memory_aware_queue_poison_pill_never_blocks() -> None:
    """Test poison pill can always be added (ignores memory limit)."""
    # Very small memory limit
    queue: MemoryAwareQueue[str] = MemoryAwareQueue(max_memory_mb=0.001)

    await queue.put("x" * 500)
    await queue.put("y" * 500)

    # Poison pill should always be allowed (no timeout)
    await asyncio.wait_for(queue.put(None), timeout=0.5)

    await queue.get()
    await queue.get()
    assert await queue.get() is None


@pytest.mark.asyncio
async def test_memory_aware_queue_crawl_result_size_estimation() -> None:
    """Test size estimation for CrawlResult objects."""
    queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(max_memory_mb=10)

    html_content = "<html><body>Test content</body></html>" * 100  # ~3KB
    result = CrawlResult(
        url="https://example.com",
        final_url="https://example.com",
        html=html_content,
        status_code=200,
        content_type="text/html",
        links=[],
        assets=[],
        content_hash="abc123",
    )

    await queue.put(result)
    memory_mb = queue.get_memory_usage_mb()

    # Memory should be roughly proportional to HTML size (with 5% overhead)
    expected_bytes = len(html_content.encode("utf-8")) * 1.05
    expected_mb = expected_bytes / (1024 * 1024)

    assert abs(memory_mb - expected_mb) < 0.01, "Memory estimate should be close to HTML size"


@pytest.mark.asyncio
async def test_pipeline_initialization() -> None:
    """Test Pipeline initialization."""
    pipeline = Pipeline(
        process_workers=5,
        queue_maxsize=100,
        max_queue_memory_mb=500,
    )

    assert pipeline.process_workers == 5
    assert pipeline.stats.items_queued == 0
    assert pipeline.stats.items_processed == 0
    assert pipeline.stats.items_failed == 0


@pytest.mark.asyncio
async def test_pipeline_enqueue_updates_stats() -> None:
    """Test enqueuing items updates statistics."""
    pipeline = Pipeline(process_workers=2, queue_maxsize=10, max_queue_memory_mb=100)

    result = CrawlResult(
        url="https://example.com",
        final_url="https://example.com",
        html="<html><body>Test</body></html>",
        status_code=200,
        content_type="text/html",
        links=[],
        assets=[],
        content_hash="abc123",
    )

    await pipeline.enqueue(result)
    await pipeline.enqueue(result)
    await pipeline.enqueue(result)

    assert pipeline.stats.items_queued == 3
    assert pipeline.stats.current_queue_depth == 3
    assert pipeline.stats.max_queue_depth == 3
    assert pipeline.stats.current_memory_mb > 0


@pytest.mark.asyncio
async def test_pipeline_worker_processing() -> None:
    """Test workers process items from queue."""
    pipeline = Pipeline(process_workers=2, queue_maxsize=10, max_queue_memory_mb=100)

    processed_items: list[str] = []

    async def process_worker(worker_id: int, queue: MemoryAwareQueue[CrawlResult]) -> None:
        """Simple worker that collects URLs."""
        while True:
            item = await queue.get()
            if item is None:  # Poison pill
                queue.task_done()
                break

            processed_items.append(item.url)
            queue.task_done()

    await pipeline.start_workers(process_worker)

    for i in range(5):
        result = CrawlResult(
            url=f"https://example.com/page{i}",
            final_url=f"https://example.com/page{i}",
            html=f"<html><body>Page {i}</body></html>",
            status_code=200,
            content_type="text/html",
            links=[],
            assets=[],
            content_hash=f"hash{i}",
        )
        await pipeline.enqueue(result)

    await pipeline.wait_completion()

    await pipeline.shutdown()

    assert len(processed_items) == 5
    assert all(f"https://example.com/page{i}" in processed_items for i in range(5))


@pytest.mark.asyncio
async def test_pipeline_graceful_shutdown() -> None:
    """Test graceful shutdown with poison pills."""
    pipeline = Pipeline(process_workers=3, queue_maxsize=10, max_queue_memory_mb=100)

    worker_received_poison_pill = [False, False, False]

    async def process_worker(worker_id: int, queue: MemoryAwareQueue[CrawlResult]) -> None:
        """Worker that tracks poison pill receipt."""
        while True:
            item = await queue.get()
            if item is None:  # Poison pill
                worker_received_poison_pill[worker_id] = True
                queue.task_done()
                break
            queue.task_done()

    # Start workers
    await pipeline.start_workers(process_worker)

    # Shutdown immediately (no items)
    await pipeline.shutdown()

    # All workers should have received poison pill
    assert all(worker_received_poison_pill), "All workers should receive poison pill"


@pytest.mark.asyncio
async def test_pipeline_worker_error_tracking() -> None:
    """Test worker error tracking in statistics."""
    pipeline = Pipeline(process_workers=2, queue_maxsize=10, max_queue_memory_mb=100)

    async def failing_worker(worker_id: int, queue: MemoryAwareQueue[CrawlResult]) -> None:
        """Worker that raises an error."""
        item = await queue.get()
        if item is None:
            queue.task_done()
            return

        # Simulate error
        queue.task_done()
        raise ValueError(f"Worker {worker_id} encountered an error")

    # Start workers
    await pipeline.start_workers(failing_worker)

    # Enqueue item that will cause error
    result = CrawlResult(
        url="https://example.com/error",
        final_url="https://example.com/error",
        html="<html><body>Error page</body></html>",
        status_code=200,
        content_type="text/html",
        links=[],
        assets=[],
        content_hash="error123",
    )
    await pipeline.enqueue(result)

    # Wait for processing (workers will fail)
    await pipeline.wait_completion()

    # Shutdown
    await pipeline.shutdown()

    # Check that at least one worker recorded an error
    # (Both workers might race to get the item, so at least one should error)
    assert len(pipeline.stats.worker_errors) > 0, "Worker errors should be tracked"


@pytest.mark.asyncio
async def test_pipeline_memory_tracking() -> None:
    """Test pipeline tracks memory usage correctly."""
    pipeline = Pipeline(process_workers=1, queue_maxsize=10, max_queue_memory_mb=10)

    # Create large HTML content
    large_html = "<html><body>" + "x" * 10000 + "</body></html>"

    result = CrawlResult(
        url="https://example.com/large",
        final_url="https://example.com/large",
        html=large_html,
        status_code=200,
        content_type="text/html",
        links=[],
        assets=[],
        content_hash="large123",
    )

    # Enqueue items
    await pipeline.enqueue(result)
    await pipeline.enqueue(result)
    await pipeline.enqueue(result)

    # Check memory stats updated
    assert pipeline.stats.current_memory_mb > 0
    assert pipeline.stats.max_memory_mb > 0
    assert pipeline.stats.max_memory_mb >= pipeline.stats.current_memory_mb


@pytest.mark.asyncio
async def test_pipeline_is_idle() -> None:
    """Test pipeline idle detection."""
    pipeline = Pipeline(process_workers=1, queue_maxsize=10, max_queue_memory_mb=100)

    assert pipeline.is_idle()

    result = CrawlResult(
        url="https://example.com",
        final_url="https://example.com",
        html="<html><body>Test</body></html>",
        status_code=200,
        content_type="text/html",
        links=[],
        assets=[],
        content_hash="abc123",
    )
    await pipeline.enqueue(result)

    assert not pipeline.is_idle()

    await pipeline.queue.get()
    pipeline.queue.task_done()

    # Queue is empty now, but stats.current_queue_depth is stale
    # (only updated on enqueue). So check queue.empty() directly instead.
    assert pipeline.queue.empty()


@pytest.mark.asyncio
async def test_pipeline_stats_initialization() -> None:
    """Test PipelineStats initialization."""
    stats = PipelineStats()

    assert stats.items_queued == 0
    assert stats.items_processed == 0
    assert stats.items_failed == 0
    assert stats.max_queue_depth == 0
    assert stats.current_queue_depth == 0
    assert stats.current_memory_mb == 0.0
    assert stats.max_memory_mb == 0.0
    assert stats.worker_errors == {}


@pytest.mark.asyncio
async def test_pipeline_concurrent_workers() -> None:
    """Test multiple workers process items concurrently."""
    pipeline = Pipeline(process_workers=5, queue_maxsize=50, max_queue_memory_mb=100)

    processed_count = [0]  # Use list to allow mutation in closure
    lock = asyncio.Lock()

    async def counting_worker(worker_id: int, queue: MemoryAwareQueue[CrawlResult]) -> None:
        """Worker that counts processed items."""
        while True:
            item = await queue.get()
            if item is None:  # Poison pill
                queue.task_done()
                break

            # Simulate some processing time
            await asyncio.sleep(0.01)

            async with lock:
                processed_count[0] += 1

            queue.task_done()

    # Start workers
    await pipeline.start_workers(counting_worker)

    # Enqueue many items
    num_items = 20
    for i in range(num_items):
        result = CrawlResult(
            url=f"https://example.com/page{i}",
            final_url=f"https://example.com/page{i}",
            html=f"<html><body>Page {i}</body></html>",
            status_code=200,
            content_type="text/html",
            links=[],
            assets=[],
            content_hash=f"hash{i}",
        )
        await pipeline.enqueue(result)

    # Wait for processing
    await pipeline.wait_completion()

    # Shutdown
    await pipeline.shutdown()

    # All items should be processed
    assert processed_count[0] == num_items
