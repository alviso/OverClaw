"""
Email Memory — Automatically indexes emails into RAG when the agent reads them.
Also feeds email content into User Profile and Relationship extractors so
emails passively build the org chart and user context.

People extraction only happens for emails the user SENT (responded to),
not every email they receive.
"""
import asyncio
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.email_memory")

# Regex to parse "Display Name <email@domain.com>" or plain "email@domain.com"
_EMAIL_PATTERN = re.compile(r'(?:"?([^"<]*)"?\s*)?<?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>?')


def _parse_email_addresses(header: str) -> list[dict]:
    """Parse an email header (From/To/CC) into [{name, email}, ...]"""
    if not header:
        return []
    results = []
    for match in _EMAIL_PATTERN.finditer(header):
        name = (match.group(1) or "").strip().strip('"').strip()
        email = match.group(2).strip().lower()
        if not name:
            name = email.split("@")[0].replace(".", " ").title()
        results.append({"name": name, "email": email})
    return results


def _is_user_sent(email: dict, user_email: str) -> bool:
    """Check if this email was sent BY the user (they responded/initiated)."""
    if not user_email:
        return False
    user_email = user_email.lower().strip()
    # Check labels for SENT
    labels = email.get("labels", [])
    if "SENT" in labels:
        return True
    # Check From field
    from_field = email.get("from", "").lower()
    if user_email in from_field:
        return True
    return False


async def store_email_memory(db, email: dict, source: str = "email/gmail"):
    """
    Store a read email as a searchable RAG entry.
    Only extracts people/relationships from emails the user SENT.
    """
    subject = email.get("subject", "(no subject)")
    sender = email.get("from", "")
    to = email.get("to", "")
    date = email.get("date", "")
    body = (email.get("body") or email.get("snippet") or "")[:2000]

    if not body and not subject:
        return

    # Build a clean text representation for RAG embedding
    content = (
        f"[Email via {source.split('/')[-1].title()}]\n"
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"To: {to}\n"
        f"Date: {date}\n"
        f"Body: {body}"
    )

    # 1) Always store as RAG memory entry (useful for recall)
    asyncio.create_task(_store_rag_entry(db, content, source, email))

    # 2) Only extract people from emails the user SENT (responded to)
    user_email = await _get_user_email(db, source)
    if _is_user_sent(email, user_email):
        logger.info(f"User-sent email detected, extracting people: {subject[:50]}")

        # 2a) Structured extraction from headers (free, no LLM)
        recipients = _parse_email_addresses(to)
        cc = _parse_email_addresses(email.get("cc", ""))
        all_contacts = recipients + cc
        # Filter out the user themselves
        all_contacts = [c for c in all_contacts if c["email"] != user_email.lower()]
        if all_contacts:
            asyncio.create_task(_upsert_email_contacts(db, all_contacts, subject))

        # 2b) LLM extraction for deeper context (roles, teams from body)
        email_text = f"Email from me to {to} about '{subject}': {body[:500]}"
        asyncio.create_task(_extract_relationships_from_email(db, email_text))

        # 2c) Profile extraction (emails may reveal user context)
        asyncio.create_task(_extract_profile_from_email(db, email_text))


async def _get_user_email(db, source: str) -> str:
    """Get the connected user's email address."""
    try:
        if "gmail" in source:
            doc = await db.gmail_tokens.find_one({"user_id": "default"}, {"email": 1})
        else:
            doc = await db.microsoft_tokens.find_one({"user_id": "default"}, {"email": 1})
        return (doc or {}).get("email", "")
    except Exception:
        return ""


async def _upsert_email_contacts(db, contacts: list[dict], subject: str):
    """Upsert contacts from email headers into the relationships collection.
    Deduplicates by email address AND name_key."""
    now = datetime.now(timezone.utc).isoformat()

    for contact in contacts:
        name = contact["name"]
        email_addr = contact["email"]
        name_key = name.lower().replace(".", "").strip()

        # Try to find existing by email first (strongest match), then by name
        existing = await db.relationships.find_one({"email_address": email_addr})
        if not existing:
            existing = await db.relationships.find_one({"name_key": name_key})

        if existing:
            # Update: add email if missing, bump count
            update = {"last_seen": now}
            if not existing.get("email_address"):
                update["email_address"] = email_addr
            # If existing name is more complete, keep it; otherwise update
            if len(name) > len(existing.get("name", "")):
                update["name"] = name
                update["name_key"] = name_key

            await db.relationships.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": update,
                    "$push": {
                        "context_history": {
                            "$each": [{"text": f"Email exchange re: {subject[:50]}", "at": now, "source": "email"}],
                            "$slice": -10,
                        }
                    },
                    "$inc": {"mention_count": 1},
                },
            )
        else:
            # Create new entry
            await db.relationships.insert_one({
                "name": name,
                "name_key": name_key,
                "email_address": email_addr,
                "role": None,
                "team": None,
                "relationship": "unknown",
                "discovered_at": now,
                "last_seen": now,
                "mention_count": 1,
                "context_history": [{"text": f"Email exchange re: {subject[:50]}", "at": now, "source": "email"}],
                "discovered_via": "email",
            })

    names = [c["name"] for c in contacts]
    logger.info(f"Email contacts upserted: {names}")


async def _store_rag_entry(db, content: str, source: str, email: dict):
    """Store the email as a vector memory entry."""
    try:
        from gateway.memory import MemoryManager
        mgr = MemoryManager(db)
        await mgr.store_memory(
            content=content,
            session_id="email-index",
            agent_id="default",
            source=source,
            metadata={
                "type": "email",
                "subject": email.get("subject", ""),
                "from": email.get("from", ""),
                "date": email.get("date", ""),
                "email_id": email.get("id", ""),
            },
        )
        logger.info(f"Email indexed into RAG: {email.get('subject', '')[:60]}")
    except Exception as e:
        logger.warning(f"Failed to index email into RAG: {e}")


async def _extract_relationships_from_email(db, text: str):
    """Feed email content into the relationship extractor."""
    try:
        from gateway.relationship_memory import extract_relationships
        await extract_relationships(db, text)
    except Exception as e:
        logger.debug(f"Email relationship extraction skipped: {e}")


async def _extract_profile_from_email(db, text: str):
    """Feed email content into the user profile extractor."""
    try:
        from gateway.user_profile import extract_profile_facts
        await extract_profile_facts(db, text)
    except Exception as e:
        logger.debug(f"Email profile extraction skipped: {e}")
