"""Serialize and save the scraped data to a JSON file."""

import json
import os
import re
from datetime import datetime
from hapag_lloyd.logger import get_logger

log = get_logger()

def make_output_path(cfg: dict, folder: str = "output") -> str:
    """Build output/ORIGIN_to_DEST_CONTAINERTYPE_YYYY-MM-DD.json from the config route."""
    def slugify(s: str) -> str:
        return re.sub(r"[^\w]+", "_", s.strip().upper()).strip("_")

    origin = slugify(cfg.get("start_location", "ORIGIN"))
    dest = slugify(cfg.get("end_location", "DEST"))
    container = slugify(cfg.get("container_type", ""))
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    stem = f"{origin}_to_{dest}"
    if container:
        stem += f"_{container}"
    return os.path.join(folder, f"{stem}_{timestamp}.json")


def save_json(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"\n[done] Saved → {path}")


def build_output(cfg: dict, visual_data: dict, api_responses: list[dict], api_data: dict | None = None) -> dict:
    """Assemble the final output dict, stripping credentials from config."""
    safe_cfg = {k: v for k, v in cfg.items() if k not in ("email", "password")}

    return {
        "config": safe_cfg,
        "api_data": api_data or {},
        "visual_data": visual_data,
        "api_responses": api_responses,
    }
