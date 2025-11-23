"""Command line interface.

CLI module using Typer with Rich-formatted output for scrape, validate, init, and list
commands. All commands use Rich for styled terminal output with progress bars and tables.
"""

# ruff: noqa: B008

import asyncio
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table
from rich.traceback import install as install_rich_traceback

from sus import __version__
from sus.config import load_config
from sus.exceptions import ConfigError, SusError

install_rich_traceback(show_locals=True)

console = Console()

app = typer.Typer(
    name="sus",
    help="SUS - Simple Universal Scraper for documentation sites",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"SUS version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """SUS - Simple Universal Scraper for documentation sites."""
    pass


@app.command()
def scrape(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to YAML config file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Override output directory",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose logging",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Don't write any files (simulation mode)",
    ),
    max_pages: int | None = typer.Option(
        None,
        "--max-pages",
        help="Limit number of pages to crawl",
        min=1,
    ),
    preview: bool = typer.Option(
        False,
        "--preview",
        help="Export dry-run JSON report",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume from checkpoint (requires checkpoint.enabled in config)",
    ),
    reset_checkpoint: bool = typer.Option(
        False,
        "--reset-checkpoint",
        help="Delete checkpoint and start fresh",
    ),
    clear_cache: bool = typer.Option(
        False,
        "--clear-cache",
        help="Clear HTTP cache before scraping",
    ),
) -> None:
    """Scrape documentation site using config file.

    Loads configuration from YAML file and runs the scraper according
    to the specified rules. Use --dry-run to preview without writing files.
    Use --resume to continue from a previous checkpoint.
    """
    try:
        console.print(f"[cyan]Loading configuration from:[/cyan] {config}")
        sus_config = load_config(config)

        if output:
            sus_config.output.base_dir = output
            console.print(f"[yellow]Output directory overridden:[/yellow] {output}")

        if max_pages:
            sus_config.crawling.max_pages = max_pages
            console.print(f"[yellow]Max pages limit set:[/yellow] {max_pages}")

        if dry_run:
            console.print("[yellow]Running in dry-run mode (no files will be written)[/yellow]")

        try:
            from sus.utils import setup_logging

            setup_logging(verbose=verbose)
        except ImportError:
            # utils module not yet implemented - use basic logging
            import logging

            level = logging.DEBUG if verbose else logging.INFO
            logging.basicConfig(
                level=level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )

        if reset_checkpoint:
            # Determine checkpoint path (match scraper.py logic)
            output_dir = Path(sus_config.output.base_dir)
            if sus_config.output.site_dir:
                output_dir = output_dir / sus_config.output.site_dir

            checkpoint_file = output_dir / sus_config.crawling.checkpoint.checkpoint_file

            if checkpoint_file.exists():
                checkpoint_file.unlink()
                console.print(f"[yellow]Deleted checkpoint:[/yellow] {checkpoint_file}")
            else:
                console.print("[dim]No checkpoint found to delete - starting fresh[/dim]")

        if clear_cache:
            import shutil

            output_dir = Path(sus_config.output.base_dir)
            cache_dir = output_dir / sus_config.crawling.cache.cache_dir

            if cache_dir.exists():
                shutil.rmtree(cache_dir)
                console.print(f"[yellow]Cleared cache directory:[/yellow] {cache_dir}")
            else:
                console.print("[dim]No cache directory found - will start fresh[/dim]")

        try:
            from sus.scraper import run_scraper

            console.print(f"[green]Starting scraper:[/green] {sus_config.name}")
            console.print(f"[cyan]Start URLs:[/cyan] {', '.join(sus_config.site.start_urls)}")

            asyncio.run(
                run_scraper(
                    config=sus_config,
                    dry_run=dry_run,
                    max_pages=max_pages,
                    preview=preview,
                    resume=resume,
                )
            )

            console.print("[green]Scraping completed successfully![/green]")

        except ImportError as e:
            console.print(f"[red]Error:[/red] Scraper module not found: {e}")
            console.print("[yellow]The scraper module is not yet implemented.[/yellow]")
            raise typer.Exit(code=1) from None

    except ConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from None

    except SusError as e:
        console.print(f"[red]Scraping failed:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from None

    except KeyboardInterrupt:
        console.print("\n[yellow]Scraping interrupted by user[/yellow]")
        raise typer.Exit(code=130) from None

    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        else:
            console.print("[dim]Use --verbose to see full traceback[/dim]")
        raise typer.Exit(code=1) from None


@app.command()
def validate(
    config_path: Path = typer.Argument(
        ...,
        help="Path to YAML config file to validate",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Validate a SUS configuration file.

    Checks YAML syntax and validates all configuration fields against
    the schema. Displays detailed error messages if validation fails.
    """
    try:
        console.print(f"[cyan]Validating configuration:[/cyan] {config_path}")

        sus_config = load_config(config_path)

        console.print("[green][OK] Configuration is valid![/green]\n")

        table = Table(title="Configuration Summary")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Name", sus_config.name)
        table.add_row("Description", sus_config.description or "[dim]none[/dim]")
        table.add_row("Start URLs", str(len(sus_config.site.start_urls)))
        table.add_row("Allowed Domains", str(len(sus_config.site.allowed_domains)))
        table.add_row("Max Pages", str(sus_config.crawling.max_pages or "unlimited"))
        table.add_row("Depth Limit", str(sus_config.crawling.depth_limit or "unlimited"))
        table.add_row("Output Directory", sus_config.output.base_dir)
        table.add_row("Download Assets", "Yes" if sus_config.assets.download else "No")

        console.print(table)

    except ConfigError as e:
        console.print("[red][FAIL] Configuration validation failed:[/red]\n")
        console.print(str(e))
        raise typer.Exit(code=1) from None

    except Exception as e:
        console.print(f"[red][ERROR] Unexpected error:[/red] {e}")
        console.print_exception()
        raise typer.Exit(code=1) from None


@app.command()
def init(
    output_path: Path | None = typer.Argument(
        None,
        help="Output path for generated config file (default: config.yaml)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing file",
    ),
) -> None:
    """Create a new SUS configuration file interactively.

    Prompts for basic configuration options and generates a minimal
    YAML config file. Use this as a starting point for your scraper.
    """
    if output_path is None:
        output_path = Path("config.yaml")

    if output_path.exists() and not force:
        console.print(f"[red]Error:[/red] File already exists: {output_path}")
        console.print("[dim]Use --force to overwrite[/dim]")
        raise typer.Exit(code=1)

    try:
        console.print("[cyan]Create a new SUS configuration[/cyan]\n")

        name = typer.prompt("Project name (e.g., 'my-docs')")
        description = typer.prompt("Description (optional)", default="")
        start_url = typer.prompt("Start URL (e.g., 'https://example.com/docs/')")

        from urllib.parse import urlparse

        parsed = urlparse(start_url)
        domain = parsed.netloc

        if not domain:
            console.print("[red]Error:[/red] Invalid URL format")
            raise typer.Exit(code=1)

        config_template = {
            "name": name,
            "description": description,
            "site": {
                "start_urls": [start_url],
                "allowed_domains": [domain],
            },
            "crawling": {
                "delay_between_requests": 0.5,
                "global_concurrent_requests": 25,
                "per_domain_concurrent_requests": 5,
            },
            "output": {
                "base_dir": "output",
                "docs_dir": "docs",
                "assets_dir": "assets",
            },
            "assets": {
                "download": True,
                "types": ["image", "css", "javascript"],
            },
        }

        with output_path.open("w", encoding="utf-8") as f:
            f.write("# SUS Configuration\n")
            f.write(f"# Generated for: {name}\n\n")
            yaml.dump(config_template, f, default_flow_style=False, sort_keys=False)

        console.print(f"\n[green][OK] Configuration created:[/green] {output_path}")
        console.print("\n[dim]Next steps:[/dim]")
        console.print(f"  1. Edit {output_path} to customize settings")
        console.print(f"  2. Run: sus validate {output_path}")
        console.print(f"  3. Run: sus scrape --config {output_path}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        raise typer.Exit(code=130) from None

    except Exception as e:
        console.print(f"[red]Error creating configuration:[/red] {e}")
        console.print_exception()
        raise typer.Exit(code=1) from None


@app.command(name="list")
def list_examples() -> None:
    """List example configurations from the examples/ directory.

    Shows all available example configs with their descriptions and
    start URLs. Use these as templates for your own configurations.
    """
    try:
        # Assuming project structure: src/sus/cli.py and examples/ at root
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        examples_dir = project_root / "examples"

        if not examples_dir.exists():
            console.print("[yellow]No examples directory found[/yellow]")
            console.print(f"[dim]Expected location:[/dim] {examples_dir}")
            raise typer.Exit(code=0)

        yaml_files = list(examples_dir.glob("*.yaml")) + list(examples_dir.glob("*.yml"))

        if not yaml_files:
            console.print("[yellow]No example configurations found[/yellow]")
            raise typer.Exit(code=0)

        table = Table(title="Example Configurations")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")
        table.add_column("Start URLs", style="green")

        for yaml_file in sorted(yaml_files):
            try:
                with yaml_file.open("r", encoding="utf-8") as f:
                    config_dict = yaml.safe_load(f)

                name = config_dict.get("name", yaml_file.stem)
                description = config_dict.get("description", "[dim]no description[/dim]")
                start_urls = config_dict.get("site", {}).get("start_urls", [])

                # Format start URLs (show first one, indicate if there are more)
                if start_urls:
                    urls_str = start_urls[0]
                    if len(start_urls) > 1:
                        urls_str += f" [dim](+{len(start_urls) - 1} more)[/dim]"
                else:
                    urls_str = "[dim]none[/dim]"

                table.add_row(name, description, urls_str)

            except Exception as e:
                table.add_row(
                    yaml_file.stem,
                    f"[red]Error loading: {e}[/red]",
                    "[dim]n/a[/dim]",
                )

        console.print(table)
        console.print(f"\n[dim]Found {len(yaml_files)} example(s) in {examples_dir}[/dim]")
        console.print("\n[dim]To use an example:[/dim]")
        console.print("  sus scrape --config examples/<name>.yaml")

    except Exception as e:
        console.print(f"[red]Error listing examples:[/red] {e}")
        console.print_exception()
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
