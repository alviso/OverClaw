"""
Email Memory — Automatically indexes emails into RAG when the agent reads them.
Also feeds email content into User Profile and Relationship extractors so
emails passively build the org chart and user context.
"""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.email_memory")


async def store_email_memory(db, email: dict, source: str = "email/gmail"):
    """
    Store a read email as a searchable RAG entry and feed it into
    the profile/relationship extractors.

    Args:
        db: MongoDB database reference
        email: dict with keys like subject, from, to, date, body
        source: "email/gmail" or "email/outlook"
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

    # 1) Store as RAG memory entry
    asyncio.create_task(_store_rag_entry(db, content, source, email))

    # 2) Feed into relationship extractor (emails mention people)
    email_text_for_extraction = f"{sender} wrote about '{subject}': {body[:500]}"
    asyncio.create_task(_extract_relationships_from_email(db, email_text_for_extraction))

    # 3) Feed into profile extractor (emails may reveal user context)
    asyncio.create_task(_extract_profile_from_email(db, email_text_for_extraction))


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
