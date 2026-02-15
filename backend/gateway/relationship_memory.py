"""
Relationship Memory — Passive extraction of people mentioned in conversations.
Builds a "discovered relationships" graph from natural conversation.
After each turn, extracts people references and stores them in MongoDB.
"""
import os
import json
import logging
from datetime import datetime, timezone

from anthropic import AsyncAnthropic

logger = logging.getLogger("gateway.relationships")

EXTRACTION_PROMPT = """Analyze the user's message and extract any PEOPLE mentioned.
For each person, return a JSON array of objects with these fields:
- "name": their name (first name or full name as mentioned)
- "role": their title or role if mentioned (null if unknown)
- "team": their team, department, or company (null if unknown)
- "relationship": their relationship to the user — one of: "report", "manager", "peer", "colleague", "client", "vendor", "external", "unknown"
- "context": a brief note about what was said about them (max 15 words)

RULES:
- Only extract REAL PEOPLE explicitly mentioned by name. No pronouns, no hypothetical people.
- If no people are mentioned, return exactly: []
- Do not extract the user themselves.
- Keep context factual and concise.

User message: "{user_message}"

Respond with ONLY a valid JSON array, no markdown, no explanation."""


async def extract_relationships(db, user_message: str):
    """Extract people mentions from a user message and upsert into the relationships collection."""
    if len(user_message.strip()) < 15:
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return

    try:
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.replace("{user_message}", user_message),
            }],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3].strip()

        people = json.loads(text)
        if not people or not isinstance(people, list):
            return

        await _upsert_people(db, people)

    except (json.JSONDecodeError, Exception) as e:
        logger.debug(f"Relationship extraction skipped: {e}")


async def _upsert_people(db, people: list):
    """Upsert discovered people into the relationships collection."""
    now = datetime.now(timezone.utc).isoformat()

    for person in people:
        if not isinstance(person, dict):
            continue
        name = (person.get("name") or "").strip()
        if not name or len(name) < 2:
            continue

        # Normalize name for matching (lowercase for lookup, preserve original for display)
        name_key = name.lower().replace(".", "").strip()

        update = {
            "name": name,
            "name_key": name_key,
            "last_seen": now,
        }

        # Only update fields that have values (don't overwrite with null)
        if person.get("role"):
            update["role"] = person["role"]
        if person.get("team"):
            update["team"] = person["team"]
        if person.get("relationship"):
            update["relationship"] = person["relationship"]

        # Append context to history (keep last 5)
        context = (person.get("context") or "").strip()

        await db.relationships.update_one(
            {"name_key": name_key},
            {
                "$set": update,
                "$setOnInsert": {"discovered_at": now},
                "$push": {
                    "context_history": {
                        "$each": [{"text": context, "at": now}] if context else [],
                        "$slice": -5,
                    }
                },
                "$inc": {"mention_count": 1},
            },
            upsert=True,
        )

    logger.info(f"Relationships updated: {[p.get('name') for p in people if isinstance(p, dict)]}")


async def build_relationships_context(db) -> str:
    """Build a context string of known people for injection into the system prompt."""
    cursor = db.relationships.find(
        {}, {"_id": 0, "name": 1, "role": 1, "team": 1, "relationship": 1, "context_history": 1}
    ).sort("mention_count", -1).limit(20)

    people = await cursor.to_list(length=20)
    if not people:
        return ""

    lines = ["\n\n---\n## People You Know About\nPeople the user has mentioned in past conversations. Reference naturally when relevant.\n"]
    for p in people:
        parts = [f"**{p['name']}**"]
        if p.get("role"):
            parts.append(f"({p['role']})")
        if p.get("team"):
            parts.append(f"@ {p['team']}")
        if p.get("relationship") and p["relationship"] != "unknown":
            parts.append(f"[{p['relationship']}]")

        # Most recent context
        history = p.get("context_history", [])
        if history:
            latest = history[-1].get("text", "")
            if latest:
                parts.append(f"— {latest}")

        lines.append(f"- {' '.join(parts)}")

    return "\n".join(lines) + "\n"


async def get_relationships(db) -> list:
    """Return all discovered relationships for the admin panel."""
    cursor = db.relationships.find(
        {}, {"_id": 0}
    ).sort("mention_count", -1)

    return await cursor.to_list(length=100)
