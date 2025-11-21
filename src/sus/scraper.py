"""Scraper pipeline orchestration.

Orchestrates the complete scraping workflow, coordinating crawler, converter, outputs, and
assets with Rich progress display. Main entry point: run_scraper().
"""

import asyncio
import errno
import inspect
import json
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from sus.checkpoint_manager import CheckpointManager

import aiofiles
import psutil
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from sus.assets import AssetDownloader
from sus.checkpoint_manager import CheckpointManager
from sus.config import SusConfig
from sus.converter import ContentConverter
from sus.crawler import Crawler, CrawlResult
from sus.outputs import OutputManager
from sus.pipeline import MemoryAwareQueue, Pipeline
from sus.plugins import PluginHook
from sus.plugins.manager import PluginManager


class ScraperStats(TypedDict):
    """Type definition for scraper statistics dictionary."""

    pages_crawled: int
    pages_failed: int
    assets_downloaded: int
    assets_skipped: int
    assets_failed: int
    total_bytes: int
    files: list[str]
    # Allow Any for error dict values (includes errno as int)
    errors: dict[str, list[dict[str, Any]]]
    stopped_reason: NotRequired[str]  # Only set when scraping stops early


@dataclass
class PagePreview:
    """Preview information for a single page."""

    url: str
    output_path: str
    title: str | None = None


@dataclass
class AssetPreview:
    """Preview information for a single asset."""

    url: str
    output_path: str
    asset_type: str


@dataclass
class PreviewReport:
    """Complete preview report for dry-run with --preview flag.

    Contains all pages and assets that would be scraped, plus statistics.
    Exported as JSON for inspection before actual scraping.
    """

    pages: list[PagePreview] = field(default_factory=list)
    assets: list[AssetPreview] = field(default_factory=list)
    total_pages: int = 0
    total_assets: int = 0
    estimated_bytes: int = 0
    config_name: str = ""


@dataclass
class ProcessingContext:
    """Shared context for page processing (both sequential and pipeline modes)."""

    config: SusConfig
    converter: ContentConverter
    output_manager: OutputManager
    asset_downloader: AssetDownloader
    plugin_manager: PluginManager | None
    checkpoint: Any  # CheckpointManager | None
    stats: ScraperStats
    unique_assets_discovered: set[str]
    preview_report: PreviewReport | None
    dry_run: bool
    preview: bool
    max_pages: int | None


async def _invoke_plugin_hook_safe(
    plugin_manager: PluginManager | None,
    hook: PluginHook,
    console: Console,
    stats: ScraperStats | None = None,
    **kwargs: Any,
) -> Any:
    """Safely invoke a plugin hook with error handling.

    Args:
        plugin_manager: Plugin manager instance (can be None)
        hook: Plugin hook to invoke
        console: Rich console for error output
        stats: Optional stats dict to record errors in
        **kwargs: Arguments to pass to the hook

    Returns:
        Result from hook (or None if hook doesn't return anything or error occurs)
    """
    if not plugin_manager:
        return None

    try:
        return await plugin_manager.invoke_hook(hook, **kwargs)
    except Exception as e:
        # Extract context for error message (URL or file_path)
        context = kwargs.get("url") or kwargs.get("file_path", "unknown")
        console.print(f"[yellow][WARN] Plugin {hook.value} failed for {context}:[/] {e}")

        # Record error in stats if provided
        if stats is not None:
            if "plugin" not in stats["errors"]:
                stats["errors"]["plugin"] = []
            stats["errors"]["plugin"].append(
                {
                    "url": kwargs.get("url", ""),
                    "hook": hook.value,
                    "error": str(e),
                    "type": type(e).__name__,
                }
            )

        return None


async def _update_checkpoint_if_enabled(
    checkpoint: CheckpointManager | None,
    config: SusConfig,
    url: str,
    content_hash: str,
    status_code: int,
    output_path: str,
    dry_run: bool,
    preview: bool,
) -> None:
    """Update checkpoint with page information if enabled.

    Args:
        checkpoint: Checkpoint manager instance
        config: SUS configuration
        url: Page URL
        content_hash: SHA-256 content hash
        status_code: HTTP status code
        output_path: Output file path
        dry_run: If True, don't record file path
        preview: If True, don't record file path
    """
    if checkpoint and config.crawling.checkpoint.enabled:
        add_page_result = checkpoint.add_page(
            url=url,
            content_hash=content_hash,
            status_code=status_code,
            file_path=output_path if not (dry_run or preview) else "",
        )
        if inspect.iscoroutine(add_page_result):
            await add_page_result


async def _process_page(
    result: CrawlResult,
    ctx: ProcessingContext,
    progress: Progress,
    pages_task: Any,  # TaskID
    assets_task: Any,  # TaskID
    asset_tasks: list[asyncio.Task[Any]],
) -> bool:
    """Process a single crawled page (shared by sequential and pipeline modes).

    Args:
        result: Crawl result to process
        ctx: Processing context with all shared components
        progress: Rich progress bar instance
        pages_task: Pages progress task ID
        assets_task: Assets progress task ID
        asset_tasks: List to append asset download tasks to

    Returns:
        True if processing succeeded, False if failed
    """
    try:
        # Show current page being processed
        progress.console.print(
            f"[dim]→[/] {result.url} [dim]({result.status_code}) {len(result.html):,} bytes[/]"
        )

        await _invoke_plugin_hook_safe(
            ctx.plugin_manager,
            PluginHook.POST_FETCH,
            progress.console,
            url=result.url,
            html=result.html,
            status_code=result.status_code,
        )

        # Convert HTML to Markdown with frontmatter
        markdown = ctx.converter.convert(
            result.html,
            result.url,
            title=None,  # Will extract from HTML
            metadata=None,
        )

        # Rewrite links to relative paths
        markdown = ctx.output_manager.rewrite_links(markdown, result.url)

        modified_markdown = await _invoke_plugin_hook_safe(
            ctx.plugin_manager,
            PluginHook.POST_CONVERT,
            progress.console,
            stats=ctx.stats,
            url=result.url,
            markdown=markdown,
        )
        if modified_markdown is not None:
            markdown = modified_markdown

        page_bytes = len(markdown.encode("utf-8"))
        ctx.stats["total_bytes"] += page_bytes

        # Get output path (for both actual save and preview)
        output_path = ctx.output_manager.get_doc_path(result.url)

        if not ctx.dry_run and not ctx.preview:
            # Create parent directories before saving
            output_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(markdown)
            ctx.stats["files"].append(str(output_path))

            await _invoke_plugin_hook_safe(
                ctx.plugin_manager,
                PluginHook.POST_SAVE,
                progress.console,
                file_path=str(output_path),
                content_type="markdown",
            )

        # Collect preview data if preview mode
        if ctx.preview_report is not None:
            # Extract title from markdown frontmatter if available
            title = None
            if markdown.startswith("---\n"):
                try:
                    frontmatter_end = markdown.find("\n---\n", 4)
                    if frontmatter_end > 0:
                        frontmatter = markdown[4:frontmatter_end]
                        for line in frontmatter.splitlines():
                            if line.startswith("title:"):
                                title = line.split(":", 1)[1].strip().strip('"').strip("'")
                                break
                except Exception:
                    pass

            ctx.preview_report.pages.append(
                PagePreview(url=result.url, output_path=str(output_path), title=title)
            )
            ctx.preview_report.estimated_bytes += page_bytes

        ctx.stats["pages_crawled"] += 1
        progress.update(pages_task, advance=1)

        await _update_checkpoint_if_enabled(
            ctx.checkpoint,
            ctx.config,
            result.url,
            result.content_hash,
            result.status_code,
            str(output_path),
            ctx.dry_run,
            ctx.preview,
        )

        # Update total if no max_pages set (based on known work)
        if not ctx.max_pages:
            # known_total = pages we've done + pages still in queue
            known_total = ctx.stats["pages_crawled"] + result.queue_size

            # Ensure total never decreases (queue might shrink if filtered URLs)
            # and never goes below pages_crawled (guarantees 100% when queue empty)
            known_total = max(known_total, ctx.stats["pages_crawled"])

            progress.update(
                pages_task,
                total=known_total,
            )

        # Check memory usage
        if ctx.stats["pages_crawled"] % ctx.config.crawling.memory_check_interval == 0:
            process = psutil.Process()
            memory_percent = process.memory_percent()
            memory_mb = process.memory_info().rss / (1024 * 1024)

            if memory_percent > 95.0:
                progress.console.print(
                    f"[red][ERROR] CRITICAL MEMORY USAGE:[/] "
                    f"{memory_mb:.1f}MB ({memory_percent:.1f}%)"
                )
                progress.console.print("[yellow]Stopping scraper to prevent OOM crash[/]")
                ctx.stats["stopped_reason"] = "high_memory"
                return False
            elif memory_percent > 80.0:
                progress.console.print(
                    f"[yellow][WARN] High memory usage:[/] "
                    f"{memory_mb:.1f}MB ({memory_percent:.1f}%)"
                )

        # Download assets for this page
        if result.assets:
            # Collect preview data for assets
            if ctx.preview_report is not None:
                for asset_url in result.assets:
                    asset_path = ctx.output_manager.get_asset_path(asset_url)
                    # Determine asset type from URL
                    asset_type = "unknown"
                    image_exts = [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]
                    font_exts = [".woff", ".woff2", ".ttf", ".eot"]
                    if any(ext in asset_url.lower() for ext in image_exts):
                        asset_type = "image"
                    elif ".css" in asset_url.lower():
                        asset_type = "css"
                    elif ".js" in asset_url.lower():
                        asset_type = "javascript"
                    elif any(ext in asset_url.lower() for ext in font_exts):
                        asset_type = "font"

                    ctx.preview_report.assets.append(
                        AssetPreview(
                            url=asset_url,
                            output_path=str(asset_path),
                            asset_type=asset_type,
                        )
                    )

            # Only download if not in dry_run/preview mode
            if not ctx.dry_run and not ctx.preview:
                for asset_url in result.assets:
                    ctx.unique_assets_discovered.add(asset_url)

                # Update progress bar total to reflect unique assets
                progress.update(assets_task, total=len(ctx.unique_assets_discovered))

                # Download assets in background (non-blocking)
                task = asyncio.create_task(ctx.asset_downloader.download_all(result.assets))
                asset_tasks.append(task)

        return True  # Success

    except OSError as e:
        ctx.stats["pages_failed"] += 1

        if e.errno == errno.ENOSPC:
            error_type = "disk_full"
            message = f"Disk full while saving {result.url}"
            progress.console.print(f"[red][ERROR] DISK FULL[/] {message}")
            progress.console.print("[yellow]Stopping scraper - no space left on device[/]")
            ctx.stats["errors"][error_type] = ctx.stats["errors"].get(error_type, [])
            ctx.stats["errors"][error_type].append(
                {"url": result.url, "error": str(e), "errno": e.errno}
            )
            progress.update(pages_task, advance=1)
            return False  # Signal to stop
        elif e.errno == errno.EACCES:
            error_type = "permission_denied"
            message = f"Permission denied writing {result.url}"
            progress.console.print(f"[red][ERROR] PERMISSION DENIED[/] {message}")
        else:
            error_type = "disk_io"
            message = f"I/O error saving {result.url}: {e}"
            progress.console.print(f"[red][ERROR] I/O ERROR[/] {message}")

        ctx.stats["errors"][error_type] = ctx.stats["errors"].get(error_type, [])
        ctx.stats["errors"][error_type].append(
            {"url": result.url, "error": str(e), "errno": e.errno}
        )
        progress.update(pages_task, advance=1)
        return True  # Continue despite error

    except Exception as e:
        ctx.stats["pages_failed"] += 1
        ctx.stats["errors"]["conversion"] = ctx.stats["errors"].get("conversion", [])
        ctx.stats["errors"]["conversion"].append(
            {"url": result.url, "error": str(e), "type": type(e).__name__}
        )
        progress.console.print(f"[red][FAIL][/] Failed to process {result.url}: {e}")
        progress.update(pages_task, advance=1)
        return True  # Continue despite error


def _create_process_worker(
    ctx: ProcessingContext,
    progress: Progress,
    pages_task: Any,
    assets_task: Any,
    asset_tasks: list[asyncio.Task[Any]],
    checkpoint_path: Path | None,
) -> Any:
    """Create a process worker function for the pipeline.

    Returns an async function that consumes CrawlResults from a queue and processes them.

    Args:
        ctx: Processing context with all shared components
        progress: Rich progress bar instance
        pages_task: Pages progress task ID
        assets_task: Assets progress task ID
        asset_tasks: List to append asset download tasks to
        checkpoint_path: Path to checkpoint file (if checkpoint enabled)

    Returns:
        Async worker function with signature:
            async def worker(worker_id: int, queue: MemoryAwareQueue) -> None
    """

    async def process_worker(worker_id: int, queue: MemoryAwareQueue[CrawlResult]) -> None:
        """Process worker that consumes CrawlResults from queue.

        Args:
            worker_id: Worker identifier
            queue: Queue to consume from
        """
        while True:
            # Get item from queue (blocks if empty)
            result = await queue.get()

            # Poison pill - shutdown signal
            if result is None:
                queue.task_done()
                break

            try:
                # Check max_pages limit
                if ctx.max_pages and ctx.stats["pages_crawled"] >= ctx.max_pages:
                    progress.console.print(
                        f"\n[yellow]Reached max pages limit ({ctx.max_pages}), stopping...[/]"
                    )
                    queue.task_done()
                    break

                # Process the page
                success = await _process_page(
                    result=result,
                    ctx=ctx,
                    progress=progress,
                    pages_task=pages_task,
                    assets_task=assets_task,
                    asset_tasks=asset_tasks,
                )

                # If disk full, break immediately
                if not success and ctx.stats.get("stopped_reason") == "high_memory":
                    queue.task_done()
                    break

            finally:
                # Mark task as done
                queue.task_done()

    return process_worker


async def _initialize_checkpoint(
    config: SusConfig,
    resume: bool,
) -> tuple[CheckpointManager | None, Path | None]:
    """Initialize checkpoint manager if enabled.

    Args:
        config: Validated SusConfig instance
        resume: If True, resume from checkpoint

    Returns:
        Tuple of (checkpoint_manager, checkpoint_path)
    """
    from sus.backends import compute_config_hash

    checkpoint: CheckpointManager | None = None
    checkpoint_path: Path | None = None

    # Determine checkpoint path if checkpoint is enabled (regardless of resume)
    # Match OutputManager's logic: use site_dir if set, otherwise use base_dir directly
    if config.crawling.checkpoint.enabled:
        output_dir = Path(config.output.base_dir)
        if config.output.site_dir:
            output_dir = output_dir / config.output.site_dir

        checkpoint_path = output_dir / config.crawling.checkpoint.checkpoint_file

        # Try to load checkpoint if resuming
        if resume:
            checkpoint = await CheckpointManager.load(checkpoint_path, config)

            if checkpoint:
                # Validate config hash
                current_config_hash = compute_config_hash(config)
                if checkpoint.config_hash != current_config_hash:
                    console = Console()
                    console.print(
                        "[yellow][WARN] Config changed since last checkpoint - "
                        "invalidating checkpoint and starting fresh[/]"
                    )
                    await checkpoint.close()
                    checkpoint = None

        # Create new checkpoint if needed (not resuming or checkpoint invalid)
        if checkpoint is None:
            checkpoint = await CheckpointManager.create_new(checkpoint_path, config)

    return checkpoint, checkpoint_path


def _initialize_components(
    config: SusConfig,
    checkpoint: CheckpointManager | None,
    dry_run: bool,
    preview: bool,
) -> tuple[Crawler, ContentConverter, OutputManager, AssetDownloader, PluginManager | None]:
    """Initialize all scraper components.

    Args:
        config: Validated SusConfig instance
        checkpoint: Checkpoint manager if enabled
        dry_run: If True, don't write files
        preview: If True, preview mode

    Returns:
        Tuple of (crawler, converter, output_manager, asset_downloader, plugin_manager)
    """
    crawler = Crawler(config, checkpoint=checkpoint)
    converter = ContentConverter(config.output.markdown)
    output_manager = OutputManager(config, dry_run=(dry_run or preview))
    asset_downloader = AssetDownloader(
        config,
        output_manager,
        client=None,  # Will create its own
    )

    plugin_manager: PluginManager | None = None
    if config.plugins.enabled:
        try:
            plugin_manager = PluginManager(config.plugins)
        except Exception as e:
            console = Console()
            console.print(f"[red][ERROR] Failed to initialize plugins:[/] {e}")
            console.print("[yellow]Continuing without plugins...[/]")

    return crawler, converter, output_manager, asset_downloader, plugin_manager


async def _finalize_scrape(
    asset_tasks: list[asyncio.Task[Any]],
    asset_downloader: AssetDownloader,
    output_manager: OutputManager,
    stats: ScraperStats,
    plugin_manager: PluginManager | None,
    console: Console,
) -> None:
    """Wait for background asset downloads and update final statistics.

    Args:
        asset_tasks: List of background asset download tasks
        asset_downloader: Asset downloader instance
        output_manager: Output manager for path resolution
        stats: Statistics dictionary to update
        plugin_manager: Plugin manager if enabled
        console: Rich console for output
    """
    if asset_tasks:
        console.print(
            f"\n[yellow][WAIT] Waiting for {len(asset_tasks)} background asset processing "
            "tasks to complete...[/]"
        )
        try:
            # Gather all tasks and collect results
            task_results = await asyncio.gather(*asset_tasks, return_exceptions=True)

            # Log any asset download failures
            for idx, task_result in enumerate(task_results):
                if isinstance(task_result, Exception):
                    console.print(
                        f"[yellow]Warning:[/] Asset download task {idx + 1} failed: {task_result}"
                    )

            stats["assets_downloaded"] = asset_downloader.stats.downloaded
            stats["assets_skipped"] = asset_downloader.stats.skipped
            stats["assets_failed"] = asset_downloader.stats.failed
            # total_bytes already updated during crawling

            for asset_url in asset_downloader.downloaded:
                asset_path = output_manager.get_asset_path(asset_url)
                stats["files"].append(str(asset_path))

                await _invoke_plugin_hook_safe(
                    plugin_manager,
                    PluginHook.POST_SAVE,
                    console,
                    file_path=str(asset_path),
                    content_type="asset",
                )

            console.print("[green][OK][/] All asset downloads completed")

        except Exception as e:
            console.print(f"[red]Error waiting for asset downloads:[/] {e}")


async def run_scraper(
    config: SusConfig,
    dry_run: bool = False,
    max_pages: int | None = None,
    preview: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Run the complete scraping pipeline.

    Args:
        config: Validated SusConfig instance
        dry_run: If True, don't write files to disk
        max_pages: Maximum number of pages to crawl (None = unlimited)
        preview: If True, return summary without writing files
        resume: If True, resume from checkpoint (requires checkpoint.enabled=True in config)

    Returns:
        Dictionary with scraping statistics:
        - pages_crawled: Number of pages successfully crawled
        - pages_failed: Number of pages that failed
        - assets_downloaded: Number of assets downloaded
        - assets_failed: Number of assets that failed
        - total_bytes: Total bytes downloaded
        - execution_time: Time taken in seconds
        - errors: Dict of error types and their occurrences
        - files: List of file paths that were written

    Workflow:
        1. Initialize components (crawler, converter, output manager, asset downloader)
        2. Setup Rich progress display with two progress bars
        3. Iterate over crawler results:
           - Convert HTML to Markdown
           - Rewrite links to relative paths
           - Save markdown file (skip if dry_run/preview)
           - Download assets for the page
           - Update progress bars
        4. Display final summary with statistics and errors
        5. Return summary dict for programmatic access
    """
    checkpoint, checkpoint_path = await _initialize_checkpoint(config, resume)

    crawler, converter, output_manager, asset_downloader, plugin_manager = _initialize_components(
        config, checkpoint, dry_run, preview
    )

    console = Console()
    start_time = time.time()

    # Statistics tracking
    stats: ScraperStats = {
        "pages_crawled": 0,
        "pages_failed": 0,
        "assets_downloaded": 0,
        "assets_skipped": 0,
        "assets_failed": 0,
        "total_bytes": 0,
        "files": [],
        "errors": defaultdict(list),
    }

    # Track unique assets discovered for accurate progress bar
    unique_assets_discovered: set[str] = set()

    asset_tasks: list[asyncio.Task[Any]] = []

    # Preview report (only used if preview=True)
    preview_report: PreviewReport | None = None
    if preview:
        preview_report = PreviewReport(config_name=config.name)

    _print_header(console, config, dry_run, preview, max_pages)

    if plugin_manager:
        try:
            await plugin_manager.invoke_hook(PluginHook.PRE_CRAWL, config=config)
        except Exception as e:
            console.print(f"[yellow][WARN] Plugin PRE_CRAWL hook failed:[/] {e}")

    ctx = ProcessingContext(
        config=config,
        converter=converter,
        output_manager=output_manager,
        asset_downloader=asset_downloader,
        plugin_manager=plugin_manager,
        checkpoint=checkpoint,
        stats=stats,
        unique_assets_discovered=unique_assets_discovered,
        preview_report=preview_report,
        dry_run=dry_run,
        preview=preview,
        max_pages=max_pages,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    ) as progress:
        # If max_pages is set, we know the total; otherwise start with initial queue size
        # Start with number of start_urls as initial estimate
        # This will be updated dynamically as we crawl
        pages_total = max_pages or max(len(config.site.start_urls), 1)

        pages_task = progress.add_task(
            "[cyan]Crawling pages",
            total=pages_total,
        )
        assets_task = progress.add_task(
            "[green]Downloading assets",
            total=0,  # Will update as we discover assets
            completed=0,
        )

        try:
            if config.crawling.pipeline.enabled:
                progress.console.print(
                    "[cyan]Pipeline mode enabled - using concurrent processing[/]"
                )

                # Calculate worker count (default: min(10, cpu_count))
                worker_count = config.crawling.pipeline.process_workers
                if worker_count is None:
                    worker_count = min(10, os.cpu_count() or 4)

                progress.console.print(f"[cyan]Starting {worker_count} process workers[/]")

                # Create pipeline
                pipeline = Pipeline(
                    process_workers=worker_count,
                    queue_maxsize=config.crawling.pipeline.queue_maxsize,
                    max_queue_memory_mb=config.crawling.pipeline.max_queue_memory_mb,
                )

                # Create process worker function
                process_worker_fn = _create_process_worker(
                    ctx=ctx,
                    progress=progress,
                    pages_task=pages_task,
                    assets_task=assets_task,
                    asset_tasks=asset_tasks,
                    checkpoint_path=checkpoint_path,
                )

                # Start workers
                await pipeline.start_workers(process_worker_fn)

                # Feed results from crawler to pipeline queue
                async for result in crawler.crawl():
                    # Enqueue result for processing
                    await pipeline.enqueue(result)

                    # Check if we should stop (max_pages limit handled by workers)
                    if stats.get("stopped_reason"):
                        break

                # Shutdown pipeline gracefully (poison pills)
                await pipeline.shutdown()

                progress.console.print("[cyan]Pipeline workers finished[/]")

            else:
                async for result in crawler.crawl():
                    # Check max_pages limit
                    if max_pages and stats["pages_crawled"] >= max_pages:
                        progress.console.print(
                            f"\n[yellow]Reached max pages limit ({max_pages}), stopping...[/]"
                        )
                        break

                    # Process the page using shared helper function
                    success = await _process_page(
                        result=result,
                        ctx=ctx,
                        progress=progress,
                        pages_task=pages_task,
                        assets_task=assets_task,
                        asset_tasks=asset_tasks,
                    )

                    if checkpoint and config.crawling.checkpoint.enabled:
                        checkpoint.queue = crawler.get_queue_snapshot()

                        # Periodically save checkpoint (every N pages)
                        if (
                            stats["pages_crawled"]
                            % config.crawling.checkpoint.checkpoint_interval_pages
                            == 0
                        ) and checkpoint_path:
                            await checkpoint.save(checkpoint_path)
                            progress.console.print(
                                f"[dim][CHECKPOINT] Saved at {stats['pages_crawled']} pages[/]"
                            )

                    # Check if we should stop (disk full, memory critical)
                    if not success and (
                        stats.get("stopped_reason") == "high_memory"
                        or stats["errors"].get("disk_full")
                    ):
                        break

        except KeyboardInterrupt:
            progress.console.print("\n[yellow]Interrupted by user[/]")
        except Exception as e:
            progress.console.print(f"\n[red]Fatal error during crawl: {e}[/]")
            stats["errors"]["fatal"].append({"error": str(e), "type": type(e).__name__})
        finally:
            if checkpoint and config.crawling.checkpoint.enabled and checkpoint_path:
                try:
                    checkpoint.queue = crawler.get_queue_snapshot()
                    await checkpoint.save(checkpoint_path)
                    page_count = await checkpoint.get_page_count()
                    console.print(
                        f"[dim][CHECKPOINT] Final checkpoint saved ({page_count} pages)[/]"
                    )
                except Exception as e:
                    console.print(f"[yellow][WARN] Failed to save final checkpoint:[/] {e}")

    execution_time = time.time() - start_time

    # Collect crawler errors
    if crawler.stats.error_counts:
        for error_type, count in crawler.stats.error_counts.items():
            for _ in range(count):
                stats["errors"]["network"].append({"error": error_type, "type": error_type})

    # Collect asset downloader errors
    if asset_downloader.stats.errors:
        for error_type, error_list in asset_downloader.stats.errors.items():
            # Extend with all errors from this type
            if "asset_download" not in stats["errors"]:
                stats["errors"]["asset_download"] = []
            for error_dict in error_list:
                # Add error_type to each error dict for consistency
                error_with_type = error_dict.copy()
                error_with_type["type"] = error_type
                stats["errors"]["asset_download"].append(error_with_type)

    # Wait for all background asset downloads to complete
    await _finalize_scrape(
        asset_tasks, asset_downloader, output_manager, stats, plugin_manager, console
    )

    # Export preview report to JSON if preview mode
    if preview_report is not None:
        preview_report.total_pages = len(preview_report.pages)
        preview_report.total_assets = len(preview_report.assets)

        # Convert to dict and export
        report_dict = asdict(preview_report)
        preview_file = Path("preview-report.json")
        async with aiofiles.open(preview_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(report_dict, indent=2))

        console.print(
            f"\n[green][OK][/] Preview report exported to: [cyan]{preview_file.absolute()}[/]"
        )

    process = psutil.Process()
    final_memory_mb = process.memory_info().rss / (1024 * 1024)
    final_memory_percent = process.memory_percent()

    if plugin_manager:
        try:
            await plugin_manager.invoke_hook(PluginHook.POST_CRAWL, stats=stats)
        except Exception as e:
            console.print(f"[yellow][WARN] Plugin POST_CRAWL hook failed:[/] {e}")

    # Collect plugin errors into stats
    if plugin_manager and plugin_manager.errors:
        if "plugin" not in stats["errors"]:
            stats["errors"]["plugin"] = []
        stats["errors"]["plugin"].extend(plugin_manager.errors)

    # Display final summary
    _print_summary(console, stats, execution_time, config, dry_run, preview)

    # Return summary dict
    summary = {
        "pages_crawled": stats["pages_crawled"],
        "pages_failed": stats["pages_failed"],
        "assets_downloaded": stats["assets_downloaded"],
        "assets_skipped": stats["assets_skipped"],
        "assets_failed": stats["assets_failed"],
        "total_bytes": stats["total_bytes"],
        "execution_time": execution_time,
        "errors": dict(stats["errors"]),
        "files": stats["files"],
        "final_memory_mb": final_memory_mb,
        "final_memory_percent": final_memory_percent,
    }

    # Include stopped_reason if scraper stopped early
    if "stopped_reason" in stats:
        summary["stopped_reason"] = stats["stopped_reason"]

    return summary


def _print_header(
    console: Console,
    config: SusConfig,
    dry_run: bool,
    preview: bool,
    max_pages: int | None,
) -> None:
    """Print initial header with configuration info.

    Args:
        console: Rich console for output
        config: SUS configuration
        dry_run: Whether this is a dry run
        preview: Whether this is preview mode
        max_pages: Maximum pages limit
    """
    # Show mode banner
    if preview:
        console.print(Panel("[bold yellow]PREVIEW MODE[/] - No files will be written"))
    elif dry_run:
        console.print(Panel("[bold yellow]DRY RUN MODE[/] - No files will be written"))

    # Show configuration
    console.print()
    console.print(f"[bold cyan]Site:[/] {config.name}")
    if config.description:
        console.print(f"[dim]{config.description}[/]")
    console.print()

    # Show start URLs
    console.print("[bold]Start URLs:[/]")
    for url in config.site.start_urls:
        console.print(f"  • {url}")
    console.print()

    # Show output directory
    output_dir = Path(config.output.base_dir)
    if config.output.site_dir:
        output_dir = output_dir / config.output.site_dir
    console.print(f"[bold]Output directory:[/] {output_dir}")
    console.print(f"  • Docs: {output_dir / config.output.docs_dir}")
    console.print(f"  • Assets: {output_dir / config.output.assets_dir}")
    console.print()

    # Show limits
    if max_pages:
        console.print(f"[bold]Max pages:[/] {max_pages}")
    if config.crawling.max_pages:
        console.print(f"[bold]Config max pages:[/] {config.crawling.max_pages}")
    if max_pages or config.crawling.max_pages:
        console.print()

    console.print("[bold green]Starting crawl...[/]\n")


def _build_summary_table(
    stats: ScraperStats,
    execution_time: float,
) -> Table:
    """Build the main statistics summary table.

    Args:
        stats: Statistics dictionary
        execution_time: Time taken in seconds

    Returns:
        Rich Table with summary statistics
    """
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Metric", style="cyan", no_wrap=True)
    summary_table.add_column("Value", style="green bold")

    summary_table.add_row("Pages crawled", str(stats["pages_crawled"]))
    if stats["pages_failed"] > 0:
        summary_table.add_row("Pages failed", f"[red]{stats['pages_failed']}[/red]")
    else:
        summary_table.add_row("Pages failed", "0")

    summary_table.add_row("Assets downloaded", str(stats["assets_downloaded"]))
    if stats["assets_skipped"] > 0:
        summary_table.add_row("Assets skipped", f"[yellow]{stats['assets_skipped']}[/yellow]")
    if stats["assets_failed"] > 0:
        summary_table.add_row("Assets failed", f"[red]{stats['assets_failed']}[/red]")
    else:
        summary_table.add_row("Assets failed", "0")

    # Format total size
    total_mb = stats["total_bytes"] / (1024 * 1024)
    size_str = f"{stats['total_bytes'] / 1024:.1f} KB" if total_mb < 0.1 else f"{total_mb:.2f} MB"
    summary_table.add_row("Total size", size_str)

    # Execution time
    if execution_time < 60:
        time_str = f"{execution_time:.2f}s"
    else:
        minutes = int(execution_time // 60)
        seconds = execution_time % 60
        time_str = f"{minutes}m {seconds:.1f}s"
    summary_table.add_row("Execution time", time_str)

    if stats["pages_crawled"] > 0 and execution_time > 0:
        pages_per_sec = stats["pages_crawled"] / execution_time
        summary_table.add_row("Speed", f"{pages_per_sec:.2f} pages/sec")

    return summary_table


def _build_error_table(stats: ScraperStats) -> Table | None:
    """Build the error summary table.

    Args:
        stats: Statistics dictionary with errors

    Returns:
        Rich Table with error summary, or None if no errors
    """
    # Check if there are any errors
    if not any(len(errors) > 0 for errors in stats["errors"].values()):
        return None

    error_table = Table(show_header=True, box=None)
    error_table.add_column("Type", style="yellow", no_wrap=True)
    error_table.add_column("Count", style="red", justify="right")
    error_table.add_column("Examples", style="dim")

    for error_category, error_list in stats["errors"].items():
        if not error_list:
            continue

        # Group errors by type within category
        error_types: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for error in error_list:
            error_type = error.get("type", "Unknown")
            error_types[error_type].append(error)

        # Display each error type
        for error_type, instances in error_types.items():
            examples = []
            for instance in instances[:3]:
                if "url" in instance:
                    examples.append(instance["url"])
                elif "error" in instance:
                    examples.append(str(instance["error"])[:80])

            example_text = "\n".join(examples)
            if len(instances) > 3:
                example_text += f"\n... and {len(instances) - 3} more"

            error_table.add_row(
                f"{error_category}/{error_type}",
                str(len(instances)),
                example_text,
            )

    return error_table


def _print_summary(
    console: Console,
    stats: ScraperStats,
    execution_time: float,
    config: SusConfig,
    dry_run: bool,
    preview: bool,
) -> None:
    """Print final summary with statistics and errors.

    Args:
        console: Rich console for output
        stats: Statistics dictionary
        execution_time: Time taken in seconds
        config: SUS configuration
        dry_run: Whether this was a dry run
        preview: Whether this was preview mode
    """
    console.print()
    console.print("=" * 70)
    console.print("[bold green]Scraping Complete![/]\n")

    summary_table = _build_summary_table(stats, execution_time)
    console.print(summary_table)

    # Display errors if any
    error_table = _build_error_table(stats)
    if error_table is not None:
        console.print()
        console.print("[bold yellow]Errors:[/]")
        console.print(error_table)

    # Output location
    console.print()
    if not dry_run and not preview:
        output_dir = Path(config.output.base_dir)
        if config.output.site_dir:
            output_dir = output_dir / config.output.site_dir
        console.print(f"[bold]Output saved to:[/] {output_dir}")
        console.print(f"  • {len([f for f in stats['files'] if '.md' in f])} markdown files")
        console.print(f"  • {len([f for f in stats['files'] if '.md' not in f])} asset files")
    elif preview:
        console.print("[dim]Preview mode - no files were written[/]")
    elif dry_run:
        console.print("[dim]Dry run - no files were written[/]")

    console.print()
    console.print("=" * 70)
    console.print()
