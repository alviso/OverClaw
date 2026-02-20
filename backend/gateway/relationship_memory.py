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
    """Upsert discovered people into the relationships collection.
    Uses fuzzy name matching to avoid duplicates. Filters out the user."""
    from gateway.email_memory import _names_match, _pick_best_name, _normalize_name

    now = datetime.now(timezone.utc).isoformat()

    # Get connected user's email and name to filter them out
    user_emails = set()
    for coll_name in ("gmail_tokens", "microsoft_tokens"):
        doc = await db[coll_name].find_one({"user_id": "default"}, {"email": 1})
        if doc and doc.get("email"):
            user_emails.add(doc["email"].lower())
    # Also get name from user profile — check multiple fact keys
    profile = await db.user_profiles.find_one({"profile_id": "default"}, {"facts": 1})
    facts = (profile or {}).get("facts", {})
    user_names = set()
    for key in ("full_name", "preferred_name", "name", "last_name"):
        val = facts.get(key, {})
        if isinstance(val, dict):
            val = val.get("value", "")
        if val:
            user_names.add(val.lower())
    # Also add email-derived name
    if facts.get("email_address"):
        ea = facts["email_address"]
        if isinstance(ea, dict):
            ea = ea.get("value", "")
        if ea:
            user_emails.add(ea.lower())

    for person in people:
        if not isinstance(person, dict):
            continue
        name = (person.get("name") or "").strip()
        if not name or len(name) < 2:
            continue

        # Skip the user themselves
        name_lower = name.lower()
        if any(un and (name_lower == un or name_lower in un or un in name_lower) for un in user_names):
            continue
        if any(email in name_lower for email in user_emails):
            continue

        name_key = _normalize_name(name).replace(" ", "")

        # 1) Try exact name_key match
        existing = await db.relationships.find_one({"name_key": name_key})

        # 2) Fuzzy name match against all existing people
        if not existing:
            all_people = await db.relationships.find(
                {}, {"name": 1, "name_key": 1, "email_address": 1}
            ).to_list(500)
            for p in all_people:
                if _names_match(name, p.get("name", "")):
                    existing = p
                    break

        update = {"last_seen": now}

        if person.get("role"):
            update["role"] = person["role"]
        if person.get("team"):
            update["team"] = person["team"]
        if person.get("relationship"):
            update["relationship"] = person["relationship"]

        context = (person.get("context") or "").strip()

        if existing:
            best_name = _pick_best_name(existing.get("name", ""), name)
            if best_name != existing.get("name", ""):
                update["name"] = best_name
                update["name_key"] = _normalize_name(best_name).replace(" ", "")

            await db.relationships.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": update,
                    "$push": {
                        "context_history": {
                            "$each": [{"text": context, "at": now}] if context else [],
                            "$slice": -10,
                        }
                    },
                    "$inc": {"mention_count": 1},
                },
            )
        else:
            await db.relationships.insert_one({
                "name": name,
                "name_key": name_key,
                "role": person.get("role"),
                "team": person.get("team"),
                "relationship": person.get("relationship", "unknown"),
                "discovered_at": now,
                "last_seen": now,
                "mention_count": 1,
                "context_history": [{"text": context, "at": now}] if context else [],
            })

    logger.info(f"Relationships updated: {[p.get('name') for p in people if isinstance(p, dict)]}")


async def build_relationships_context(db) -> str:
    """Build a context string of known people for injection into the system prompt."""
    cursor = db.relationships.find(
        {}, {"_id": 0, "name": 1, "role": 1, "team": 1, "relationship": 1, "email_address": 1, "context_history": 1}
    ).sort("mention_count", -1).limit(20)

    people = await cursor.to_list(length=20)
    if not people:
        return ""

    lines = ["\n\n---\n## People You Know About\nPeople the user has mentioned in past conversations or exchanged emails with. Reference naturally when relevant.\n"]
    for p in people:
        parts = [f"**{p['name']}**"]
        if p.get("email_address"):
            parts.append(f"<{p['email_address']}>")
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
    cursor = db.relationships.find({}).sort("mention_count", -1)
    docs = await cursor.to_list(length=100)
    # Convert _id to string for JSON serialization
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return docs
