"""
Fact Extraction — converts raw Q&A memories into discrete, searchable facts.

Uses Claude Haiku 4.5 (cheap/fast) to extract structured facts from conversation pairs.
Supports reprocessing of existing memories via an API endpoint.
"""
import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from anthropic import AsyncAnthropic

logger = logging.getLogger("gateway.fact_extraction")

EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

EXTRACTION_PROMPT = """Extract discrete, self-contained facts from this conversation exchange.
Each fact should be a single, clear statement that stands on its own.
Categorize each fact as: "fact", "decision", "action_item", or "preference".

Rules:
- Only extract information that is explicitly stated or clearly implied
- Each fact must be independently understandable without the original context
- Skip greetings, pleasantries, and filler
- If there are no substantive facts, return NONE
- Keep each fact to 1-2 sentences max

Format your response as one fact per line, prefixed with the category in brackets:
[fact] Peter's email extension is ext_mkoval
[decision] The team will use React for the frontend
[action_item] Schedule a meeting with Sarah about the Q3 roadmap
[preference] User prefers dark mode interfaces

Conversation:
{content}"""


class FactExtractor:
    """Extract structured facts from raw conversation text using Haiku."""

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
        """Extract discrete facts from a conversation exchange.

        Returns list of {"text": "...", "type": "fact|decision|action_item|preference"}
        """
        client = self._get_client()

        response = await client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.format(content=content[:2000]),
            }],
        )

        text = response.content[0].text.strip()
        if text.upper() == "NONE" or not text:
            return []

        facts = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Parse [category] text
            if line.startswith("["):
                bracket_end = line.find("]")
                if bracket_end > 0:
                    category = line[1:bracket_end].strip().lower()
                    fact_text = line[bracket_end + 1:].strip()
                    if fact_text and category in ("fact", "decision", "action_item", "preference"):
                        facts.append({"text": fact_text, "type": category})

        return facts


async def extract_and_store_facts(
    db,
    session_id: str,
    agent_id: str,
    user_message: str,
    assistant_response: str,
):
    """
    After an agent turn, extract discrete facts and store each as a separate memory.
    Replaces the old raw Q&A storage approach.
    """
    if len(assistant_response) < 80:
        return

    content = f"User: {user_message}\nAssistant: {assistant_response[:1500]}"

    try:
        extractor = FactExtractor()
        facts = await extractor.extract_facts(content)

        if not facts:
            return

        from gateway.memory import MemoryManager
        mgr = MemoryManager(db)

        stored = 0
        for fact in facts:
            # Dedupe: check if a very similar fact already exists
            existing = await mgr.search_memory(fact["text"], agent_id=agent_id, top_k=1, threshold=0.92)
            if existing:
                logger.debug(f"Fact already exists (sim={existing[0]['similarity']}): {fact['text'][:60]}")
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
            logger.info(f"Extracted {stored} new facts from conversation (agent={agent_id})")

    except Exception as e:
        logger.warning(f"Fact extraction failed: {e}")


async def reprocess_memories(db, batch_size: int = 10, progress_callback=None) -> dict:
    """
    Reprocess existing raw Q&A memories into discrete facts.
    - Finds memories with source='conversation' that contain 'Q:' and 'A:' patterns
    - Extracts facts from each
    - Stores new fact memories, marks originals as reprocessed
    - Idempotent: skips already-reprocessed memories
    """
    from gateway.memory import MemoryManager

    query = {
        "source": "conversation",
        "metadata.reprocessed": {"$ne": True},
        "content": {"$regex": "^Q: "},
    }
    total = await db.memories.count_documents(query)
    if total == 0:
        return {"total": 0, "processed": 0, "facts_created": 0, "skipped": 0, "status": "nothing_to_reprocess"}

    extractor = FactExtractor()
    mgr = MemoryManager(db)
    processed = 0
    facts_created = 0
    errors = 0

    cursor = db.memories.find(query, {"_id": 1, "content": 1, "agent_id": 1, "session_id": 1}).limit(500)
    batch = await cursor.to_list(500)

    for doc in batch:
        try:
            facts = await extractor.extract_facts(doc["content"])

            for fact in facts:
                # Dedupe
                existing = await mgr.search_memory(fact["text"], agent_id=doc.get("agent_id", "default"), top_k=1, threshold=0.92)
                if existing:
                    continue

                await mgr.store_memory(
                    content=fact["text"],
                    session_id=doc.get("session_id", "unknown"),
                    agent_id=doc.get("agent_id", "default"),
                    source="fact_extraction",
                    metadata={"type": fact["type"], "extracted_from": "reprocessing", "original_id": str(doc["_id"])},
                )
                facts_created += 1

            # Mark original as reprocessed (don't delete — keep for audit)
            await db.memories.update_one(
                {"_id": doc["_id"]},
                {"$set": {"metadata.reprocessed": True, "metadata.reprocessed_at": datetime.now(timezone.utc).isoformat()}},
            )
            processed += 1

            if progress_callback:
                await progress_callback(processed, total, facts_created)

            # Rate limit to avoid hammering the API
            if processed % batch_size == 0:
                await asyncio.sleep(1)

        except Exception as e:
            logger.warning(f"Reprocessing failed for memory {doc['_id']}: {e}")
            errors += 1

    return {
        "total": total,
        "processed": processed,
        "facts_created": facts_created,
        "errors": errors,
        "status": "complete",
    }
