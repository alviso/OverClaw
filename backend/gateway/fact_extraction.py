"""
Fact Extraction — The sole path for storing memories.

All content (conversations, emails, screen captures) is distilled through
Claude Haiku 4.5 into discrete, searchable facts before storage.
Raw content is never stored in memory.
"""
import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from anthropic import AsyncAnthropic

logger = logging.getLogger("gateway.fact_extraction")

EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

EXTRACTION_PROMPT = """Extract discrete, self-contained facts from this content.
Each fact should be a single, clear statement that stands on its own.
Categorize each as: "fact", "decision", "action_item", "preference", or "summary".

Rules:
- Only extract information that is explicitly stated or clearly implied
- Each fact must be independently understandable without the original context
- Skip greetings, pleasantries, filler, and pure test messages ("hello", "what is 2+2")
- If the content involves browsing a URL or reading a document, extract a concise summary of the key content as a [summary] fact. Include the URL or document name.
- For screen captures, extract what application/page is shown and any notable data points
- For emails, extract the key message, who it's from, and any dates/actions mentioned
- If there is truly nothing worth remembering, return NONE
- Keep each fact to 1-2 sentences max

Format: one fact per line, prefixed with the category in brackets:
[fact] Peter's email extension is ext_mkoval
[decision] The team will use React for the frontend
[action_item] Schedule a meeting with Sarah about the Q3 roadmap
[preference] User prefers dark mode interfaces
[summary] https://news.ycombinator.com — Top HN stories: AI code editors, PostgreSQL tuning, new Rust framework

Content:
{content}"""


class FactExtractor:
    """Extract structured facts from any content using Haiku 4.5."""

    def __init__(self):
        self._client: Optional[AsyncAnthropic] = None

    def _get_client(self) -> AsyncAnthropic:
        if not self._client:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY required for fact extraction")
            self._client = AsyncAnthropic(api_key=api_key)
        return self._client

    async def extract_facts(self, content: str) -> list[dict]:
        """Extract discrete facts from content.
        Returns list of {"text": "...", "type": "fact|decision|action_item|preference|summary"}
        """
        client = self._get_client()

        response = await client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.format(content=content[:4500]),
            }],
        )

        text = response.content[0].text.strip()
        if text.upper() == "NONE" or not text:
            return []

        facts = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or not line.startswith("["):
                continue
            bracket_end = line.find("]")
            if bracket_end > 0:
                category = line[1:bracket_end].strip().lower()
                fact_text = line[bracket_end + 1:].strip()
                if fact_text and category in ("fact", "decision", "action_item", "preference", "summary"):
                    facts.append({"text": fact_text, "type": category})

        return facts


async def extract_and_store_facts(
    db,
    session_id: str,
    agent_id: str,
    user_message: str,
    assistant_response: str,
):
    """After an agent turn, extract facts and store them. No raw content is saved."""
    if len(assistant_response) < 80:
        return

    content = f"User: {user_message[:500]}\nAssistant: {assistant_response[:4000]}"

    try:
        extractor = FactExtractor()
        facts = await extractor.extract_facts(content)

        if not facts:
            return

        from gateway.memory import MemoryManager
        mgr = MemoryManager(db)

        stored = 0
        for fact in facts:
            existing = await mgr.search_memory(fact["text"], agent_id=agent_id, top_k=1, threshold=0.92)
            if existing:
                logger.debug(f"Dedupe skip (sim={existing[0]['similarity']}): {fact['text'][:60]}")
                continue

            await mgr.store_memory(
                content=fact["text"],
                session_id=session_id,
                agent_id=agent_id,
                source="fact_extraction",
                metadata={"type": fact["type"], "extracted_from": "conversation"},
            )
            stored += 1

        if stored:
            logger.info(f"Extracted {stored} facts from conversation (agent={agent_id})")

    except Exception as e:
        logger.warning(f"Fact extraction failed: {e}")


async def migrate_raw_memories_to_facts(db) -> dict:
    """
    One-time migration: convert all raw memories into distilled facts, then delete originals.
    Runs as a background task on startup. Idempotent — only processes non-fact sources.
    """
    from gateway.memory import MemoryManager

    # Find all raw memories (anything that isn't already a fact or manual entry)
    query = {
        "source": {"$nin": ["fact_extraction", "manual"]},
        "metadata.migrated_to_facts": {"$ne": True},
    }
    total = await db.memories.count_documents(query)
    if total == 0:
        return {"status": "nothing_to_migrate", "total": 0}

    logger.info(f"Migrating {total} raw memories to facts...")

    extractor = FactExtractor()
    mgr = MemoryManager(db)
    processed = 0
    facts_created = 0
    deleted = 0

    cursor = db.memories.find(query, {"embedding": 0}).limit(500)
    batch = await cursor.to_list(500)

    for doc in batch:
        doc_id = doc["_id"]
        content = doc.get("content", "")
        agent_id = doc.get("agent_id", "default")
        session_id = doc.get("session_id", "unknown")
        source = doc.get("source", "unknown")

        try:
            facts = await extractor.extract_facts(content)

            for fact in facts:
                existing = await mgr.search_memory(fact["text"], agent_id=agent_id, top_k=1, threshold=0.92)
                if existing:
                    continue

                await mgr.store_memory(
                    content=fact["text"],
                    session_id=session_id,
                    agent_id=agent_id,
                    source="fact_extraction",
                    metadata={"type": fact["type"], "extracted_from": source, "migrated": True},
                )
                facts_created += 1

            # Delete the original raw memory
            await db.memories.delete_one({"_id": doc_id})
            deleted += 1
            processed += 1

            # Rate limit
            if processed % 10 == 0:
                await asyncio.sleep(1)
                logger.info(f"Migration progress: {processed}/{total}, {facts_created} facts created")

        except Exception as e:
            logger.warning(f"Migration failed for {doc_id}: {e}")
            # Mark as attempted so we don't retry endlessly
            await db.memories.update_one(
                {"_id": doc_id},
                {"$set": {"metadata.migrated_to_facts": True}},
            )

    # Rebuild FAISS index after migration
    await mgr.initialize_index()

    result = {
        "status": "complete",
        "total": total,
        "processed": processed,
        "facts_created": facts_created,
        "deleted": deleted,
    }
    logger.info(f"Migration complete: {result}")
    return result
