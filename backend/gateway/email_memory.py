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
_ADDR_WITH_NAME = re.compile(r'"?([^"<,]+?)"?\s*<([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>')
_ADDR_PLAIN = re.compile(r'(?<![<\w.%+\-])([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})(?!>)')


def _parse_email_addresses(header: str) -> list[dict]:
    """Parse an email header (From/To/CC) into [{name, email}, ...]"""
    if not header:
        return []
    results = []
    seen = set()

    # First pass: "Name <email>" format
    for match in _ADDR_WITH_NAME.finditer(header):
        name = match.group(1).strip().strip('"').strip()
        email = match.group(2).strip().lower()
        if email not in seen:
            seen.add(email)
            results.append({"name": name, "email": email})

    # Second pass: plain email addresses not already captured
    for match in _ADDR_PLAIN.finditer(header):
        email = match.group(1).strip().lower()
        if email not in seen:
            seen.add(email)
            name = email.split("@")[0].replace(".", " ").title()
            results.append({"name": name, "email": email})

    return results


def _normalize_name(name: str) -> str:
    """Normalize name for matching: lowercase, strip parens/suffixes, consistent ordering."""
    name = name.lower().strip()
    # Remove parenthetical suffixes like "(TcT)"
    name = re.sub(r'\s*\([^)]*\)\s*', ' ', name)
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _name_tokens(name: str) -> set:
    """Get a set of meaningful name tokens for fuzzy matching."""
    normalized = _normalize_name(name)
    # Remove dots, commas
    cleaned = normalized.replace(".", "").replace(",", "")
    tokens = {t for t in cleaned.split() if len(t) > 1}
    return tokens


def _names_match(name_a: str, name_b: str) -> bool:
    """Check if two names likely refer to the same person.
    - Exact match after normalization
    - One is a subset of the other (e.g., 'Áron' vs 'Vadász Áron')
    - Significant token overlap (e.g., 'Attila Vadász' vs 'Vadász Attila (TcT)')
    """
    norm_a = _normalize_name(name_a)
    norm_b = _normalize_name(name_b)

    if norm_a == norm_b:
        return True

    tokens_a = _name_tokens(name_a)
    tokens_b = _name_tokens(name_b)

    if not tokens_a or not tokens_b:
        return False

    # One name is a subset of the other
    if tokens_a.issubset(tokens_b) or tokens_b.issubset(tokens_a):
        return True

    # Significant overlap: overlap must cover majority of the smaller name
    overlap = tokens_a & tokens_b
    smaller = min(len(tokens_a), len(tokens_b))
    if smaller > 0 and len(overlap) / smaller >= 0.6:
        return True

    return False


def _pick_best_name(existing_name: str, new_name: str) -> str:
    """Pick the most complete/informative name."""
    # Strip parens from both for comparison
    clean_existing = re.sub(r'\s*\([^)]*\)\s*', ' ', existing_name).strip()
    clean_new = re.sub(r'\s*\([^)]*\)\s*', ' ', new_name).strip()

    # Prefer the one with more word parts (fuller name)
    parts_existing = [p for p in clean_existing.split() if len(p) > 1]
    parts_new = [p for p in clean_new.split() if len(p) > 1]

    if len(parts_new) > len(parts_existing):
        return new_name
    if len(parts_new) == len(parts_existing) and len(clean_new) > len(clean_existing):
        return new_name
    return existing_name


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
    Deduplicates by email address, name_key, AND fuzzy name matching."""
    now = datetime.now(timezone.utc).isoformat()

    for contact in contacts:
        name = contact["name"]
        email_addr = contact["email"]
        name_key = _normalize_name(name).replace(" ", "")

        # 1) Try exact email match first (strongest signal)
        existing = await db.relationships.find_one({"email_address": email_addr})

        # 2) Try exact name_key match
        if not existing:
            existing = await db.relationships.find_one({"name_key": name_key})

        # 3) Fuzzy name match against all existing people
        if not existing:
            all_people = await db.relationships.find(
                {}, {"name": 1, "name_key": 1, "email_address": 1}
            ).to_list(500)
            for person in all_people:
                if _names_match(name, person.get("name", "")):
                    existing = person
                    break

        if existing:
            # Merge: update email if missing, pick best name, bump count
            update = {"last_seen": now}

            if not existing.get("email_address") and email_addr:
                update["email_address"] = email_addr

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
