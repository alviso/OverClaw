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
EMAIL_TRIAGE_PROMPT_VERSION = 4

# ── The improved prompt ──────────────────────────────────────────────────
EMAIL_TRIAGE_PROMPT = """You are running an automated email triage check. Your ONLY job is to find emails where someone is explicitly asking the user to DO something, and notify via Slack ONLY for those.

## Step 1 — Fetch recent unread emails
Use the `gmail` tool with action "search" and query "is:unread newer_than:1h" to find recent unread emails. If nothing is found, try "is:unread newer_than:3h".

If there are NO new unread emails, respond with exactly: "No new emails." and STOP. Do NOT call slack_notify.

## Step 2 — Classify each email (be STRICT)
For each unread email, classify it. Default to SKIP unless the email clearly fits Tier A.

**Tier A — Direct Action Request** (the ONLY tier that triggers a Slack notification):
An email is Tier A ONLY if ALL of these are true:
- A real person (not an automated system) wrote the email
- They are explicitly asking the user to perform a specific action (reply, send something, approve, review, schedule, sign, etc.)
- The action has a clear deadline OR is time-sensitive
Examples that ARE Tier A: "Can you send me the invoice by Friday?", "Please review this PR before our 3pm meeting", "Need your approval on the budget doc"
Examples that are NOT Tier A: "FYI — the deployment is done", "Here's the meeting summary", "Your order has shipped", GitHub PR notifications, calendar invites with no action needed

**Tier B — FYI** (mention only as a footnote, never by itself):
- Emails from real people that are informational but don't require action
- Only include if there are also Tier A emails. Do NOT notify for Tier B alone.

**Skip entirely** (the DEFAULT — most emails go here):
- ALL automated/system emails (GitHub, Jira, CI/CD, order confirmations, shipping, calendar, newsletters)
- Marketing, promotions, social media
- Informational emails that don't request action
- CC'd emails where the user is not the primary recipient

## Step 3 — If there are Tier A emails, read them in full
For each Tier A email only, use the `gmail` tool with action "read" to get the full body. Extract:
- **The specific action requested** (one sentence, e.g., "Send the Q4 invoice to finance@acme.com")
- **The deadline** (if stated)
- **One key detail** (if critical for the action)

If after reading the full email you realize it's not actually asking for action, downgrade it to Skip.

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
- When in doubt, SKIP the email. Only notify for clear, direct action requests from real people.
- NEVER call slack_notify if there are no Tier A emails. Silence is better than noise.
- Maximum 3 lines per email in the notification. If it's longer, cut it.
- Never include context the user already knows (project history, who people are, roles).
- ONE slack_notify call maximum. Never send multiple messages.
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
