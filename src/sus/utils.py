"""Utility functions."""

import logging

from rich.logging import RichHandler


def setup_logging(verbose: bool = False) -> None:
    """Setup logging with RichHandler for beautiful console output.

    Args:
        verbose: If True, sets logging to DEBUG level and shows file paths.
                If False, sets logging to INFO level and suppresses noisy loggers.
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Configure RichHandler
    handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=verbose,  # Only show file path in verbose mode
    )

    # Setup format
    formatter = logging.Formatter(
        "%(message)s",
        datefmt="[%X]",
    )
    handler.setFormatter(formatter)

    # Apply to root logger
    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True,  # Override any existing config
    )

    # Suppress noisy loggers unless verbose
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
