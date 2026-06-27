"""Logging module for MergeMate.

Clean logging with no circular dependencies on config.
Uses loguru under the hood with structured output support.
"""

from __future__ import annotations

import logging
import os
import sys
from enum import Enum
from typing import Optional

from loguru import logger


class LogFormat(Enum):
    CONSOLE = "CONSOLE"
    JSON = "JSON"


def setup(level: str = "INFO", fmt: LogFormat = LogFormat.CONSOLE, analytics_dir: Optional[str] = None) -> None:
    """Configure MergeMate logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        fmt: Output format — CONSOLE (human-readable) or JSON (structured).
        analytics_dir: Optional directory for analytics log files.
    """
    log_level: int = logging.getLevelName(level.upper())
    if not isinstance(log_level, int):
        log_level = logging.INFO

    def _analytics_filter(record: dict) -> bool:
        return record.get("extra", {}).get("analytics", False)

    def _not_analytics_filter(record: dict) -> bool:
        return not record.get("extra", {}).get("analytics", False)

    logger.remove()

    if fmt == LogFormat.JSON:
        logger.add(
            sys.stdout,
            filter=_not_analytics_filter,
            level=log_level,
            format="{message}",
            colorize=False,
            serialize=True,
        )
    else:
        logger.add(sys.stdout, level=log_level, colorize=True, filter=_not_analytics_filter)

    if analytics_dir:
        os.makedirs(analytics_dir, exist_ok=True)
        pid = os.getpid()
        log_path = os.path.join(analytics_dir, f"mergemate.{pid}.log")
        logger.add(
            log_path,
            filter=_analytics_filter,
            level=log_level,
            format="{message}",
            colorize=False,
            serialize=True,
        )


def get() -> logger:
    """Get the configured logger instance."""
    return logger
