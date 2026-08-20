"""Central logging setup.

Logs are written to logs/<IST-date>/scraper_<HHMMSS>.log as JSON lines (one
dated folder per day, Indian Standard Time), plus mirrored to the console in
plain text. JSON is used for the file so Promtail/Loki can parse level and
timestamp as labels without a regex; the trace_id/span_id fields (populated
via OTel context when a span is active) let Grafana jump from a log line to
its trace in Tempo.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone

from pythonjsonlogger import json as jsonlogger

IST = timezone(timedelta(hours=5, minutes=30))

_configured = False


class _TraceContextFilter(logging.Filter):
    """Attach the active OTel trace_id/span_id (if any) to each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                record.trace_id = format(ctx.trace_id, "032x")
                record.span_id = format(ctx.span_id, "016x")
        except Exception:
            pass
        return True


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the root "hapag_lloyd" logger once; safe to call multiple times."""
    global _configured
    logger = logging.getLogger("hapag_lloyd")

    if _configured:
        return logger

    now_ist = datetime.now(IST)
    log_dir = f"logs/{now_ist.strftime('%Y-%m-%d')}"
    import os
    os.makedirs(log_dir, exist_ok=True)

    log_file = f"{log_dir}/scraper_{now_ist.strftime('%Y-%m-%d_%H-%M-%S')}.log"

    json_formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s %(span_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(json_formatter)
    file_handler.addFilter(_TraceContextFilter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    _configured = True
    logger.info(f"Logging to {log_file}")
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("hapag_lloyd")
