"""
Slack Notify Tool — Allows the agent to proactively send messages to Slack.
Used by scheduled tasks (e.g., email triage) to push notifications.
"""
import logging
import os
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.slack_notify")

FEEDBACK_FOOTER = "\n\n_React :thumbsup: or :thumbsdown: to rate this summary_"


class SlackNotifyTool(Tool):
    name = "slack_notify"
    description = (
        "Send a proactive message to Slack. Automatically targets the last active "
        "Slack conversation. Use this to notify the user about important findings, "
        "email summaries, or alerts. Provide 'message' (required). Optionally override "
        "the target with 'channel' (a channel ID like C0123 or user ID like U0123). "
        "Set 'request_feedback' to true for email triage summaries so the user can rate them."
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Override: Slack channel ID or user ID. Omit to use last active conversation.",
            },
            "message": {
                "type": "string",
                "description": "The message text to send. Supports Slack mrkdwn formatting.",
            },
            "request_feedback": {
                "type": "boolean",
                "description": "If true, append a feedback prompt and track the message for quality feedback. Use for email triage summaries.",
            },
        },
        "required": ["message"],
    }

    async def execute(self, params: dict) -> str:
        from gateway.channels import get_channel

        message = params.get("message", "").strip()
        if not message:
            return "Error: 'message' is required."

        request_feedback = params.get("request_feedback", False)

        slack = get_channel("slack")
        if not slack or not slack.is_connected():
            return "Error: Slack is not connected. Cannot send notification."

        target = params.get("channel", "").strip()

        # Default to last active conversation (in-memory first, then DB)
        if not target:
            target = getattr(slack, "_last_active_channel", None) or ""

        if not target:
            target = await self._load_channel_from_db()

        if not target:
            return "Error: No active Slack conversation found yet. The user needs to send at least one message to the bot in Slack first."

        # Append feedback footer for triage messages
        full_message = message + FEEDBACK_FOOTER if request_feedback else message

        try:
            # Use direct API call to get message timestamp for feedback tracking
            if request_feedback and hasattr(slack, '_app') and slack._app:
                from gateway.channels.slack_channel import markdown_to_slack
                formatted = markdown_to_slack(full_message)
                resp = await slack._app.client.chat_postMessage(
                    channel=target, text=formatted
                )
                if resp.get("ok"):
                    message_ts = resp.get("ts", "")
                    # Track this message for feedback
                    if message_ts:
                        from gateway.triage_feedback import track_triage_message
                        import asyncio
                        asyncio.create_task(
                            track_triage_message(target, message_ts, message)
                        )
                    return f"Slack notification sent successfully to {target} (feedback tracking enabled)"
                return "Error: Slack API returned not-ok response."
            else:
                ok = await slack.send_message(target, full_message)
                if ok:
                    return f"Slack notification sent successfully to {target}"
                return "Error: send_message returned False — check Slack connection."
        except Exception as e:
            logger.exception("slack_notify failed")
            return f"Error sending Slack message: {str(e)}"

    async def _load_channel_from_db(self) -> str:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            doc = await db.settings.find_one({"key": "slack_last_active_channel"})
            if doc and doc.get("value"):
                return doc["value"]
        except Exception as e:
            logger.debug(f"Failed to load channel from DB: {e}")
        return ""


register_tool(SlackNotifyTool())
