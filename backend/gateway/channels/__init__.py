"""
Channel abstraction layer — Phase 4
Defines the ChannelAdapter interface and registry.
Inspired by OpenClaw's src/channels/plugins/types.plugin.ts (simplified from 15+ adapters to 5).
"""
import logging
from typing import Optional

logger = logging.getLogger("gateway.channels")


class ChannelAdapter:
    """Base interface for all messaging channels."""
    id: str = ""
    name: str = ""

    async def setup(self, config: dict) -> bool:
        """Start the channel connection. Returns True if successful."""
        raise NotImplementedError

    async def teardown(self):
        """Stop the channel connection."""
        pass

    async def send_message(self, target: str, text: str, thread_id: Optional[str] = None) -> bool:
        """Send a message to a target (user/channel)."""
        raise NotImplementedError

    def is_connected(self) -> bool:
        return False

    def get_status(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "connected": self.is_connected(),
            "status": "active" if self.is_connected() else "disconnected",
        }


# ── Registry ─────────────────────────────────────────────────────────────
_channels: dict[str, ChannelAdapter] = {}


def register_channel(adapter: ChannelAdapter):
    _channels[adapter.id] = adapter
    logger.info(f"Channel registered: {adapter.id} ({adapter.name})")


def get_channel(channel_id: str) -> ChannelAdapter | None:
    return _channels.get(channel_id)


def list_channels() -> list[dict]:
    return [ch.get_status() for ch in _channels.values()]


async def start_channels(config):
    """Start all enabled channels."""
    for ch in _channels.values():
        try:
            await ch.setup(config)
        except Exception as e:
            logger.error(f"Failed to start channel {ch.id}: {e}")


async def stop_channels():
    """Stop all channels."""
    for ch in _channels.values():
        try:
            await ch.teardown()
        except Exception:
            pass
