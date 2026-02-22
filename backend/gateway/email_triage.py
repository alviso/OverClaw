"""
Email Triage — Improved prompt and seeding for the scheduled email check task.
Provides a structured, actionable prompt that produces concise Slack-ready summaries.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.email_triage")

# ── The Task ID (stable, so we can update it idempotently) ───────────────
EMAIL_TRIAGE_TASK_ID = "email-triage"

# ── Version — bump this when you change the prompt to force a DB update ──
EMAIL_TRIAGE_PROMPT_VERSION = 2

# ── The improved prompt ──────────────────────────────────────────────────
EMAIL_TRIAGE_PROMPT = """You are running an automated email triage check. Your ONLY job is to find NEW emails that require the user's attention and send a concise, actionable Slack notification.

## Step 1 — Fetch recent unread emails
Use the `gmail` tool with action "search" and query "is:unread newer_than:1h" to find recent unread emails. If nothing is found, try "is:unread newer_than:3h".

If there are NO new unread emails, do NOT send any Slack message. Simply respond: "No new emails requiring attention."

## Step 2 — Classify each email
For each unread email, classify it into one of three tiers:

**Tier A — Action Required** (notify immediately):
- A person is asking the user to DO something (reply, send a document, schedule a call, approve, review, etc.)
- Contains a deadline or time-sensitive request
- From a known important contact (boss, client, direct collaborator)
- Contains financial/legal information requiring action

**Tier B — FYI / Informational** (mention briefly):
- Status updates, meeting notes, shared documents
- Newsletters or digests the user subscribed to and might care about
- Automated notifications from important tools (GitHub, Jira, etc.)

**Tier C — Skip entirely** (do NOT include in notification):
- Marketing/promotional emails
- Automated notifications from low-priority tools
- Spam, social media alerts, generic newsletters

## Step 3 — Read Tier A emails in full
For each Tier A email, use the `gmail` tool with action "read" to get the full body. Extract:
- **The specific action requested** (e.g., "Send the Q4 invoice to finance@acme.com by Friday")
- **Any deadline or urgency signal**
- **Key details the user needs** (amounts, names, dates, links)

Do NOT include background information the user already knows (project history, who people are, what their roles are). Only include what's NEW and what's NEEDED TO ACT.

## Step 4 — Compose and send ONE Slack notification
Use the `slack_notify` tool to send a SINGLE message. Format:

For Tier A emails (action required):
```
:rotating_light: *[Sender Name] — [Subject line]*
→ *Action:* [One sentence: what the user needs to do]
→ *Deadline:* [If any, otherwise omit this line]
→ *Key detail:* [One critical piece of info, if relevant]
```

For Tier B emails (FYI), add a brief section at the end:
```
---
:inbox_tray: Also received:
• [Sender] — [Subject] (FYI)
• [Sender] — [Subject] (FYI)
```

## Rules
- Lead with the ACTION, not the context. Wrong: "John, your colleague from the finance team, has sent you an email about the Q4 invoice project that was discussed in last week's meeting." Right: "→ Action: Send Q4 invoice to finance@acme.com"
- Maximum 3-4 lines per email. If it's longer, you're including too much context.
- Never tell the user things they already know about their contacts or projects.
- If ALL emails are Tier C (skip), respond "No new emails requiring attention." and do NOT send a Slack message.
- Combine everything into ONE slack_notify call. Never send multiple messages.
"""


async def seed_email_triage_task(db):
    """Create or update the email triage task with the latest prompt version."""
    existing = await db.tasks.find_one({"id": EMAIL_TRIAGE_TASK_ID}, {"_id": 0})

    if existing:
        # Only update if our prompt version is newer
        current_version = existing.get("prompt_version", 1)
        if current_version >= EMAIL_TRIAGE_PROMPT_VERSION:
            logger.debug("Email triage task already at latest prompt version")
            return
        # Update the prompt
        await db.tasks.update_one(
            {"id": EMAIL_TRIAGE_TASK_ID},
            {"$set": {
                "prompt": EMAIL_TRIAGE_PROMPT,
                "prompt_version": EMAIL_TRIAGE_PROMPT_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(f"Email triage prompt updated to version {EMAIL_TRIAGE_PROMPT_VERSION}")
    else:
        # Create the task
        task = {
            "id": EMAIL_TRIAGE_TASK_ID,
            "name": "Email Triage",
            "description": "Checks Gmail for new emails, classifies by importance, and sends actionable Slack summaries.",
            "prompt": EMAIL_TRIAGE_PROMPT,
            "prompt_version": EMAIL_TRIAGE_PROMPT_VERSION,
            "agent_id": "default",
            "interval_seconds": 300,  # 5 minutes
            "enabled": False,  # User enables when Gmail is connected
            "notify": "always",
            "notify_level": "info",
            "running": False,
            "last_run": None,
            "next_run": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.tasks.insert_one({**task})
        logger.info("Email triage task seeded (disabled by default — enable after connecting Gmail)")
