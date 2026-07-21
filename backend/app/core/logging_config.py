"""Central logging configuration.

Provides a single ``configure_logging`` entry point, a ``get_logger`` helper,
and a small ``LogTimer`` context manager used throughout the pipeline to emit
consistent stage-timing / throughput metrics.

Two output formats are supported (``log_format`` setting):

* ``text`` — human-readable, timestamped lines (default; best for local dev).
* ``json`` — one JSON object per line, suited to log aggregation systems
  (ELK, CloudWatch Logs, Loki, ...) where structured fields (level, logger,
  extra timing/perf fields) need to be queryable rather than grep'd.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from logging import Logger

_CONFIGURED = False

_TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Standard LogRecord attributes we should NOT re-emit as "extra" fields when
# serialising to JSON (they are either already surfaced explicitly or are
# CPython internals irrelevant to log consumers).
_RESERVED_RECORD_ATTRS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys()
) | {"message", "asctime"}


class _JsonFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Surface any structured ``extra=...`` fields passed to the logger.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(value)  # ensure it is JSON-serialisable
                    payload[key] = value
                except TypeError:
                    payload[key] = str(value)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", *, log_format: str = "text") -> None:
    """Configure the root logger exactly once.

    Args:
        level: Logging level name (e.g. ``"INFO"``, ``"DEBUG"``).
        log_format: ``"text"`` (default) or ``"json"``.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    if log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(fmt=_TEXT_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    root.addHandler(handler)

    # Tame noisy third-party loggers.
    for noisy in ("uvicorn.access", "multipart", "PIL", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> Logger:
    """Return a module-scoped logger, configuring logging on first use."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)


class LogTimer:
    """Context manager that logs the wall-clock duration of a code block.

    Used across the analysis pipeline to produce consistent stage-timing and
    throughput (items/sec) metrics without scattering ``time.perf_counter()``
    calls through business logic.

    Example:
        >>> with LogTimer(logger, "motion_detection", item_count=total_frames) as t:
        ...     ...  # do work
        >>> t.elapsed_seconds  # available after the block exits
    """

    def __init__(
        self,
        logger: Logger,
        stage: str,
        *,
        item_count: int | None = None,
        item_label: str = "frames",
        level: int = logging.INFO,
    ) -> None:
        self._logger = logger
        self._stage = stage
        self._item_count = item_count
        self._item_label = item_label
        self._level = level
        self._start = 0.0
        self.elapsed_seconds = 0.0

    def __enter__(self) -> LogTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.elapsed_seconds = time.perf_counter() - self._start
        extra: dict[str, object] = {"stage": self._stage, "elapsed_seconds": round(self.elapsed_seconds, 3)}
        throughput_msg = ""
        if self._item_count is not None and self.elapsed_seconds > 0:
            throughput = self._item_count / self.elapsed_seconds
            extra["item_count"] = self._item_count
            extra["throughput_per_sec"] = round(throughput, 2)
            throughput_msg = f" ({self._item_count} {self._item_label}, {throughput:.1f}/s)"

        if exc_type is None:
            self._logger.log(
                self._level,
                "Stage '%s' completed in %.3fs%s",
                self._stage,
                self.elapsed_seconds,
                throughput_msg,
                extra=extra,
            )
        else:
            self._logger.warning(
                "Stage '%s' failed after %.3fs: %s",
                self._stage,
                self.elapsed_seconds,
                exc,
                extra=extra,
            )
