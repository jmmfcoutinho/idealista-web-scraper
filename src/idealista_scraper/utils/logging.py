"""Logging configuration for the Idealista scraper."""

from __future__ import annotations

import logging
import sys
from typing import Literal


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    format_type: Literal["simple", "json"] = "simple",
) -> None:
    """Configure logging for the application.

    Args:
        level: The logging level to use.
        format_type: The format type for log messages. "simple" for human-readable,
            "json" for structured logs.
    """
    log_level = getattr(logging, level)

    if format_type == "simple":
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        # JSON format for production/structured logging
        formatter = logging.Formatter(
            fmt='{"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: The name for the logger, typically __name__.

    Returns:
        A configured logger instance.
    """
    return logging.getLogger(name)
