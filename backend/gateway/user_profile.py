"""
User Profile — Passive extraction of user preferences and personal facts.
After each conversation turn, extracts facts (name, role, preferences, schedule)
from the user's messages and stores them in MongoDB. Before each turn, the
accumulated profile is injected into the system prompt so the agent "knows" the user.
"""
import os
import json
import logging
from datetime import datetime, timezone

from anthropic import AsyncAnthropic

logger = logging.getLogger("gateway.user_profile")

EXTRACTION_PROMPT = """Analyze the user's message below and extract any personal facts about them.
Return a JSON object where keys are fact identifiers and values are the fact.

Categories to look for:
- preferred_name: what they want to be called
- role/title: their job title or role
- team/department: their team or department
- company: their company or organization
- communication_style: how they prefer responses (bullet points, brief, detailed, etc.)
- recurring_events: meetings, standups, deadlines they mention regularly
- current_projects: projects or initiatives they're working on
- tools_and_tech: tools, languages, or platforms they use
- timezone/location: where they're based
- interests: professional interests or focus areas
- people: colleagues, reports, or managers they mention by name and role
- any other personal/professional fact worth remembering

RULES:
- Only extract CLEAR, EXPLICIT facts — do not infer or guess.
- If the message contains no personal facts, return exactly an empty JSON object.
- Keep values concise (under 20 words each).
- Use snake_case keys that describe the fact.

User message: "{user_message}"

Respond with ONLY valid JSON, no markdown, no explanation."""

PROFILE_ID = "default"


async def extract_profile_facts(db, user_message: str):
    """Extract personal facts from a user message and upsert into the profile."""
    # Quick pre-filter: skip very short or obviously non-personal messages
    if len(user_message.strip()) < 10:
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key_openai = os.environ.get("OPENAI_API_KEY", "")
        if not api_key_openai:
            logger.debug("No API key available for profile extraction")
            return
        # Fall back to OpenAI
        return await _extract_with_openai(db, user_message, api_key_openai)

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
        facts = json.loads(text)

        if not facts or not isinstance(facts, dict):
            return

        await _upsert_facts(db, facts)

    except (json.JSONDecodeError, Exception) as e:
        logger.debug(f"Profile extraction skipped: {e}")


async def _extract_with_openai(db, user_message: str, api_key: str):
    """Fallback: extract facts using OpenAI."""
    from openai import AsyncOpenAI
    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.replace("{user_message}", user_message),
            }],
        )
        text = response.choices[0].message.content.strip()
        facts = json.loads(text)

        if not facts or not isinstance(facts, dict):
            return

        await _upsert_facts(db, facts)

    except (json.JSONDecodeError, Exception) as e:
        logger.debug(f"Profile extraction (OpenAI fallback) skipped: {e}")


async def _upsert_facts(db, facts: dict):
    """Merge new facts into the stored profile."""
    now = datetime.now(timezone.utc).isoformat()

    update_fields = {}
    for key, value in facts.items():
        if not value or not isinstance(value, str):
            continue
        safe_key = key.strip().replace(".", "_").replace("$", "")
        update_fields[f"facts.{safe_key}"] = {
            "value": str(value).strip(),
            "extracted_at": now,
        }

    if not update_fields:
        return

    update_fields["updated_at"] = now

    await db.user_profiles.update_one(
        {"profile_id": PROFILE_ID},
        {"$set": update_fields},
        upsert=True,
    )
    logger.info(f"Profile updated: {list(facts.keys())}")


async def build_profile_context(db) -> str:
    """Load the user profile and format it for injection into the system prompt."""
    doc = await db.user_profiles.find_one(
        {"profile_id": PROFILE_ID}, {"_id": 0, "facts": 1}
    )
    if not doc or not doc.get("facts"):
        return ""

    facts = doc["facts"]
    if not facts:
        return ""

    lines = ["\n\n---\n## About This User\nYou've learned the following about the user from past conversations. Use this naturally — don't repeat it back unless relevant.\n"]
    for key, entry in facts.items():
        label = key.replace("_", " ").title()
        lines.append(f"- **{label}**: {entry['value']}")

    return "\n".join(lines) + "\n"


async def get_profile(db) -> dict:
    """Return the raw profile document (for admin/debug)."""
    doc = await db.user_profiles.find_one(
        {"profile_id": PROFILE_ID}, {"_id": 0}
    )
    return doc or {"profile_id": PROFILE_ID, "facts": {}}
