"""
Slack Notify Tool — Allows the agent to proactively send messages to Slack.
Used by scheduled tasks (e.g., email triage) to push notifications.
"""
import logging
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.slack_notify")


class SlackNotifyTool(Tool):
    name = "slack_notify"
    description = (
        "Send a proactive message to Slack. Automatically targets the last active "
        "Slack conversation. Use this to notify the user about important findings, "
        "email summaries, or alerts. Provide 'message' (required). Optionally override "
        "the target with 'channel' (a channel ID like C0123 or user ID like U0123)."
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
        },
        "required": ["message"],
    }

    async def execute(self, params: dict) -> str:
        from gateway.channels import get_channel

        message = params.get("message", "").strip()
        if not message:
            return "Error: 'message' is required."

        slack = get_channel("slack")
        if not slack or not slack.is_connected():
            return "Error: Slack is not connected. Cannot send notification."

        target = params.get("channel", "").strip()

        # Default to last active conversation
        if not target:
            target = getattr(slack, "_last_active_channel", None) or ""

        if not target:
            return "Error: No active Slack conversation found yet. The user needs to send at least one message to the bot in Slack first."

        try:
            ok = await slack.send_message(target, message)
            if ok:
                return f"Message sent to Slack ({target})"
            return "Error: send_message returned False — check Slack connection."
        except Exception as e:
            logger.exception("slack_notify failed")
            return f"Error sending Slack message: {str(e)}"


register_tool(SlackNotifyTool())
