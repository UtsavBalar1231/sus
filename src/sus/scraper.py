"""Scraper pipeline orchestration.

Orchestrates the complete scraping workflow, coordinating crawler, converter, outputs, and
assets with Rich progress display. Main entry point: run_scraper().
"""

import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypedDict

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
from sus.config import SusConfig
from sus.converter import ContentConverter
from sus.crawler import Crawler
from sus.outputs import OutputManager


class ScraperStats(TypedDict):
    """Type definition for scraper statistics dictionary."""

    pages_crawled: int
    pages_failed: int
    assets_downloaded: int
    assets_failed: int
    total_bytes: int
    files: list[str]
    errors: dict[str, list[dict[str, str]]]


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


async def run_scraper(
    config: SusConfig,
    dry_run: bool = False,
    max_pages: int | None = None,
    preview: bool = False,
) -> dict[str, Any]:
    """Run the complete scraping pipeline.

    Args:
        config: Validated SusConfig instance
        dry_run: If True, don't write files to disk
        max_pages: Maximum number of pages to crawl (None = unlimited)
        preview: If True, return summary without writing files

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
    # Initialize components
    crawler = Crawler(config)
    converter = ContentConverter(config.output.markdown)
    output_manager = OutputManager(config, dry_run=(dry_run or preview))
    asset_downloader = AssetDownloader(
        config.assets,
        output_manager,
        client=None,  # Will create its own
    )

    console = Console()
    start_time = time.time()

    # Statistics tracking
    stats: ScraperStats = {
        "pages_crawled": 0,
        "pages_failed": 0,
        "assets_downloaded": 0,
        "assets_failed": 0,
        "total_bytes": 0,
        "files": [],
        "errors": defaultdict(list),
    }

    # Track unique assets discovered for accurate progress bar
    unique_assets_discovered: set[str] = set()

    # Preview report (only used if preview=True)
    preview_report: PreviewReport | None = None
    if preview:
        preview_report = PreviewReport(config_name=config.name)

    # Display initial information
    _print_header(console, config, dry_run, preview, max_pages)

    # Setup Rich Progress display
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
        # Create progress tasks
        # If max_pages is set, we know the total; otherwise start with estimate
        pages_total = max_pages if max_pages else 100
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
            # Iterate over crawler results
            async for result in crawler.crawl():
                # Check max_pages limit
                if max_pages and stats["pages_crawled"] >= max_pages:
                    progress.console.print(
                        f"\n[yellow]Reached max pages limit ({max_pages}), stopping...[/]"
                    )
                    break

                try:
                    # Show current page being processed
                    progress.console.print(
                        f"[dim]→[/] {result.url} "
                        f"[dim]({result.status_code}) "
                        f"{len(result.html):,} bytes[/]"
                    )

                    # Convert HTML to Markdown with frontmatter
                    markdown = converter.convert(
                        result.html,
                        result.url,
                        title=None,  # Will extract from HTML
                        metadata=None,
                    )

                    # Rewrite links to relative paths
                    markdown = output_manager.rewrite_links(markdown, result.url)

                    # Calculate page size
                    page_bytes = len(markdown.encode("utf-8"))
                    stats["total_bytes"] += page_bytes

                    # Get output path (for both actual save and preview)
                    output_path = output_manager.get_doc_path(result.url)

                    # Save markdown file (unless dry_run/preview)
                    if not dry_run and not preview:
                        output_path.write_text(markdown, encoding="utf-8")
                        stats["files"].append(str(output_path))

                    # Collect preview data if preview mode
                    if preview_report is not None:
                        # Extract title from markdown frontmatter if available
                        title = None
                        if markdown.startswith("---\n"):
                            try:
                                frontmatter_end = markdown.find("\n---\n", 4)
                                if frontmatter_end > 0:
                                    frontmatter = markdown[4:frontmatter_end]
                                    for line in frontmatter.splitlines():
                                        if line.startswith("title:"):
                                            title = (
                                                line.split(":", 1)[1]
                                                .strip()
                                                .strip('"')
                                                .strip("'")
                                            )
                                            break
                            except Exception:
                                pass

                        preview_report.pages.append(
                            PagePreview(url=result.url, output_path=str(output_path), title=title)
                        )
                        preview_report.estimated_bytes += page_bytes

                    # Update page statistics
                    stats["pages_crawled"] += 1
                    progress.update(pages_task, advance=1)

                    # Update total if no max_pages set (expand as we discover more)
                    if not max_pages:
                        progress.update(
                            pages_task,
                            total=stats["pages_crawled"] + 10,
                        )

                    # Download assets for this page
                    if result.assets:
                        # Collect preview data for assets
                        if preview_report is not None:
                            for asset_url in result.assets:
                                asset_path = output_manager.get_asset_path(asset_url)
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

                                preview_report.assets.append(
                                    AssetPreview(
                                        url=asset_url,
                                        output_path=str(asset_path),
                                        asset_type=asset_type,
                                    )
                                )

                        # Only download if not in dry_run/preview mode
                        if not dry_run and not preview:
                            # Add newly discovered assets to the set
                            for asset_url in result.assets:
                                unique_assets_discovered.add(asset_url)

                            # Update progress bar total to reflect unique assets
                            progress.update(assets_task, total=len(unique_assets_discovered))

                            # Download assets
                            await asset_downloader.download_all(result.assets)

                            # Update asset statistics from downloader
                            stats["assets_downloaded"] = asset_downloader.stats.downloaded
                            stats["assets_failed"] = asset_downloader.stats.failed
                            stats["total_bytes"] += asset_downloader.stats.total_bytes

                            # Update progress bar to match actual downloaded count
                            progress.update(
                                assets_task,
                                completed=asset_downloader.stats.downloaded,
                            )

                            # Add downloaded asset paths to files list
                            for asset_url in result.assets:
                                if asset_url in asset_downloader.downloaded:
                                    asset_path = output_manager.get_asset_path(asset_url)
                                    stats["files"].append(str(asset_path))

                except Exception as e:
                    # Handle page processing errors
                    stats["pages_failed"] += 1
                    stats["errors"]["conversion"].append(
                        {"url": result.url, "error": str(e), "type": type(e).__name__}
                    )
                    progress.console.print(f"[red]✗[/] Failed to process {result.url}: {e}")
                    progress.update(pages_task, advance=1)

        except KeyboardInterrupt:
            progress.console.print("\n[yellow]Interrupted by user[/]")
        except Exception as e:
            progress.console.print(f"\n[red]Fatal error during crawl: {e}[/]")
            stats["errors"]["fatal"].append({"error": str(e), "type": type(e).__name__})

    # Calculate execution time
    execution_time = time.time() - start_time

    # Collect crawler errors
    if crawler.stats.error_counts:
        for error_type, count in crawler.stats.error_counts.items():
            for _ in range(count):
                stats["errors"]["network"].append({"error": error_type, "type": error_type})

    # Collect asset downloader errors
    if asset_downloader.stats.errors:
        for error_type, count in asset_downloader.stats.errors.items():
            for _ in range(count):
                stats["errors"]["asset_download"].append({"error": error_type, "type": error_type})

    # Export preview report to JSON if preview mode
    if preview_report is not None:
        # Update totals
        preview_report.total_pages = len(preview_report.pages)
        preview_report.total_assets = len(preview_report.assets)

        # Convert to dict and export
        report_dict = asdict(preview_report)
        preview_file = Path("preview-report.json")
        preview_file.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

        console.print(
            f"\n[green]✓[/] Preview report exported to: [cyan]{preview_file.absolute()}[/]"
        )

    # Display final summary
    _print_summary(console, stats, execution_time, config, dry_run, preview)

    # Return summary dict
    return {
        "pages_crawled": stats["pages_crawled"],
        "pages_failed": stats["pages_failed"],
        "assets_downloaded": stats["assets_downloaded"],
        "assets_failed": stats["assets_failed"],
        "total_bytes": stats["total_bytes"],
        "execution_time": execution_time,
        "errors": dict(stats["errors"]),
        "files": stats["files"],
    }


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

    # Build statistics table
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Metric", style="cyan", no_wrap=True)
    summary_table.add_column("Value", style="green bold")

    # Add rows
    summary_table.add_row("Pages crawled", str(stats["pages_crawled"]))
    if stats["pages_failed"] > 0:
        summary_table.add_row("Pages failed", f"[red]{stats['pages_failed']}[/red]")
    else:
        summary_table.add_row("Pages failed", "0")

    summary_table.add_row("Assets downloaded", str(stats["assets_downloaded"]))
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

    # Calculate speed
    if stats["pages_crawled"] > 0 and execution_time > 0:
        pages_per_sec = stats["pages_crawled"] / execution_time
        summary_table.add_row("Speed", f"{pages_per_sec:.2f} pages/sec")

    console.print(summary_table)

    # Display errors if any
    if any(len(errors) > 0 for errors in stats["errors"].values()):
        console.print()
        console.print("[bold yellow]Errors:[/]")

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
                # Build example text (show up to 3 examples)
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
