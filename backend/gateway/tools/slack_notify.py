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
        "Send a proactive message to a Slack channel or user DM. "
        "Use this to notify the user about important findings, email summaries, or alerts. "
        "Provide 'channel' (channel ID like C0123 or user ID like U0123 for DM) and 'message'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Slack channel ID (C...) or user ID (U...) for DM. If user ID, a DM will be opened.",
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

        # If no channel specified, try to find one from recent DMs
        if not target:
            return "Error: 'channel' is required. Provide a Slack channel ID (C...) or user ID (U...) for DM."

        try:
            app = slack._app

            # If target looks like a user ID (U...), open a DM first
            if target.startswith("U"):
                conv = await app.client.conversations_open(users=[target])
                dm_channel = conv["channel"]["id"]
                await app.client.chat_postMessage(channel=dm_channel, text=message)
                return f"DM sent to user {target} (channel {dm_channel})"

            # Otherwise post to the channel directly
            await app.client.chat_postMessage(channel=target, text=message)
            return f"Message sent to channel {target}"

        except Exception as e:
            logger.exception("slack_notify failed")
            return f"Error sending Slack message: {str(e)}"


register_tool(SlackNotifyTool())
