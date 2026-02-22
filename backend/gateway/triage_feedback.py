"""
Triage Feedback — Tracks 👍/👎 reactions on email triage Slack messages.
Stores feedback, computes stats, and builds prompt adjustments for auto-tuning.
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("gateway.triage_feedback")

_db = None


def set_feedback_db(database):
    global _db
    _db = database


async def track_triage_message(channel: str, message_ts: str, summary_text: str):
    """Record a triage message so we can match reactions to it later."""
    if not _db:
        return
    doc = {
        "channel": channel,
        "message_ts": message_ts,
        "summary_preview": summary_text[:500],
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "feedback": None,
    }
    await _db.triage_messages.insert_one(doc)
    logger.info(f"Tracked triage message: channel={channel} ts={message_ts}")


async def record_feedback(channel: str, message_ts: str, reaction: str, user: str) -> bool:
    """Record a 👍/👎 reaction on a tracked triage message. Returns True if matched."""
    if not _db:
        return False

    # Map reaction names to feedback
    feedback_map = {
        "+1": "positive",
        "thumbsup": "positive",
        "-1": "negative",
        "thumbsdown": "negative",
    }
    feedback = feedback_map.get(reaction)
    if not feedback:
        return False

    result = await _db.triage_messages.update_one(
        {"channel": channel, "message_ts": message_ts, "feedback": None},
        {"$set": {
            "feedback": feedback,
            "feedback_reaction": reaction,
            "feedback_user": user,
            "feedback_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if result.modified_count > 0:
        logger.info(f"Triage feedback recorded: {feedback} on message {message_ts}")
        return True
    return False


async def get_feedback_stats(days: int = 30) -> dict:
    """Get feedback statistics for the last N days."""
    if not _db:
        return {"total": 0, "positive": 0, "negative": 0, "pending": 0, "approval_rate": None}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    pipeline = [
        {"$match": {"sent_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$feedback",
            "count": {"$sum": 1},
        }},
    ]
    results = await _db.triage_messages.aggregate(pipeline).to_list(10)

    stats = {"total": 0, "positive": 0, "negative": 0, "pending": 0}
    for r in results:
        count = r["count"]
        stats["total"] += count
        if r["_id"] == "positive":
            stats["positive"] = count
        elif r["_id"] == "negative":
            stats["negative"] = count
        else:
            stats["pending"] = count

    rated = stats["positive"] + stats["negative"]
    stats["approval_rate"] = round(stats["positive"] / rated * 100, 1) if rated > 0 else None
    stats["rated_count"] = rated
    stats["days"] = days

    return stats


async def get_recent_feedback(limit: int = 10) -> list[dict]:
    """Get recent feedback entries for display."""
    if not _db:
        return []
    docs = await _db.triage_messages.find(
        {"feedback": {"$ne": None}},
        {"_id": 0, "summary_preview": 1, "feedback": 1, "feedback_at": 1, "sent_at": 1},
    ).sort("feedback_at", -1).to_list(limit)
    return docs


async def build_feedback_prompt_section() -> str:
    """Build a prompt section that injects feedback context for auto-tuning.
    Returns an empty string if there isn't enough data."""
    stats = await get_feedback_stats(days=14)

    # Need at least 3 rated messages to be meaningful
    if stats["rated_count"] < 3:
        return ""

    section = "\n\n## Feedback from Previous Summaries\n"
    section += f"Over the last 14 days, {stats['rated_count']} summaries were rated: "
    section += f"{stats['positive']} positive, {stats['negative']} negative "
    section += f"({stats['approval_rate']}% approval rate).\n"

    if stats["approval_rate"] is not None and stats["approval_rate"] < 60:
        section += (
            "\nThe user is NOT satisfied with recent summaries. ADJUST your approach:\n"
            "- Be MORE concise — cut anything that isn't a direct action or new info\n"
            "- Lead with the SPECIFIC action the user must take\n"
            "- If you can't identify a clear action, classify as Tier B not Tier A\n"
            "- Avoid any context the user already knows about their contacts/projects\n"
        )
    elif stats["approval_rate"] is not None and stats["approval_rate"] >= 80:
        section += "\nThe user finds these summaries helpful. Maintain the current style and detail level.\n"
    else:
        section += (
            "\nFeedback is mixed. Try to:\n"
            "- Be slightly more concise\n"
            "- Make sure every Tier A email has a clear, specific action item\n"
        )

    # Show examples of recent negative feedback for context
    if stats["negative"] > 0:
        recent_negative = await _db.triage_messages.find(
            {"feedback": "negative"},
            {"_id": 0, "summary_preview": 1},
        ).sort("feedback_at", -1).to_list(2)

        if recent_negative:
            section += "\nExamples of summaries the user disliked (avoid this style):\n"
            for neg in recent_negative:
                preview = neg.get("summary_preview", "")[:150]
                section += f"- \"{preview}...\"\n"

    return section
