"""
Debug Logger — Writes structured log entries to MongoDB for remote debugging.
Captures WARNING and above from all gateway.* loggers.
"""
import logging
import traceback
from datetime import datetime, timezone
from collections import deque

logger = logging.getLogger("gateway.debug_log")

# In-memory ring buffer for fast reads (last 500 entries)
_ring_buffer = deque(maxlen=500)

# Reference to the DB — set on startup
_db = None


def init_debug_logger(db):
    """Install the MongoDB log handler on the root gateway logger."""
    global _db
    _db = db
    handler = MongoLogHandler(db)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(message)s"))
    # Attach to the gateway root logger so all gateway.* children propagate here
    gateway_logger = logging.getLogger("gateway")
    gateway_logger.addHandler(handler)
    logger.info("Debug logger initialized — WARNING+ logs will be persisted to MongoDB")


class MongoLogHandler(logging.Handler):
    """Async-safe log handler that writes to MongoDB and a ring buffer."""

    def __init__(self, db):
        super().__init__()
        self._db = db

    def emit(self, record):
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "component": record.name,
                "message": record.getMessage(),
                "func": f"{record.filename}:{record.lineno}",
            }

            # Capture traceback if present
            if record.exc_info and record.exc_info[0]:
                entry["traceback"] = traceback.format_exception(*record.exc_info)

            # Write to ring buffer (sync, always works)
            _ring_buffer.append(entry)

            # Write to MongoDB (fire-and-forget via the event loop)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._write_to_db(entry))
            except RuntimeError:
                pass  # No event loop — skip DB write, ring buffer still has it

        except Exception:
            self.handleError(record)

    async def _write_to_db(self, entry):
        try:
            await self._db.debug_logs.insert_one(entry)
            # Keep only last 2000 entries in DB
            count = await self._db.debug_logs.count_documents({})
            if count > 2000:
                oldest = await self._db.debug_logs.find(
                    {}, {"_id": 1}
                ).sort("timestamp", 1).limit(count - 2000).to_list(count - 2000)
                if oldest:
                    ids = [d["_id"] for d in oldest]
                    await self._db.debug_logs.delete_many({"_id": {"$in": ids}})
        except Exception:
            pass  # Never let DB errors crash the app


async def get_recent_logs(db, limit=100, level=None, component=None):
    """Fetch recent log entries from MongoDB."""
    query = {}
    if level:
        query["level"] = level.upper()
    if component:
        query["component"] = {"$regex": component, "$options": "i"}

    cursor = db.debug_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    logs = await cursor.to_list(limit)
    logs.reverse()  # Oldest first
    return logs


async def get_buffered_logs(limit=100, level=None, component=None):
    """Fetch from the in-memory ring buffer (fast, no DB needed)."""
    entries = list(_ring_buffer)
    if level:
        entries = [e for e in entries if e["level"] == level.upper()]
    if component:
        comp_lower = component.lower()
        entries = [e for e in entries if comp_lower in e["component"].lower()]
    return entries[-limit:]


async def clear_logs(db):
    """Clear all debug logs from DB and memory."""
    result = await db.debug_logs.delete_many({})
    _ring_buffer.clear()
    return result.deleted_count
