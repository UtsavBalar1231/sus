"""Benchmark pipeline mode vs sequential mode for throughput comparison.

Tests the producer-consumer pipeline implementation to validate the target
3-10x throughput improvement over sequential processing.

Usage:
    # Run default benchmark (100 pages, various worker counts)
    python benchmarks/benchmark_pipeline.py

    # Custom page count
    python benchmarks/benchmark_pipeline.py --pages 500

    # Compare specific worker counts
    python benchmarks/benchmark_pipeline.py --workers 2 5 10

    # Save results to JSON
    python benchmarks/benchmark_pipeline.py --output results.json
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psutil

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import contextlib

from sus.config import SusConfig
from sus.scraper import run_scraper


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""

    mode: str  # "sequential" or "pipeline"
    workers: int | None  # Number of workers (None for sequential)
    pages_crawled: int
    execution_time: float  # seconds
    throughput: float  # pages/sec
    memory_peak_mb: float
    memory_avg_mb: float
    speedup: float | None = None  # vs sequential baseline


@dataclass
class BenchmarkSuite:
    """Complete benchmark suite results."""

    total_pages: int
    sequential_baseline: BenchmarkResult
    pipeline_results: list[BenchmarkResult] = field(default_factory=list)
    max_speedup: float = 0.0
    avg_speedup: float = 0.0


def get_test_url(page_count: int) -> str:
    """Get test URL for benchmarking.

    Uses httpbin.org which provides a reliable test endpoint with linked pages.

    Args:
        page_count: Number of pages to crawl (approximate)

    Returns:
        Test URL string
    """
    # httpbin.org/links/n/offset generates a page with n links
    # Use min to avoid overloading httpbin.org
    link_count = min(page_count // 2, 20)
    return f"http://httpbin.org/links/{link_count}/0"


def create_benchmark_config(
    base_url: str, output_dir: Path, page_count: int, pipeline_enabled: bool, workers: int | None
) -> SusConfig:
    """Create benchmark configuration.

    Args:
        base_url: Base URL for test site
        output_dir: Output directory path
        page_count: Maximum pages to crawl
        pipeline_enabled: Enable pipeline mode
        workers: Number of workers (if pipeline enabled)

    Returns:
        Configured SusConfig instance
    """
    config_dict: dict[str, Any] = {
        "name": f"benchmark_{'pipeline' if pipeline_enabled else 'sequential'}",
        "site": {
            "start_urls": [base_url],
            "allowed_domains": ["httpbin.org"],
        },
        "crawling": {
            "max_pages": page_count,
            "delay_between_requests": 0.1,  # Be polite to httpbin.org
            "global_concurrent_requests": 25,  # Reasonable concurrency
            "per_domain_concurrent_requests": 5,
            "respect_robots_txt": False,
            "pipeline": {
                "enabled": pipeline_enabled,
                "process_workers": workers,
                "queue_maxsize": 100,
                "max_queue_memory_mb": 500,
            },
        },
        "output": {
            "base_dir": str(output_dir),
        },
        "assets": {
            "download": False,  # Skip assets for benchmark
        },
    }

    return SusConfig(**config_dict)


async def run_benchmark(
    base_url: str,
    output_dir: Path,
    page_count: int,
    pipeline_enabled: bool,
    workers: int | None,
) -> BenchmarkResult:
    """Run a single benchmark.

    Args:
        base_url: Base URL for test site
        output_dir: Output directory path
        page_count: Maximum pages to crawl
        pipeline_enabled: Enable pipeline mode
        workers: Number of workers (if pipeline enabled)

    Returns:
        BenchmarkResult with timing and throughput data
    """
    config = create_benchmark_config(base_url, output_dir, page_count, pipeline_enabled, workers)

    process = psutil.Process()
    memory_samples = []

    # Memory monitoring task
    async def monitor_memory() -> None:
        while True:
            memory_mb = process.memory_info().rss / (1024 * 1024)
            memory_samples.append(memory_mb)
            await asyncio.sleep(0.1)

    monitor_task = asyncio.create_task(monitor_memory())

    start_time = time.time()
    result = await run_scraper(config, dry_run=False)
    execution_time = time.time() - start_time

    monitor_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await monitor_task

    pages_crawled = result["pages_crawled"]
    throughput = pages_crawled / execution_time if execution_time > 0 else 0.0
    memory_peak_mb = max(memory_samples) if memory_samples else 0.0
    memory_avg_mb = statistics.mean(memory_samples) if memory_samples else 0.0

    mode = "pipeline" if pipeline_enabled else "sequential"

    return BenchmarkResult(
        mode=mode,
        workers=workers,
        pages_crawled=pages_crawled,
        execution_time=execution_time,
        throughput=throughput,
        memory_peak_mb=memory_peak_mb,
        memory_avg_mb=memory_avg_mb,
    )


async def run_benchmark_suite(
    page_count: int, worker_counts: list[int], output_file: Path | None
) -> BenchmarkSuite:
    """Run complete benchmark suite.

    Args:
        page_count: Number of pages to crawl
        worker_counts: List of worker counts to test
        output_file: Optional path to save JSON results

    Returns:
        BenchmarkSuite with all results
    """
    print("=== SUS Pipeline Benchmark Suite ===")
    print(f"Pages: {page_count}")
    print(f"Worker counts: {worker_counts}")
    print()

    print("Using httpbin.org for testing...")
    base_url = get_test_url(page_count)
    print(f"Test URL: {base_url}")
    print()

    output_base = Path("/tmp/sus_benchmark_output")
    output_base.mkdir(exist_ok=True)

    print("[1/N] Running sequential baseline...")
    sequential_output = output_base / "sequential"
    sequential_output.mkdir(exist_ok=True)
    sequential_result = await run_benchmark(
        base_url, sequential_output, page_count, pipeline_enabled=False, workers=None
    )
    print(f"  ✓ Pages crawled: {sequential_result.pages_crawled}")
    print(f"  ✓ Throughput: {sequential_result.throughput:.2f} pages/sec")
    print(f"  ✓ Time: {sequential_result.execution_time:.2f}s")
    print(f"  ✓ Memory peak: {sequential_result.memory_peak_mb:.1f} MB")
    print()

    if sequential_result.pages_crawled == 0:
        print("[red]ERROR: Sequential baseline crawled 0 pages - cannot benchmark[/]")
        print("This likely means the test site is unavailable or misconfigured.")
        sys.exit(1)

    pipeline_results = []
    for idx, workers in enumerate(worker_counts, start=2):
        print(f"[{idx}/{len(worker_counts) + 1}] Running pipeline mode (workers={workers})...")
        pipeline_output = output_base / f"pipeline_{workers}"
        pipeline_output.mkdir(exist_ok=True)

        result = await run_benchmark(
            base_url, pipeline_output, page_count, pipeline_enabled=True, workers=workers
        )

        # Calculate speedup (avoid division by zero)
        if sequential_result.throughput > 0:
            result.speedup = result.throughput / sequential_result.throughput
        else:
            result.speedup = 0.0

        print(f"  ✓ Pages crawled: {result.pages_crawled}")
        print(f"  ✓ Throughput: {result.throughput:.2f} pages/sec")
        print(f"  ✓ Time: {result.execution_time:.2f}s")
        print(f"  ✓ Memory peak: {result.memory_peak_mb:.1f} MB")
        print(f"  ✓ Speedup: {result.speedup:.2f}x")
        print()

        pipeline_results.append(result)

    speedups = [r.speedup for r in pipeline_results if r.speedup is not None and r.speedup > 0]
    max_speedup = max(speedups) if speedups else 0.0
    avg_speedup = statistics.mean(speedups) if speedups else 0.0

    suite = BenchmarkSuite(
        total_pages=page_count,
        sequential_baseline=sequential_result,
        pipeline_results=pipeline_results,
        max_speedup=max_speedup,
        avg_speedup=avg_speedup,
    )

    if output_file:
        output_data = {
            "total_pages": suite.total_pages,
            "sequential_baseline": asdict(suite.sequential_baseline),
            "pipeline_results": [asdict(r) for r in suite.pipeline_results],
            "max_speedup": suite.max_speedup,
            "avg_speedup": suite.avg_speedup,
        }
        output_file.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
        print(f"Results saved to: {output_file}")
        print()

    return suite


def print_summary(suite: BenchmarkSuite) -> None:
    """Print benchmark summary.

    Args:
        suite: BenchmarkSuite with results
    """
    print("=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)
    print()

    print(f"Total pages crawled: {suite.total_pages}")
    print()

    print("Sequential Baseline:")
    print(f"  Throughput: {suite.sequential_baseline.throughput:.2f} pages/sec")
    print(f"  Time: {suite.sequential_baseline.execution_time:.2f}s")
    print()

    print("Pipeline Results:")
    for result in suite.pipeline_results:
        print(f"  Workers: {result.workers}")
        print(f"    Throughput: {result.throughput:.2f} pages/sec")
        print(f"    Time: {result.execution_time:.2f}s")
        print(f"    Speedup: {result.speedup:.2f}x")
        print()

    print(f"Max speedup: {suite.max_speedup:.2f}x")
    print(f"Avg speedup: {suite.avg_speedup:.2f}x")
    print()

    # Validate 3-10x target
    if suite.max_speedup >= 3.0:
        print(f"✓ TARGET MET: {suite.max_speedup:.2f}x speedup (target: 3-10x)")
    else:
        print(f"✗ TARGET MISSED: {suite.max_speedup:.2f}x speedup (target: 3-10x)")

    print("=" * 70)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark pipeline mode vs sequential mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pages", type=int, default=100, help="Number of pages to crawl (default: 100)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        nargs="+",
        default=[2, 5, 10],
        help="Worker counts to test (default: 2 5 10)",
    )
    parser.add_argument("--output", type=Path, default=None, help="Save results to JSON file")

    args = parser.parse_args()

    # Run benchmark suite
    suite = asyncio.run(run_benchmark_suite(args.pages, args.workers, args.output))

    # Print summary
    print_summary(suite)


if __name__ == "__main__":
    main()
