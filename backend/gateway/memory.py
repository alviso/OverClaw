"""
Memory / RAG — Scalable Hybrid Search with Per-Agent Isolation

Architecture:
- MongoDB: persistent storage (memories collection with text index)
- FAISS: in-memory vector index (rebuilt on startup from MongoDB)
- Hybrid scoring: vector similarity (FAISS) + keyword match (MongoDB $text) → blended

Isolation:
- Orchestrator/default agent: searches ALL memories
- Specialist agents: only their own memories
"""
import os
import logging
import threading
import numpy as np
import faiss
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId

from openai import AsyncOpenAI

logger = logging.getLogger("gateway.memory")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
TOP_K_RESULTS = 5
SIMILARITY_THRESHOLD = 0.25
HYBRID_VECTOR_WEIGHT = 0.7   # 70% vector, 30% keyword
OVERFETCH_FACTOR = 5          # fetch 5x top_k from FAISS, then filter by agent


class VectorIndex:
    """FAISS-backed vector search index with MongoDB ID mapping."""

    def __init__(self):
        self._lock = threading.Lock()
        self._index: Optional[faiss.IndexFlatIP] = None
        self._ids: list[str] = []          # FAISS row → MongoDB _id string
        self._agents: list[str] = []       # FAISS row → agent_id
        self._count = 0

    @property
    def size(self) -> int:
        return self._count

    def build(self, ids: list[str], agents: list[str], embeddings: np.ndarray):
        """Build the full index from existing data."""
        with self._lock:
            self._index = faiss.IndexFlatIP(EMBEDDING_DIMS)
            if len(ids) > 0:
                # Normalize vectors for cosine similarity via inner product
                faiss.normalize_L2(embeddings)
                self._index.add(embeddings)
            self._ids = list(ids)
            self._agents = list(agents)
            self._count = len(ids)
        logger.info(f"FAISS index built: {self._count} vectors ({EMBEDDING_DIMS}d)")

    def add(self, doc_id: str, agent_id: str, embedding: list[float]):
        """Add a single vector to the index."""
        vec = np.array([embedding], dtype=np.float32)
        faiss.normalize_L2(vec)
        with self._lock:
            if self._index is None:
                self._index = faiss.IndexFlatIP(EMBEDDING_DIMS)
            self._index.add(vec)
            self._ids.append(doc_id)
            self._agents.append(agent_id)
            self._count += 1

    def search(
        self,
        query_vec: list[float],
        top_k: int,
        agent_filter: Optional[str] = None,
    ) -> list[tuple[str, float]]:
        """Return [(doc_id, cosine_score), ...] filtered by agent."""
        if self._count == 0 or self._index is None:
            return []

        vec = np.array([query_vec], dtype=np.float32)
        faiss.normalize_L2(vec)

        # Over-fetch when filtering by agent
        fetch_k = min(top_k * OVERFETCH_FACTOR, self._count) if agent_filter else min(top_k, self._count)

        with self._lock:
            scores, indices = self._index.search(vec, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            # Agent isolation filter
            if agent_filter and self._agents[idx] != agent_filter:
                continue
            results.append((self._ids[idx], float(score)))
            if len(results) >= top_k:
                break

        return results

    def rebuild_needed(self) -> bool:
        """After deletions, flag for rebuild."""
        return self._index is None


# Singleton vector index
_vector_index = VectorIndex()


def get_vector_index() -> VectorIndex:
    return _vector_index


class MemoryManager:
    """Manages long-term memory with FAISS vector search + MongoDB text search."""

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

    # ── Index Management ──

    async def initialize_index(self):
        """Load all embeddings from MongoDB and build the FAISS index."""
        cursor = self.db.memories.find(
            {"embedding": {"$exists": True}},
            {"_id": 1, "agent_id": 1, "embedding": 1},
        )
        ids, agents, vecs = [], [], []
        async for doc in cursor:
            emb = doc.get("embedding")
            if emb and len(emb) == EMBEDDING_DIMS:
                ids.append(str(doc["_id"]))
                agents.append(doc.get("agent_id", "default"))
                vecs.append(emb)

        embeddings = np.array(vecs, dtype=np.float32) if vecs else np.empty((0, EMBEDDING_DIMS), dtype=np.float32)
        _vector_index.build(ids, agents, embeddings)

        # Ensure MongoDB text index exists for keyword search
        existing = await self.db.memories.index_information()
        if "content_text" not in existing:
            await self.db.memories.create_index([("content", "text")], name="content_text")
            logger.info("Created MongoDB text index on memories.content")

    # ── Store ──

    async def store_memory(
        self,
        content: str,
        session_id: str,
        agent_id: str = "default",
        source: str = "conversation",
        metadata: dict = None,
    ) -> dict:
        """Store a memory with its embedding in MongoDB + FAISS."""
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
        result = await self.db.memories.insert_one(doc)
        doc_id = str(result.inserted_id)

        # Add to FAISS index
        _vector_index.add(doc_id, agent_id, embedding)

        logger.info(f"Memory stored: {content[:60]}... (agent={agent_id}, source={source})")
        return {"content": content, "session_id": session_id, "source": source, "agent_id": agent_id}

    # ── Hybrid Search ──

    async def search_memory(
        self,
        query: str,
        agent_id: str = None,
        top_k: int = TOP_K_RESULTS,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> list[dict]:
        """
        Hybrid search: FAISS vector similarity + MongoDB keyword match.
        Agent isolation: specialists see only their own; orchestrator sees all.
        """
        # Determine agent filter
        agent_filter = None
        if agent_id and agent_id != "default":
            agent_filter = agent_id

        # 1. Vector search via FAISS
        query_embedding = await self.embed_text(query)
        vector_hits = _vector_index.search(query_embedding, top_k * 2, agent_filter=agent_filter)
        vector_scores = {doc_id: score for doc_id, score in vector_hits if score >= threshold}

        # 2. Keyword search via MongoDB text index
        keyword_scores = {}
        try:
            text_filter = {"$text": {"$search": query}}
            if agent_filter:
                text_filter["agent_id"] = agent_filter
            cursor = self.db.memories.find(
                text_filter,
                {"score": {"$meta": "textScore"}, "_id": 1},
            ).sort([("score", {"$meta": "textScore"})]).limit(top_k * 2)
            async for doc in cursor:
                keyword_scores[str(doc["_id"])] = doc["score"]
        except Exception as e:
            logger.debug(f"Text search skipped: {e}")

        # 3. Blend scores
        all_doc_ids = set(vector_scores.keys()) | set(keyword_scores.keys())
        if not all_doc_ids:
            return []

        # Normalize keyword scores to 0-1 range
        max_kw = max(keyword_scores.values()) if keyword_scores else 1.0
        norm_kw = {k: v / max_kw for k, v in keyword_scores.items()} if max_kw > 0 else {}

        scored = []
        for doc_id in all_doc_ids:
            vs = vector_scores.get(doc_id, 0.0)
            ks = norm_kw.get(doc_id, 0.0)
            final = HYBRID_VECTOR_WEIGHT * vs + (1 - HYBRID_VECTOR_WEIGHT) * ks
            scored.append((doc_id, final, vs, ks))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_ids = [s[0] for s in scored[:top_k]]
        score_map = {s[0]: (s[1], s[2], s[3]) for s in scored[:top_k]}

        # 4. Fetch full documents
        object_ids = [ObjectId(did) for did in top_ids]
        docs = await self.db.memories.find(
            {"_id": {"$in": object_ids}},
            {"embedding": 0},
        ).to_list(top_k)

        results = []
        for doc in docs:
            doc_id = str(doc["_id"])
            final, vs, ks = score_map.get(doc_id, (0, 0, 0))
            results.append({
                "content": doc.get("content", ""),
                "session_id": doc.get("session_id", ""),
                "agent_id": doc.get("agent_id", ""),
                "source": doc.get("source", ""),
                "created_at": doc.get("created_at", ""),
                "metadata": doc.get("metadata", {}),
                "similarity": round(final, 4),
                "vector_score": round(vs, 4),
                "keyword_score": round(ks, 4),
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results

    # ── List / Delete / Clear ──

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
        """Delete a specific memory (triggers index rebuild)."""
        result = await self.db.memories.delete_one({"content": content, "session_id": session_id})
        if result.deleted_count > 0:
            await self.initialize_index()  # rebuild FAISS
        return result.deleted_count > 0

    async def clear_memories(self, agent_id: str = None) -> int:
        """Clear memories, optionally filtered by agent."""
        filter_query = {}
        if agent_id:
            filter_query["agent_id"] = agent_id
        result = await self.db.memories.delete_many(filter_query)
        logger.info(f"Cleared {result.deleted_count} memories")
        await self.initialize_index()  # rebuild FAISS
        return result.deleted_count

    async def get_memory_count(self, agent_id: str = None) -> int:
        filter_query = {}
        if agent_id:
            filter_query["agent_id"] = agent_id
        return await self.db.memories.count_documents(filter_query)

    async def get_index_stats(self) -> dict:
        """Return index health stats."""
        total = await self.db.memories.count_documents({})
        pipeline = [{"$group": {"_id": "$agent_id", "count": {"$sum": 1}}}]
        by_agent = {doc["_id"]: doc["count"] async for doc in self.db.memories.aggregate(pipeline)}
        return {
            "total_memories": total,
            "faiss_index_size": _vector_index.size,
            "by_agent": by_agent,
            "embedding_dims": EMBEDDING_DIMS,
            "hybrid_weights": {"vector": HYBRID_VECTOR_WEIGHT, "keyword": 1 - HYBRID_VECTOR_WEIGHT},
        }


# ── Convenience Functions ──

async def build_memory_context(db, query: str, agent_id: str, max_results: int = 3) -> str:
    """Search memory and build context to inject into the system prompt."""
    mgr = MemoryManager(db)
    try:
        results = await mgr.search_memory(query, agent_id=agent_id, top_k=max_results)
        if not results:
            return ""

        sections = ["\n\n---\n## Relevant Memory (from past conversations)\n"]
        for i, r in enumerate(results, 1):
            fact_type = r.get("metadata", {}).get("type", "")
            type_label = f" [{fact_type}]" if fact_type else ""
            sections.append(
                f"**Memory {i}** (relevance: {r['similarity']}{type_label}):\n"
                f"{r['content'][:500]}\n"
            )
        return "\n".join(sections)
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return ""
