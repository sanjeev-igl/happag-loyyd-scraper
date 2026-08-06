"""Track which (route, container type) combinations have already been scraped,
so a re-run can skip them instead of re-scraping from scratch.

Each entry records whether that combination last succeeded or failed. Only
successes are skipped on resume — failed combinations are retried, since a
run left at "failed" hasn't actually produced output yet.
"""

import json
import os
from datetime import datetime, timezone

_DEFAULT_PATH = "checkpoint.json"


def _key(start_location: str, end_location: str, container_type: str) -> str:
    return f"{start_location.strip().upper()}|{end_location.strip().upper()}|{container_type.strip().upper()}"


def load_checkpoint(path: str = _DEFAULT_PATH) -> dict:
    """Return {key: entry} for every route+container-type attempted so far,
    or an empty dict if the checkpoint file doesn't exist yet."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("entries", {})


def is_done(checkpoint: dict, start_location: str, end_location: str, container_type: str) -> bool:
    """True only if this combination previously succeeded (failures are retried)."""
    entry = checkpoint.get(_key(start_location, end_location, container_type))
    return bool(entry) and entry.get("status") == "success"


def _record(
    checkpoint: dict,
    start_location: str,
    end_location: str,
    container_type: str,
    status: str,
    path: str,
    error: str | None = None,
) -> None:
    entry = {
        "start_location": start_location,
        "end_location": end_location,
        "container_type": container_type,
        "status": status,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        entry["error"] = error
    checkpoint[_key(start_location, end_location, container_type)] = entry
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"entries": checkpoint}, f, indent=2)


def mark_success(
    checkpoint: dict, start_location: str, end_location: str, container_type: str, path: str = _DEFAULT_PATH,
) -> None:
    """Record a successful scrape and persist immediately, so progress survives
    even if the run is interrupted mid-way."""
    _record(checkpoint, start_location, end_location, container_type, "success", path)


def mark_failed(
    checkpoint: dict,
    start_location: str,
    end_location: str,
    container_type: str,
    error: str = "",
    path: str = _DEFAULT_PATH,
) -> None:
    """Record a failed scrape (still retried on the next run) and persist immediately."""
    _record(checkpoint, start_location, end_location, container_type, "failed", path, error=error)
