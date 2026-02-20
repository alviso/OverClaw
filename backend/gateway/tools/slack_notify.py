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
        "Provide 'message' (required) and optionally 'channel' (channel ID like C0123, or user ID like U0123 for DM). "
        "If no channel is given, the tool will try to DM the workspace owner."
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Slack channel ID (C...) or user ID (U...) for DM. Optional — auto-discovers if omitted.",
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
        app = slack._app

        try:
            # Auto-discover target if not provided
            if not target:
                target = await self._find_notify_target(app)
                if not target:
                    return "Error: Could not find a Slack channel to notify. Please provide a 'channel' parameter (channel ID or user ID)."

            # If target is a user ID (U...), open a DM first
            if target.startswith("U"):
                try:
                    conv = await app.client.conversations_open(users=[target])
                    dm_channel = conv["channel"]["id"]
                    await app.client.chat_postMessage(channel=dm_channel, text=message)
                    return f"DM sent to user {target}"
                except Exception as e:
                    return f"Error opening DM with {target}: {e}"

            # Post to channel
            await app.client.chat_postMessage(channel=target, text=message)
            return f"Message sent to {target}"

        except Exception as e:
            logger.exception("slack_notify failed")
            return f"Error sending Slack message: {str(e)}"

    async def _find_notify_target(self, app) -> str:
        """Try to auto-discover the best notification target."""
        try:
            # Check if there's a stored notification channel preference
            from gateway.tools.gmail import _db
            if _db:
                pref = await _db.settings.find_one({"key": "slack_notify_channel"})
                if pref and pref.get("value"):
                    return pref["value"]

            # Try to get the workspace owner's user ID from auth.test
            auth = await app.client.auth_test()
            # The bot's own user ID — we can't DM ourselves, but this confirms connectivity
            # Try conversations.list for DM channels the bot has
            try:
                convs = await app.client.conversations_list(types="im", limit=5)
                if convs.get("ok") and convs.get("channels"):
                    # Return the first DM channel
                    return convs["channels"][0]["id"]
            except Exception:
                pass  # Missing scope — that's OK

        except Exception as e:
            logger.debug(f"Auto-discover failed: {e}")

        return ""


register_tool(SlackNotifyTool())
