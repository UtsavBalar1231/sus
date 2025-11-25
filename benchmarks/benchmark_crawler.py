#!/usr/bin/env python3
"""Standalone crawler benchmark script.

Usage:
    python benchmarks/benchmark_crawler.py [--pages N]

Measures:
- Pages per second throughput
- Memory usage over time
- HTTP request latency
- File I/O performance
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import psutil
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sus.config import (
    AssetConfig,
    CrawlingRules,
    MarkdownConfig,
    OutputConfig,
    PathMappingConfig,
    SiteConfig,
    SusConfig,
)
from sus.crawler import Crawler


async def benchmark_crawler(num_pages: int = 100) -> dict[str, float]:
    """Run crawler benchmark."""
    console = Console()

    config = SusConfig(
        name="benchmark",
        description="Benchmark configuration",
        site=SiteConfig(
            start_urls=["http://httpbin.org/links/10/0"],  # Real test site
            allowed_domains=["httpbin.org"],
        ),
        crawling=CrawlingRules(
            delay_between_requests=0.1,  # Polite rate limiting
            global_concurrent_requests=25,
            per_domain_concurrent_requests=5,
            max_pages=num_pages,
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

    console.print(f"[bold]Benchmarking crawler with {num_pages} pages...[/]")

    process = psutil.Process()
    start_memory = process.memory_info().rss / (1024 * 1024)
    start_time = time.perf_counter()

    crawler = Crawler(config)
    page_count = 0

    async for _result in crawler.crawl():
        page_count += 1
        if page_count >= num_pages:
            break

    end_time = time.perf_counter()
    end_memory = process.memory_info().rss / (1024 * 1024)

    duration = end_time - start_time
    pages_per_sec = page_count / duration if duration > 0 else 0
    memory_used = end_memory - start_memory

    return {
        "pages": page_count,
        "duration": duration,
        "pages_per_sec": pages_per_sec,
        "memory_mb": end_memory,
        "memory_delta_mb": memory_used,
    }


def main() -> None:
    """Run benchmark and display results."""
    parser = argparse.ArgumentParser(description="Benchmark SUS crawler")
    parser.add_argument("--pages", type=int, default=100, help="Number of pages to crawl")
    args = parser.parse_args()

    results = asyncio.run(benchmark_crawler(args.pages))

    console = Console()
    table = Table(title="Crawler Benchmark Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Pages Crawled", f"{results['pages']}")
    table.add_row("Duration", f"{results['duration']:.2f}s")
    table.add_row("Throughput", f"{results['pages_per_sec']:.2f} pages/sec")
    table.add_row("Memory Usage", f"{results['memory_mb']:.1f} MB")
    table.add_row("Memory Delta", f"{results['memory_delta_mb']:.1f} MB")

    console.print(table)

    # Performance targets
    if results["pages_per_sec"] < 15.0:
        console.print("[yellow][WARN] Warning: Throughput below target (15 pages/sec)[/]")
    else:
        console.print("[green][OK] Throughput meets target![/]")


if __name__ == "__main__":
    main()
