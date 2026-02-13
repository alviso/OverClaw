"""
Memory / RAG — Phase 7
Long-term memory across conversations using embeddings.
Stores conversation facts as vectors in MongoDB, retrieves via cosine similarity.
Inspired by OpenClaw's src/memory/ (simplified: 1 provider, no sqlite-vec, MongoDB storage).

Flow:
1. After each agent turn, extract key facts from the conversation
2. Embed facts using OpenAI text-embedding-3-small
3. Store fact + vector in MongoDB
4. On new turns, search memory for relevant context
5. Inject top-N matches into the system prompt
"""
import os
import logging
import numpy as np
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger("gateway.memory")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
TOP_K_RESULTS = 5
SIMILARITY_THRESHOLD = 0.25


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


class MemoryManager:
    """Manages long-term memory with embeddings."""

    def __init__(self, db):
        self.db = db
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if not self._client:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise ValueError("OPENAI_API_KEY required for memory embeddings")
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        """Get embedding vector for a text string."""
        client = self._get_client()
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding

    async def store_memory(
        self,
        content: str,
        session_id: str,
        agent_id: str = "default",
        source: str = "conversation",
        metadata: dict = None,
    ) -> dict:
        """Store a memory with its embedding vector."""
        embedding = await self.embed_text(content)

        doc = {
            "content": content,
            "embedding": embedding,
            "session_id": session_id,
            "agent_id": agent_id,
            "source": source,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.memories.insert_one(doc)
        logger.info(f"Memory stored: {content[:60]}... (session={session_id})")
        return {"content": content, "session_id": session_id, "source": source}

    async def search_memory(
        self,
        query: str,
        agent_id: str = None,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> list[dict]:
        """Search memories by semantic similarity."""
        query_embedding = await self.embed_text(query)

        # Fetch all memories (filter by agent if specified)
        filter_query = {}
        if agent_id:
            filter_query["$or"] = [
                {"agent_id": agent_id},
                {"agent_id": "default"},
            ]

        cursor = self.db.memories.find(filter_query, {"_id": 0})
        memories = await cursor.to_list(2000)

        if not memories:
            return []

        # Compute similarities
        scored = []
        for mem in memories:
            emb = mem.get("embedding")
            if not emb:
                continue
            sim = cosine_similarity(query_embedding, emb)
            if sim >= threshold:
                scored.append({
                    "content": mem["content"],
                    "session_id": mem.get("session_id", ""),
                    "agent_id": mem.get("agent_id", ""),
                    "source": mem.get("source", ""),
                    "created_at": mem.get("created_at", ""),
                    "similarity": round(sim, 4),
                })

        # Sort by similarity descending, return top_k
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    async def list_memories(self, limit: int = 50, agent_id: str = None) -> list[dict]:
        """List recent memories."""
        filter_query = {}
        if agent_id:
            filter_query["agent_id"] = agent_id

        memories = await self.db.memories.find(
            filter_query, {"_id": 0, "embedding": 0}
        ).sort("created_at", -1).to_list(limit)
        return memories

    async def delete_memory(self, content: str, session_id: str) -> bool:
        """Delete a specific memory."""
        result = await self.db.memories.delete_one({
            "content": content, "session_id": session_id
        })
        return result.deleted_count > 0

    async def clear_memories(self, agent_id: str = None) -> int:
        """Clear all memories, optionally filtered by agent."""
        filter_query = {}
        if agent_id:
            filter_query["agent_id"] = agent_id
        result = await self.db.memories.delete_many(filter_query)
        logger.info(f"Cleared {result.deleted_count} memories")
        return result.deleted_count

    async def get_memory_count(self, agent_id: str = None) -> int:
        filter_query = {}
        if agent_id:
            filter_query["agent_id"] = agent_id
        return await self.db.memories.count_documents(filter_query)


async def extract_and_store_memories(
    db,
    session_id: str,
    agent_id: str,
    user_message: str,
    assistant_response: str,
):
    """
    After an agent turn, extract key facts and store them as memories.
    Simple heuristic: store the Q&A pair as a single memory if it's substantive.
    """
    # Skip very short or trivial exchanges
    if len(assistant_response) < 100:
        return

    mgr = MemoryManager(db)

    # Build a memory entry from the exchange
    content = f"Q: {user_message}\nA: {assistant_response[:1000]}"

    try:
        await mgr.store_memory(
            content=content,
            session_id=session_id,
            agent_id=agent_id,
            source="conversation",
            metadata={"user_message_len": len(user_message), "response_len": len(assistant_response)},
        )
    except Exception as e:
        logger.warning(f"Failed to store memory: {e}")


async def build_memory_context(db, query: str, agent_id: str, max_results: int = 3) -> str:
    """Search memory and build context to inject into the system prompt."""
    mgr = MemoryManager(db)
    try:
        results = await mgr.search_memory(query, agent_id=agent_id, top_k=max_results)
        if not results:
            return ""

        sections = ["\n\n---\n## Relevant Memory (from past conversations)\n"]
        for i, r in enumerate(results, 1):
            sections.append(f"**Memory {i}** (similarity: {r['similarity']}):\n{r['content'][:500]}\n")

        return "\n".join(sections)
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return ""
