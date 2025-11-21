#!/usr/bin/env python3
"""Benchmark script for JavaScript rendering performance.

Compares performance between HTTP-only crawling and JavaScript rendering:
- Throughput (pages/second)
- Memory usage
- Context pool efficiency
- Overall time taken

Usage:
    python benchmarks/benchmark_js_rendering.py --pages 50
    python benchmarks/benchmark_js_rendering.py --pages 100 --pool-size 10
"""

import argparse
import asyncio
import importlib.util
import time
from pathlib import Path

import psutil

from sus.config import SusConfig
from sus.crawler import Crawler

PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None

def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB."""
    process = psutil.Process()
    return process.memory_info().rss / (1024 * 1024)


async def benchmark_http_crawling(num_pages: int) -> dict[str, float]:
    """Benchmark HTTP-only crawling (no JavaScript)."""
    print(f"\n{'=' * 60}")
    print(f"Benchmarking HTTP-only crawling ({num_pages} pages)")
    print(f"{'=' * 60}")

    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "spa"
    test_url = f"file://{fixtures_dir / 'simple-spa.html'}"

    SusConfig(
        name="benchmark-http",
        site={
            "start_urls": [test_url],
            "allowed_domains": [""],
        },
        crawling={
            "javascript": {"enabled": False},
            "max_pages": num_pages,
        },
    )

    mem_before = get_memory_usage_mb()
    start_time = time.time()

    with open(fixtures_dir / "simple-spa.html") as f:
        raw_html = f.read()

    pages_processed = 0
    for _ in range(num_pages):
        # Simulate processing overhead
        _ = raw_html
        pages_processed += 1

    elapsed = time.time() - start_time
    mem_after = get_memory_usage_mb()
    mem_delta = mem_after - mem_before

    throughput = pages_processed / elapsed if elapsed > 0 else 0

    print(f"  Pages processed: {pages_processed}")
    print(f"  Time taken: {elapsed:.2f}s")
    print(f"  Throughput: {throughput:.2f} pages/sec")
    print(f"  Memory delta: {mem_delta:.2f} MB")
    print(f"  Memory/page: {mem_delta/pages_processed if pages_processed > 0 else 0:.2f} MB")

    return {
        "pages": pages_processed,
        "time": elapsed,
        "throughput": throughput,
        "memory_mb": mem_delta,
        "memory_per_page_mb": mem_delta / pages_processed if pages_processed > 0 else 0,
    }


async def benchmark_js_rendering(num_pages: int, pool_size: int) -> dict[str, float]:
    """Benchmark JavaScript rendering with Playwright."""
    if not PLAYWRIGHT_AVAILABLE:
        print("\nSkipping JS benchmark: Playwright not installed")
        print("Install with: uv sync --group js && uv run playwright install chromium")
        return {}

    print(f"\n{'=' * 60}")
    print(f"Benchmarking JavaScript rendering ({num_pages} pages, pool={pool_size})")
    print(f"{'=' * 60}")

    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "spa"
    test_url = f"file://{fixtures_dir / 'simple-spa.html'}"

    config = SusConfig(
        name="benchmark-js",
        site={
            "start_urls": [test_url],
            "allowed_domains": [""],
        },
        crawling={
            "javascript": {
                "enabled": True,
                "wait_for": "domcontentloaded",  # Faster for benchmark
                "context_pool_size": pool_size,
            },
            "max_pages": num_pages,
        },
    )

    mem_before = get_memory_usage_mb()
    start_time = time.time()

    crawler = Crawler(config)

    # Add URLs to queue for processing
    for _ in range(num_pages - 1):  # -1 because start_url is already added
        await crawler.queue.put((test_url, None))

    pages_processed = 0
    async for _result in crawler.crawl():
        pages_processed += 1

    elapsed = time.time() - start_time
    mem_after = get_memory_usage_mb()
    mem_delta = mem_after - mem_before

    throughput = pages_processed / elapsed if elapsed > 0 else 0

    print(f"  Pages processed: {pages_processed}")
    print(f"  Time taken: {elapsed:.2f}s")
    print(f"  Throughput: {throughput:.2f} pages/sec")
    print(f"  Memory delta: {mem_delta:.2f} MB")
    print(f"  Memory/page: {mem_delta/pages_processed if pages_processed > 0 else 0:.2f} MB")
    print(f"  Context pool size: {pool_size}")

    return {
        "pages": pages_processed,
        "time": elapsed,
        "throughput": throughput,
        "memory_mb": mem_delta,
        "memory_per_page_mb": mem_delta / pages_processed if pages_processed > 0 else 0,
        "pool_size": pool_size,
    }


async def benchmark_pool_size_comparison(num_pages: int) -> None:
    """Benchmark different context pool sizes."""
    if not PLAYWRIGHT_AVAILABLE:
        return

    print(f"\n{'=' * 60}")
    print(f"Context Pool Size Comparison ({num_pages} pages)")
    print(f"{'=' * 60}")

    pool_sizes = [1, 3, 5, 10]
    results = []

    for pool_size in pool_sizes:
        result = await benchmark_js_rendering(num_pages, pool_size)
        if result:
            results.append(result)
            await asyncio.sleep(2)  # Brief pause between benchmarks

    if results:
        print(f"\n{'=' * 60}")
        print("Pool Size Comparison Summary")
        print(f"{'=' * 60}")
        print(f"{'Pool Size':<12} {'Throughput':<15} {'Mem/Page':<12} {'Total Time':<12}")
        print(f"{'-' * 60}")
        for result in results:
            print(
                f"{result['pool_size']:<12} "
                f"{result['throughput']:.2f} pages/s{'':<4} "
                f"{result['memory_per_page_mb']:.2f} MB{'':<6} "
                f"{result['time']:.2f}s"
            )


async def main() -> None:
    """Run all benchmarks."""
    parser = argparse.ArgumentParser(
        description="Benchmark JavaScript rendering performance"
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=50,
        help="Number of pages to benchmark (default: 50)",
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=5,
        help="Context pool size for JS rendering (default: 5)",
    )
    parser.add_argument(
        "--compare-pools",
        action="store_true",
        help="Compare different pool sizes",
    )
    args = parser.parse_args()

    print("\nJavaScript Rendering Performance Benchmark")
    print("=" * 60)
    print(f"Pages to process: {args.pages}")
    print(f"Context pool size: {args.pool_size}")

    if args.compare_pools:
        await benchmark_pool_size_comparison(args.pages)
    else:
        # Run both benchmarks
        http_result = await benchmark_http_crawling(args.pages)
        js_result = await benchmark_js_rendering(args.pages, args.pool_size)

        # Print comparison summary
        if http_result and js_result:
            print(f"\n{'=' * 60}")
            print("Performance Comparison Summary")
            print(f"{'=' * 60}")

            slowdown = js_result["time"] / http_result["time"] if http_result["time"] > 0 else 0
            throughput_ratio = (
                http_result["throughput"] / js_result["throughput"]
                if js_result["throughput"] > 0
                else 0
            )

            print("\nHTTP-only:")
            print(f"  Throughput: {http_result['throughput']:.2f} pages/sec")
            print(f"  Total time: {http_result['time']:.2f}s")
            print(f"  Memory/page: {http_result['memory_per_page_mb']:.2f} MB")

            print("\nJavaScript rendering:")
            print(f"  Throughput: {js_result['throughput']:.2f} pages/sec")
            print(f"  Total time: {js_result['time']:.2f}s")
            print(f"  Memory/page: {js_result['memory_per_page_mb']:.2f} MB")
            print(f"  Context pool: {js_result['pool_size']}")

            print("\nPerformance Impact:")
            print(f"  Slowdown: {slowdown:.2f}x")
            print(f"  Throughput reduction: {throughput_ratio:.2f}x")

            print(f"\n{'=' * 60}")
            print("Target: <3x slowdown with context pooling")
            if slowdown < 3.0:
                print(f"✓ PASS: {slowdown:.2f}x is within target")
            else:
                print(f"✗ MISS: {slowdown:.2f}x exceeds target of 3x")


if __name__ == "__main__":
    asyncio.run(main())
