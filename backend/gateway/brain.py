"""
Brain Export/Import — Portable knowledge transfer between OverClaw deployments.
Exports memories, user profile, and relationships as a single JSON file.
Imports them into a fresh instance to seed the agent's knowledge.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.brain")

# Collections that form the agent's "brain"
BRAIN_COLLECTIONS = {
    "memories": {"exclude_fields": {"_id": 1, "embedding": 1}},
    "user_profiles": {"exclude_fields": {"_id": 1}},
    "relationships": {"exclude_fields": {"_id": 1}},
}


async def export_brain(db) -> dict:
    """Export all knowledge collections into a portable dict."""
    brain = {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "collections": {},
        "stats": {},
    }

    for collection_name, opts in BRAIN_COLLECTIONS.items():
        coll = db[collection_name]
        projection = {"_id": 0}
        # For memories, exclude the embedding vectors (large, can be regenerated)
        if "embedding" in opts.get("exclude_fields", {}):
            projection["embedding"] = 0

        docs = await coll.find({}, projection).to_list(10000)
        brain["collections"][collection_name] = docs
        brain["stats"][collection_name] = len(docs)

    logger.info(f"Brain exported: {brain['stats']}")
    return brain


async def import_brain(db, brain_data: dict) -> dict:
    """Import knowledge from a brain export into the database."""
    if not isinstance(brain_data, dict) or "collections" not in brain_data:
        return {"ok": False, "error": "Invalid brain file format"}

    version = brain_data.get("version", 0)
    if version != 1:
        return {"ok": False, "error": f"Unsupported brain version: {version}"}

    results = {}
    now = datetime.now(timezone.utc).isoformat()

    for collection_name in BRAIN_COLLECTIONS:
        docs = brain_data["collections"].get(collection_name, [])
        if not docs:
            results[collection_name] = {"imported": 0, "skipped": 0}
            continue

        coll = db[collection_name]
        imported = 0
        skipped = 0

        for doc in docs:
            if not isinstance(doc, dict):
                skipped += 1
                continue

            doc["imported_at"] = now

            if collection_name == "memories":
                # Dedupe by content + session_id
                existing = await coll.find_one({
                    "content": doc.get("content"),
                    "session_id": doc.get("session_id"),
                })
                if existing:
                    skipped += 1
                    continue
                # Re-embed if embedding was stripped
                if "embedding" not in doc:
                    try:
                        from gateway.memory import MemoryManager
                        mgr = MemoryManager(db)
                        doc["embedding"] = await mgr.embed_text(doc.get("content", ""))
                    except Exception as e:
                        logger.warning(f"Re-embedding failed, storing without vector: {e}")

                await coll.insert_one(doc)
                imported += 1

            elif collection_name == "user_profiles":
                # Merge facts into existing profile
                profile_id = doc.get("profile_id", "default")
                existing = await coll.find_one({"profile_id": profile_id})
                if existing:
                    # Merge facts: imported facts don't overwrite newer local ones
                    existing_facts = existing.get("facts", {})
                    incoming_facts = doc.get("facts", {})
                    for key, val in incoming_facts.items():
                        if key not in existing_facts:
                            existing_facts[key] = val
                    await coll.update_one(
                        {"profile_id": profile_id},
                        {"$set": {"facts": existing_facts, "imported_at": now}},
                    )
                else:
                    await coll.insert_one(doc)
                imported += 1

            elif collection_name == "relationships":
                # Upsert by name_key
                name_key = doc.get("name_key", "")
                if not name_key:
                    skipped += 1
                    continue
                existing = await coll.find_one({"name_key": name_key})
                if existing:
                    # Merge: keep higher mention_count, merge context_history
                    update = {}
                    if doc.get("mention_count", 0) > existing.get("mention_count", 0):
                        update["mention_count"] = doc["mention_count"]
                    if doc.get("role") and not existing.get("role"):
                        update["role"] = doc["role"]
                    if doc.get("team") and not existing.get("team"):
                        update["team"] = doc["team"]
                    # Append new context entries
                    new_contexts = doc.get("context_history", [])
                    if new_contexts:
                        existing_texts = {c.get("text") for c in existing.get("context_history", [])}
                        for ctx in new_contexts:
                            if ctx.get("text") not in existing_texts:
                                await coll.update_one(
                                    {"name_key": name_key},
                                    {"$push": {"context_history": {"$each": [ctx], "$slice": -10}}},
                                )
                    if update:
                        update["imported_at"] = now
                        await coll.update_one({"name_key": name_key}, {"$set": update})
                    skipped += 1  # existed, merged
                else:
                    await coll.insert_one(doc)
                    imported += 1

        results[collection_name] = {"imported": imported, "skipped": skipped}

    logger.info(f"Brain imported: {results}")
    return {"ok": True, "results": results}


async def get_brain_stats(db) -> dict:
    """Get counts of what's in the brain."""
    stats = {}
    for collection_name in BRAIN_COLLECTIONS:
        stats[collection_name] = await db[collection_name].count_documents({})
    return stats
