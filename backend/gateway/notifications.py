"""
Notification System — Phase 8
Stores and delivers notifications from scheduled tasks and monitors.
Pushes real-time alerts to connected WebSocket clients and optionally to Slack.
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("gateway.notifications")


class NotificationManager:
    """Manages notifications: create, store, push to clients."""

    def __init__(self, db, ws_manager):
        self.db = db
        self.ws_manager = ws_manager

    async def create_notification(
        self,
        title: str,
        body: str,
        source: str = "system",
        level: str = "info",
        task_id: str = None,
    ) -> dict:
        """Create and broadcast a notification."""
        notif = {
            "id": f"notif-{uuid.uuid4().hex[:8]}",
            "title": title,
            "body": body[:1000],
            "source": source,
            "level": level,
            "task_id": task_id,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.db.notifications.insert_one({**notif})
        logger.info(f"Notification created: {notif['id']} — {title}")

        # Broadcast to all connected WebSocket clients
        await self._broadcast(notif)

        # Try to send via Slack if configured
        await self._send_slack(notif)

        return notif

    async def _broadcast(self, notif: dict):
        """Push notification to all connected WebSocket clients."""
        from gateway.protocol import event_message
        message = event_message("notification.new", {
            "id": notif["id"],
            "title": notif["title"],
            "body": notif["body"],
            "level": notif["level"],
            "source": notif["source"],
            "created_at": notif["created_at"],
        })

        for client in self.ws_manager.get_all_clients():
            try:
                await client.ws.send_json(message)
            except Exception:
                pass

    async def _send_slack(self, notif: dict):
        """Send notification to Slack if configured."""
        try:
            from gateway.channels import get_channel
            slack = get_channel("slack")
            if slack and slack.connected:
                # Get notification channel from config
                config = await self.db.gateway_config.find_one({"_id": "main"})
                slack_config = config.get("channels", {}).get("slack", {}) if config else {}
                notify_channel = slack_config.get("notify_channel", "")
                if notify_channel:
                    level_emoji = {"info": "info", "warning": "warning", "critical": "rotating_light"}.get(notif["level"], "bell")
                    text = f":{level_emoji}: *{notif['title']}*\n{notif['body'][:500]}"
                    await slack.send_message(notify_channel, text)
        except Exception as e:
            logger.debug(f"Slack notification skipped: {e}")

    async def list_notifications(self, limit: int = 50, unread_only: bool = False) -> list[dict]:
        query = {"read": False} if unread_only else {}
        return await self.db.notifications.find(
            query, {"_id": 0}
        ).sort("created_at", -1).to_list(limit)

    async def get_unread_count(self) -> int:
        return await self.db.notifications.count_documents({"read": False})

    async def mark_read(self, notif_id: str) -> bool:
        result = await self.db.notifications.update_one(
            {"id": notif_id}, {"$set": {"read": True}}
        )
        return result.modified_count > 0

    async def mark_all_read(self) -> int:
        result = await self.db.notifications.update_many(
            {"read": False}, {"$set": {"read": True}}
        )
        return result.modified_count

    async def clear_notifications(self) -> int:
        result = await self.db.notifications.delete_many({})
        return result.deleted_count
