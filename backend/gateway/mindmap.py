"""
Mindmap Generator — Builds a visual graph of the user's cognitive landscape.
Clusters memories, emails, and conversations into topic nodes,
with people attached as secondary participants.
"""
import os
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.mindmap")

CLUSTER_PROMPT = """You are analyzing a user's work assistant data to build a mindmap of their cognitive landscape.

Given the following data about:
1. MEMORIES (extracted facts from conversations)
2. PEOPLE (discovered relationships)
3. RECENT CONVERSATIONS (session summaries)

Generate a mindmap graph with:
- **Topic nodes**: Work streams, projects, ongoing efforts, subjects the user is engaged with
- **People nodes**: People connected to those topics (secondary — they appear as participants, not primary focus)
- **Edges**: Connections between topics and people, and between related topics

Return ONLY valid JSON with this structure:
{
  "nodes": [
    {"id": "topic-1", "label": "Project Alpha", "type": "topic", "category": "work", "summary": "Brief description", "importance": "medium"},
    {"id": "person-1", "label": "Sarah Chen", "type": "person", "role": "Engineering Lead", "team": "Backend"},
    ...
  ],
  "edges": [
    {"source": "topic-1", "target": "person-1", "label": "leads"},
    {"source": "topic-1", "target": "topic-2", "label": "depends on"},
    ...
  ]
}

Rules:
- Topic categories: "work", "personal", "urgent", "planning", "communication", "learning"
- Importance levels: "high", "medium", "low"
- Keep labels concise (2-4 words)
- Summaries max 20 words
- Create 3-15 topic nodes depending on data richness
- Only include people who are clearly connected to topics
- Add edges between related topics too (not just topic-person)
- If data is sparse, create fewer but meaningful nodes

DATA:

## MEMORIES
{memories}

## PEOPLE
{people}

## RECENT CONVERSATIONS
{conversations}

Respond with ONLY the JSON object. No markdown fences, no explanation."""


async def generate_mindmap(db) -> dict:
    """Generate a mindmap graph from the user's data."""
    # Gather data from multiple sources
    memories_text = await _gather_memories(db)
    people_text = await _gather_people(db)
    conversations_text = await _gather_conversations(db)

    if not memories_text and not people_text and not conversations_text:
        return {
            "nodes": [],
            "edges": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "empty": True,
        }

    prompt = CLUSTER_PROMPT.format(
        memories=memories_text or "(No memories yet)",
        people=people_text or "(No people discovered yet)",
        conversations=conversations_text or "(No recent conversations)",
    )

    graph = await _call_llm(prompt)

    if not graph:
        return {
            "nodes": [],
            "edges": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": "LLM failed to generate mindmap",
        }

    # Merge in any user-set importance overrides
    overrides = await db.mindmap_overrides.find({}, {"_id": 0}).to_list(100)
    override_map = {o["node_id"]: o for o in overrides}
    for node in graph.get("nodes", []):
        if node["id"] in override_map:
            node["importance"] = override_map[node["id"]].get("importance", node.get("importance", "medium"))

    result = {
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache the result
    await db.mindmap_cache.replace_one(
        {"_id": "latest"},
        {"_id": "latest", **result},
        upsert=True,
    )

    return result


async def get_cached_mindmap(db) -> dict:
    """Return the cached mindmap, or empty if none exists."""
    doc = await db.mindmap_cache.find_one({"_id": "latest"}, {"_id": 0})
    if doc:
        # Apply latest overrides
        overrides = await db.mindmap_overrides.find({}, {"_id": 0}).to_list(100)
        override_map = {o["node_id"]: o for o in overrides}
        for node in doc.get("nodes", []):
            if node["id"] in override_map:
                node["importance"] = override_map[node["id"]].get("importance", node.get("importance", "medium"))
        return doc
    return {"nodes": [], "edges": [], "empty": True}


async def set_node_importance(db, node_id: str, importance: str) -> dict:
    """Set user-defined importance on a mindmap node."""
    if importance not in ("high", "medium", "low"):
        return {"ok": False, "error": "importance must be high, medium, or low"}

    await db.mindmap_overrides.update_one(
        {"node_id": node_id},
        {"$set": {
            "node_id": node_id,
            "importance": importance,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    # Also update cached mindmap in-place
    await db.mindmap_cache.update_one(
        {"_id": "latest", "nodes.id": node_id},
        {"$set": {"nodes.$.importance": importance}},
    )

    return {"ok": True, "node_id": node_id, "importance": importance}


async def _gather_memories(db) -> str:
    """Fetch recent memories for clustering."""
    memories = await db.memories.find(
        {}, {"_id": 0, "content": 1, "source": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(50)

    if not memories:
        return ""

    lines = []
    for m in memories:
        content = m.get("content", "")[:300]
        lines.append(f"- [{m.get('source', 'unknown')}] {content}")
    return "\n".join(lines)


async def _gather_people(db) -> str:
    """Fetch known relationships."""
    people = await db.relationships.find(
        {}, {"_id": 0, "name": 1, "role": 1, "team": 1, "relationship": 1,
             "email_address": 1, "context_history": 1, "mention_count": 1}
    ).sort("mention_count", -1).to_list(30)

    if not people:
        return ""

    lines = []
    for p in people:
        parts = [p.get("name", "Unknown")]
        if p.get("role"):
            parts.append(f"({p['role']})")
        if p.get("team"):
            parts.append(f"@ {p['team']}")
        if p.get("relationship") and p["relationship"] != "unknown":
            parts.append(f"[{p['relationship']}]")
        ctx = p.get("context_history", [])
        if ctx:
            latest = ctx[-1].get("text", "")
            if latest:
                parts.append(f"— {latest}")
        lines.append(f"- {' '.join(parts)} (mentions: {p.get('mention_count', 0)})")
    return "\n".join(lines)


async def _gather_conversations(db) -> str:
    """Fetch recent conversation summaries."""
    # Get distinct sessions with recent messages
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$session_id",
            "last_message": {"$first": "$content"},
            "last_time": {"$first": "$timestamp"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"last_time": -1}},
        {"$limit": 10},
    ]

    sessions = await db.chat_messages.aggregate(pipeline).to_list(10)
    if not sessions:
        return ""

    lines = []
    for s in sessions:
        sid = s["_id"] or "unknown"
        preview = (s.get("last_message") or "")[:200]
        lines.append(f"- Session '{sid}' ({s.get('count', 0)} msgs): {preview}")
    return "\n".join(lines)


async def _call_llm(prompt: str) -> dict:
    """Call the LLM to generate the mindmap graph structure."""
    # Try Anthropic first (better at structured output), fallback to OpenAI
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if anthropic_key:
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=anthropic_key)
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return _parse_json(text)
        except Exception as e:
            logger.warning(f"Anthropic mindmap generation failed: {e}")

    if openai_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=openai_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content.strip()
            return _parse_json(text)
        except Exception as e:
            logger.warning(f"OpenAI mindmap generation failed: {e}")

    logger.error("No LLM available for mindmap generation")
    return None


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM output, handling markdown fences."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)
