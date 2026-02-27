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
EMAIL_TRIAGE_PROMPT_VERSION = 6

# ── The improved prompt ──────────────────────────────────────────────────
EMAIL_TRIAGE_PROMPT = """You are running an automated email triage check. Your job is to find emails that matter to the user — either requiring action OR containing personally relevant information — and handle them appropriately.

## Step 1 — Fetch recent unread emails
Use the `gmail` tool with action "search" and query "is:unread newer_than:1h" to find recent unread emails. If nothing is found, try "is:unread newer_than:3h".

If there are NO new unread emails, respond with exactly: "No new emails." and STOP.

## Step 2 — Classify each email (be STRICT)
For each unread email, classify it. Default to SKIP unless it clearly fits a tier.

**Tier A — Direct Action Request** (triggers Slack notification):
ALL of these must be true:
- A real person (not an automated system) wrote the email
- They are explicitly asking the user to perform a specific action (reply, send something, approve, review, schedule, sign, etc.)
- The action has a clear deadline OR is time-sensitive
Examples: "Can you send me the invoice by Friday?", "Please review this PR before our 3pm meeting"

**Tier B — Personal / Notable** (read for memory, NO Slack notification):
An email is Tier B if:
- It's from a real person (colleague, manager, client, partner — not a system)
- It contains information the user might want to recall later (project updates, meeting notes, decisions, personal messages, shared documents, org changes)
- OR it's a meaningful automated email about the user's own work (CI/CD results for their project, calendar changes to their meetings, etc.)
Examples: "FYI the deployment is done", "Meeting summary from today's standup", "Your PR was merged", personal messages from colleagues

**Skip entirely** (the DEFAULT — most emails go here):
- ALL marketing, promotions, newsletters, social media notifications
- Bulk automated emails not specific to user's work (GitHub digest, general announcements)
- Spam, surveys, subscription confirmations
- Order confirmations, shipping notifications, receipts

## Step 3 — Read Tier A AND Tier B emails in full
For each Tier A and Tier B email, use the `gmail` tool with action "read" and the ACTUAL `message_id` value (the `id` field returned from search results in Step 1). Do NOT invent or guess message IDs.

For Tier A, extract:
- **The specific action requested** (one sentence)
- **The deadline** (if stated)
- **One key detail** (if critical for the action)

For Tier B, simply read the full email. The system will automatically distill and remember the key content.

If after reading, you realize an email doesn't fit its tier, downgrade it.

## Step 4 — Send Slack notification ONLY if Tier A emails exist
If there are ZERO Tier A emails: respond "No actionable emails." and STOP. Do NOT call slack_notify.

If there ARE Tier A emails, use `slack_notify` with `request_feedback` set to `true`:

```
:rotating_light: *[Sender Name] — [Subject]*
→ *Action:* [What you need to do]
→ *Deadline:* [If any, otherwise omit]
```

If there are also Tier B emails, append briefly:
```
---
:inbox_tray: FYI: [Sender] — [Subject] | [Sender] — [Subject]
```

## Hard Rules
- When in doubt, SKIP the email. Only notify for clear, direct action requests.
- NEVER call slack_notify if there are no Tier A emails.
- Maximum 3 lines per email in the notification.
- ONE slack_notify call maximum.
"""


async def build_triage_prompt_with_feedback(db) -> str:
    """Build the full triage prompt with feedback context injected."""
    from gateway.triage_feedback import build_feedback_prompt_section
    feedback_section = await build_feedback_prompt_section()
    return EMAIL_TRIAGE_PROMPT + feedback_section


async def seed_email_triage_task(db):
    """Create or update the email triage task with the latest prompt version."""
    existing = await db.tasks.find_one({"id": EMAIL_TRIAGE_TASK_ID}, {"_id": 0})

    if existing:
        # Only update if our prompt version is newer
        current_version = existing.get("prompt_version", 1)
        if current_version >= EMAIL_TRIAGE_PROMPT_VERSION:
            logger.debug("Email triage task already at latest prompt version")
            return
        # Update the prompt AND fix notify mode
        await db.tasks.update_one(
            {"id": EMAIL_TRIAGE_TASK_ID},
            {"$set": {
                "prompt": EMAIL_TRIAGE_PROMPT,
                "prompt_version": EMAIL_TRIAGE_PROMPT_VERSION,
                "notify": "never",  # Agent handles Slack via slack_notify tool
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(f"Email triage prompt updated to version {EMAIL_TRIAGE_PROMPT_VERSION} (notify=never)")
    else:
        # Create the task
        task = {
            "id": EMAIL_TRIAGE_TASK_ID,
            "name": "Email Triage",
            "description": "Checks Gmail for new emails and notifies via Slack only when someone explicitly requests action.",
            "prompt": EMAIL_TRIAGE_PROMPT,
            "prompt_version": EMAIL_TRIAGE_PROMPT_VERSION,
            "agent_id": "default",
            "interval_seconds": 300,  # 5 minutes
            "enabled": False,  # User enables when Gmail is connected
            "notify": "never",  # Agent handles Slack via slack_notify tool
            "notify_level": "info",
            "running": False,
            "last_run": None,
            "next_run": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.tasks.insert_one({**task})
        logger.info("Email triage task seeded (disabled by default — enable after connecting Gmail)")
