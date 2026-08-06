"""Central logging setup.

Logs are written to logs/<IST-date>/scraper_<HHMMSS>.log, one dated folder per
day (Indian Standard Time) so a day's runs are easy to find and troubleshoot,
plus mirrored to the console like the old print() calls were.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

_configured = False


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

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    _configured = True
    logger.info(f"Logging to {log_file}")
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("hapag_lloyd")
