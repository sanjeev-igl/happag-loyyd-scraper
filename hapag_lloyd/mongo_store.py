"""Save scraped output dicts to MongoDB, in addition to the local JSON file."""

from pymongo import MongoClient

from hapag_lloyd.config import MONGO_URI, MONGO_DB, MONGO_COLLECTION
from hapag_lloyd.logger import get_logger

log = get_logger()
_client: MongoClient | None = None


def _get_collection():
    global _client
    if not MONGO_URI or not MONGO_DB or not MONGO_COLLECTION:
        raise ValueError("MONGO_URI, MONGO_DB, and MONGO_COLLECTION must be set (in .env).")
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client[MONGO_DB][MONGO_COLLECTION]


def save_to_mongo(data: dict) -> None:
    collection = _get_collection()
    collection.insert_one(dict(data))
    log.info(f"[done] Saved → mongodb {MONGO_DB}.{MONGO_COLLECTION}")
