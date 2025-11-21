"""Producer-consumer pipeline for concurrent scraping.

Implements a multi-stage pipeline architecture with memory-aware queues to achieve
3-10x throughput improvement over sequential processing.

Architecture:
- Producer: Crawler (fetches HTML, extracts links/assets)
- Queue: MemoryAwareQueue (CrawlResults with backpressure)
- Consumers: Process workers (convert to markdown, save files, download assets)

The crawler already handles concurrent fetching via global_concurrent_requests.
The pipeline adds parallel processing of fetched pages to eliminate sequential bottleneck.
"""

import asyncio
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sus.crawler import CrawlResult


class PipelineStage(Enum):
    """Pipeline processing stages."""

    CRAWL = "crawl"  # Fetch HTML + extract links/assets (done by Crawler)
    PROCESS = "process"  # Convert to markdown + save files + download assets
    COMPLETE = "complete"  # Processing finished


@dataclass
class PipelineStats:
    """Statistics for pipeline performance monitoring."""

    items_queued: int = 0
    items_processed: int = 0
    items_failed: int = 0
    max_queue_depth: int = 0
    current_queue_depth: int = 0
    current_memory_mb: float = 0.0
    max_memory_mb: float = 0.0
    worker_errors: dict[int, list[str]] = field(default_factory=dict)


class MemoryAwareQueue[T]:
    """Queue with memory usage tracking to prevent OOM.

    Tracks estimated memory usage of queued items and blocks put() operations
    when memory limit is reached. This provides backpressure to prevent the
    crawler from overwhelming the system memory with fetched pages.

    Example:
        >>> queue = MemoryAwareQueue[CrawlResult](maxsize=100, max_memory_mb=500)
        >>> await queue.put(result)  # Blocks if memory limit reached
        >>> result = await queue.get()
    """

    def __init__(self, maxsize: int = 0, max_memory_mb: int = 500) -> None:
        """Initialize memory-aware queue.

        Args:
            maxsize: Maximum queue size (0 = unlimited by count)
            max_memory_mb: Maximum memory usage in MB (hard limit)
        """
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(maxsize=maxsize)
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._current_memory_bytes = 0
        self._lock = asyncio.Lock()
        self._memory_available = asyncio.Event()
        self._memory_available.set()  # Initially available

    async def put(self, item: T | None) -> None:
        """Put item in queue, blocking if memory limit reached.

        Args:
            item: Item to enqueue (None = poison pill for shutdown)
        """
        if item is None:
            # Poison pill - always allow
            await self._queue.put(None)
            return

        item_size = self._estimate_size(item)

        while True:
            async with self._lock:
                if self._current_memory_bytes + item_size <= self._max_memory_bytes:
                    self._current_memory_bytes += item_size
                    if self._current_memory_bytes >= self._max_memory_bytes * 0.95:
                        self._memory_available.clear()
                    break

            # Memory limit reached - wait for space
            await self._memory_available.wait()
            await asyncio.sleep(0.1)  # Brief pause before retry

        await self._queue.put(item)

    async def get(self) -> T | None:
        """Get item from queue and free its memory.

        Returns:
            Item from queue, or None if poison pill received
        """
        item = await self._queue.get()

        if item is None:
            return None

        item_size = self._estimate_size(item)
        async with self._lock:
            self._current_memory_bytes = max(0, self._current_memory_bytes - item_size)
            # Signal memory availability
            self._memory_available.set()

        return item

    def task_done(self) -> None:
        """Mark task as done (for queue.join())."""
        self._queue.task_done()

    async def join(self) -> None:
        """Wait for all tasks to complete."""
        await self._queue.join()

    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    def get_memory_usage_mb(self) -> float:
        return self._current_memory_bytes / (1024 * 1024)

    def _estimate_size(self, item: T) -> int:
        """Estimate memory size of item in bytes.

        Args:
            item: Item to estimate

        Returns:
            Estimated size in bytes
        """
        if isinstance(item, CrawlResult):
            # Main memory consumer is HTML content
            html_size = len(item.html.encode("utf-8"))
            # Add overhead for links, assets, metadata (~5%)
            return int(html_size * 1.05)
        elif isinstance(item, str):
            return len(item.encode("utf-8"))
        else:
            # Fallback to sys.getsizeof (less accurate but safe)
            return sys.getsizeof(item)


class Pipeline:
    """Producer-consumer pipeline for concurrent scraping.

    Coordinates crawler (producer) and process workers (consumers) via
    memory-aware queues. Handles graceful shutdown with poison pill pattern.

    Example:
        >>> pipeline = Pipeline(
        ...     process_workers=10,
        ...     queue_maxsize=100,
        ...     max_queue_memory_mb=500,
        ... )
        >>> await pipeline.start_workers(process_fn)
        >>> # Feed items from crawler
        >>> async for result in crawler.crawl():
        ...     await pipeline.enqueue(result)
        >>> await pipeline.shutdown()
    """

    def __init__(
        self,
        process_workers: int,
        queue_maxsize: int = 100,
        max_queue_memory_mb: int = 500,
    ) -> None:
        """Initialize pipeline.

        Args:
            process_workers: Number of concurrent process workers
            queue_maxsize: Max size of processing queue
            max_queue_memory_mb: Max memory per queue in MB
        """
        self.process_workers = process_workers

        # Processing queue (crawler → process workers)
        self.queue: MemoryAwareQueue[CrawlResult] = MemoryAwareQueue(
            maxsize=queue_maxsize,
            max_memory_mb=max_queue_memory_mb,
        )

        # Worker tasks
        self._process_tasks: list[asyncio.Task[Any]] = []

        # Statistics
        self.stats = PipelineStats()

        # Shutdown flag
        self._shutdown = False

    async def enqueue(self, result: CrawlResult) -> None:
        """Enqueue a crawl result for processing.

        Args:
            result: CrawlResult to process
        """
        await self.queue.put(result)
        self.stats.items_queued += 1

        # Update queue depth stats
        current_depth = self.queue.qsize()
        self.stats.current_queue_depth = current_depth
        self.stats.max_queue_depth = max(self.stats.max_queue_depth, current_depth)

        # Update memory stats
        current_memory = self.queue.get_memory_usage_mb()
        self.stats.current_memory_mb = current_memory
        self.stats.max_memory_mb = max(self.stats.max_memory_mb, current_memory)

    async def start_workers(
        self,
        process_fn: Any,  # Async function: (worker_id, queue) -> None
    ) -> None:
        """Start process worker pool.

        Args:
            process_fn: Async function for process workers
                Signature: async def process_fn(
                    worker_id: int, queue: MemoryAwareQueue
                ) -> None
        """
        # Start process workers
        for worker_id in range(self.process_workers):
            task = asyncio.create_task(
                self._worker_wrapper(worker_id, process_fn),
                name=f"process-worker-{worker_id}",
            )
            self._process_tasks.append(task)

    async def _worker_wrapper(self, worker_id: int, process_fn: Any) -> None:
        """Wrapper for worker function with error handling.

        Args:
            worker_id: Worker identifier
            process_fn: Worker function to execute
        """
        try:
            await process_fn(worker_id, self.queue)
        except Exception as e:
            if worker_id not in self.stats.worker_errors:
                self.stats.worker_errors[worker_id] = []
            self.stats.worker_errors[worker_id].append(f"{type(e).__name__}: {e}")
            # Let the exception propagate for debugging
            raise

    async def shutdown(self) -> None:
        """Gracefully shutdown pipeline with poison pills.

        Sends poison pills (None) to all workers and waits for them to complete.
        """
        self._shutdown = True

        # Send poison pills to process workers
        for _ in range(self.process_workers):
            await self.queue.put(None)

        await asyncio.gather(*self._process_tasks, return_exceptions=True)

    async def wait_completion(self) -> None:
        """Wait for all queued items to be processed."""
        await self.queue.join()

    def is_idle(self) -> bool:
        """Check if pipeline is idle (queue empty and no items processing)."""
        return self.queue.empty() and self.stats.current_queue_depth == 0
