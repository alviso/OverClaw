"""
Slack Channel Adapter — Phase 4
Uses slack-bolt for Python. Handles inbound messages, mention gating, thread support.
Handles file attachments (PDF, images, audio) by downloading and passing to agent tools.
"""
import asyncio
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import httpx

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from gateway.channels import ChannelAdapter, register_channel

logger = logging.getLogger("gateway.channels.slack")

UPLOAD_DIR = Path("/tmp/gateway_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class SlackBearerAuth(httpx.Auth):
    """Custom httpx auth that persists the Bearer token across redirects."""
    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request

FILE_TYPE_MAP = {
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image",
    ".webp": "image", ".bmp": "image", ".svg": "image",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".flac": "audio",
    ".m4a": "audio", ".webm": "audio", ".mpga": "audio", ".mpeg": "audio",
    ".pdf": "document", ".docx": "document", ".doc": "document",
    ".txt": "document", ".csv": "document", ".json": "document",
    ".xml": "document", ".md": "document", ".yaml": "document",
    ".yml": "document", ".log": "document",
    ".py": "document", ".js": "document", ".ts": "document",
    ".html": "document", ".css": "document",
}

TOOL_FOR_TYPE = {
    "image": "analyze_image",
    "audio": "transcribe_audio",
    "document": "parse_document",
}


class SlackChannel(ChannelAdapter):
    id = "slack"
    name = "Slack"

    def __init__(self):
        self._app: Optional[AsyncApp] = None
        self._handler: Optional[AsyncSocketModeHandler] = None
        self._connected = False
        self._bot_user_id: Optional[str] = None
        self._bot_token: Optional[str] = None
        self._on_message = None  # Callback: async (channel, user, text, thread_ts) -> str
        self._background_tasks: set = set()  # prevent GC of background tasks
        self._handler_task = None  # reference to socket mode handler task
        self._app_token: Optional[str] = None
        self._last_active_channel: Optional[str] = None

    def set_message_handler(self, handler):
        """Set the callback for incoming messages."""
        self._on_message = handler

    def is_connected(self) -> bool:
        return self._connected

    def get_status(self) -> dict:
        base = super().get_status()
        base["bot_user_id"] = self._bot_user_id
        return base

    async def setup(self, config) -> bool:
        slack_cfg = config.channels.slack
        if not slack_cfg.enabled:
            logger.info("Slack: disabled in config")
            return False

        bot_token = slack_cfg.bot_token
        app_token = slack_cfg.app_token

        if not bot_token or not app_token:
            logger.warning("Slack: bot_token or app_token missing")
            return False

        try:
            self._app = AsyncApp(token=bot_token)
            self._bot_token = bot_token

            # Get bot user ID
            auth = await self._app.client.auth_test()
            self._bot_user_id = auth.get("user_id")
            logger.info(f"Slack: authenticated as {auth.get('user', 'unknown')} ({self._bot_user_id})")

            # Register message handler
            @self._app.event("message")
            async def handle_message(event, say):
                logger.info(f"Slack EVENT received: type=message user={event.get('user','?')} text={str(event.get('text',''))[:60]}")
                await self._process_message(event, say)

            @self._app.event("app_mention")
            async def handle_mention(event, say):
                logger.info(f"Slack EVENT received: type=app_mention user={event.get('user','?')}")
                await self._process_message(event, say)

            # Listen for reactions on triage messages
            @self._app.event("reaction_added")
            async def handle_reaction(event):
                await self._process_reaction(event)

            # Start Socket Mode — save reference to prevent GC
            self._app_token = app_token
            self._handler = AsyncSocketModeHandler(self._app, app_token)
            self._handler_task = asyncio.create_task(self._run_handler())

            self._connected = True
            logger.info("Slack: connected via Socket Mode")
            return True

        except Exception as e:
            logger.exception(f"Slack: setup failed: {e}")
            self._connected = False
            return False

    async def _run_handler(self):
        """Run Socket Mode with automatic reconnection on silent drops."""
        max_retries = 50
        for attempt in range(max_retries):
            try:
                logger.info(f"Slack: starting Socket Mode handler (attempt {attempt + 1})...")
                # Start the handler in a task so we can run health checks alongside it
                handler_task = asyncio.create_task(self._handler.start_async())
                health_task = asyncio.create_task(self._health_check_loop())

                # Wait for either task to finish (handler crash or health check failure)
                done, pending = await asyncio.wait(
                    [handler_task, health_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # Cancel the other task
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

                # Check what happened
                for t in done:
                    exc = t.exception() if not t.cancelled() else None
                    if t is handler_task:
                        if exc:
                            logger.error(f"Slack: socket mode handler crashed: {exc}")
                        else:
                            logger.warning("Slack: Socket Mode handler exited normally (unexpected)")
                    elif t is health_task:
                        logger.warning("Slack: health check detected dead connection, forcing reconnect")

            except Exception as e:
                logger.error(f"Slack: socket mode error: {e}")

            # Teardown current handler before recreating
            try:
                if self._handler:
                    await self._handler.close_async()
            except Exception:
                pass

            # Reconnect after a brief delay with backoff
            if attempt < max_retries - 1:
                wait = min(5 * (attempt + 1), 30)
                logger.info(f"Slack: reconnecting in {wait}s (attempt {attempt + 2})...")
                await asyncio.sleep(wait)
                try:
                    self._handler = AsyncSocketModeHandler(self._app, self._app_token)
                except Exception as e:
                    logger.error(f"Slack: failed to recreate handler: {e}")
                    break

        self._connected = False
        logger.error("Slack: Socket Mode handler stopped after max retries")

    async def _health_check_loop(self):
        """Periodically ping Slack API to detect silent connection drops."""
        consecutive_failures = 0
        max_failures = 3
        check_interval = 30  # seconds

        # Initial grace period to let the connection establish
        await asyncio.sleep(15)

        while True:
            try:
                resp = await self._app.client.auth_test()
                if resp.get("ok"):
                    consecutive_failures = 0
                    logger.debug("Slack: health check OK")
                else:
                    consecutive_failures += 1
                    logger.warning(f"Slack: health check returned not-ok ({consecutive_failures}/{max_failures})")
            except Exception as e:
                consecutive_failures += 1
                logger.warning(f"Slack: health check failed ({consecutive_failures}/{max_failures}): {e}")

            if consecutive_failures >= max_failures:
                logger.error(f"Slack: {max_failures} consecutive health check failures — triggering reconnect")
                return  # Exit the health check loop → triggers reconnect in _run_handler

            await asyncio.sleep(check_interval)

    async def _download_slack_file(self, file_info: dict) -> Optional[dict]:
        """Download a file from Slack and save it locally.
        Uses httpx custom Auth to persist the bearer token across redirects,
        since Slack's file URLs 302 to a different host which normally drops Authorization.
        """
        url = file_info.get("url_private_download") or file_info.get("url_private")
        if not url:
            return None

        name = file_info.get("name", "unknown_file")
        ext = os.path.splitext(name)[1].lower()
        file_type = FILE_TYPE_MAP.get(ext, "unknown")

        try:
            # Custom auth that re-attaches token on every request (including redirects)
            auth = SlackBearerAuth(self._bot_token)
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, auth=auth) as client:
                resp = await client.get(url)

                if resp.status_code != 200:
                    logger.error(f"Slack file download failed: {resp.status_code} for {name}")
                    return None

                content = resp.content
                # Verify we got a real file, not an HTML login page
                stripped = content[:30].lstrip().lower()
                if stripped.startswith(b'<!doctype') or stripped.startswith(b'<html'):
                    logger.error(f"Slack file download returned HTML page instead of file for {name} (missing files:read scope?)")
                    return None

                safe_name = f"{uuid.uuid4().hex[:8]}_{name}"
                file_path = UPLOAD_DIR / safe_name
                file_path.write_bytes(content)

                logger.info(f"Slack file downloaded: {name} -> {file_path} ({len(content)} bytes)")
                return {
                    "path": str(file_path),
                    "name": name,
                    "type": file_type,
                    "size": len(content),
                    "tool": TOOL_FOR_TYPE.get(file_type),
                }
        except Exception as e:
            logger.exception(f"Slack file download error for {name}: {e}")
            return None

    async def _process_message(self, event: dict, say):
        """Process an incoming Slack message."""
        # Ignore bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            logger.debug(f"Slack: ignoring bot message subtype={event.get('subtype')}")
            return

        user = event.get("user", "")
        text = event.get("text", "")
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        channel_type = event.get("channel_type", "")

        # Strip bot mention from text
        if self._bot_user_id:
            text = re.sub(rf"<@{self._bot_user_id}>\s*", "", text).strip()

        # Handle file attachments
        files = event.get("files", [])
        file_contexts = []
        if files and self._bot_token:
            for f in files:
                downloaded = await self._download_slack_file(f)
                if downloaded:
                    ctx = f"[Attached file: {downloaded['name']} ({downloaded['type']}) at {downloaded['path']}]"
                    if downloaded["tool"]:
                        ctx += f"\nUse the {downloaded['tool']} tool with file_path=\"{downloaded['path']}\" to process this file."
                    file_contexts.append(ctx)

        # Build the full message text
        if file_contexts:
            file_block = "\n".join(file_contexts)
            if text:
                text = f"{file_block}\n\n{text}"
            else:
                text = f"{file_block}\n\nPlease process the attached file(s)."

        if not text:
            logger.debug("Slack: ignoring empty message")
            return

        # ── Slash-style commands (handled before the agent) ──
        stripped_cmd = text.strip().lower()
        if stripped_cmd.startswith("!"):
            await self._handle_command(stripped_cmd, channel, user)
            return

        logger.info(f"Slack message ACCEPTED: user={user} channel={channel} dm={channel_type} files={len(files)} text={text[:80]}")

        # Persist last active conversation for proactive notifications
        self._last_active_channel = channel
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            import os
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            _db = client[os.environ["DB_NAME"]]
            asyncio.create_task(
                _db.settings.update_one(
                    {"key": "slack_last_active_channel"},
                    {"$set": {"value": channel, "user": user}},
                    upsert=True,
                )
            )
        except Exception:
            pass

        # Run message handling in background so it doesn't block other Slack events
        # Use direct API calls instead of say() for reliability from background tasks
        task = asyncio.create_task(self._handle_message_async(text, channel, user, thread_ts))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _handle_command(self, cmd: str, channel: str, user: str):
        """Handle !-prefixed commands."""
        COMMANDS_HELP = (
            "*Available commands:*\n"
            "`!clear` — Clear conversation history and start fresh\n"
            "`!status` — Show agent and connection status\n"
            "`!debug` — Show active agent config (prompt, tools, model)\n"
            "`!help` — Show this help message"
        )

        if cmd == "!help":
            await self._app.client.chat_postMessage(channel=channel, text=COMMANDS_HELP)

        elif cmd == "!clear":
            session_id = f"slack:{channel}:{user}"
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                import os
                client = AsyncIOMotorClient(os.environ["MONGO_URL"])
                db = client[os.environ["DB_NAME"]]
                r1 = await db.chat_messages.delete_many({"session_id": session_id})
                await db.sessions.delete_many({"session_id": session_id})
                await self._app.client.chat_postMessage(
                    channel=channel,
                    text=f"Conversation cleared ({r1.deleted_count} messages removed). Starting fresh."
                )
                logger.info(f"Slack: cleared session {session_id} ({r1.deleted_count} msgs)")
            except Exception as e:
                logger.exception("Slack: !clear error")
                await self._app.client.chat_postMessage(
                    channel=channel, text=f"Error clearing history: {str(e)[:200]}"
                )

        elif cmd == "!status":
            from gateway.channels import get_channel
            slack_ch = get_channel("slack")
            connected = slack_ch._connected if slack_ch else False
            session_id = f"slack:{channel}:{user}"
            msg_count = 0
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                import os
                client = AsyncIOMotorClient(os.environ["MONGO_URL"])
                db = client[os.environ["DB_NAME"]]
                msg_count = await db.chat_messages.count_documents({"session_id": session_id})
            except Exception:
                pass
            await self._app.client.chat_postMessage(
                channel=channel,
                text=(
                    f"*Status*\n"
                    f"Slack connected: {'Yes' if connected else 'No'}\n"
                    f"Session: `{session_id}`\n"
                    f"Messages in history: {msg_count}\n"
                    f"Type `!help` for available commands."
                )
            )

        elif cmd == "!debug":
            # Show what agent config is active for this session
            session_id = f"slack:{channel}:{user}"
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                import os
                client = AsyncIOMotorClient(os.environ["MONGO_URL"])
                db = client[os.environ["DB_NAME"]]
                cfg = await db.gateway_config.find_one({"_id": "main"}, {"_id": 0})
                if cfg:
                    agent_cfg = cfg.get("agent", {})
                    tools = agent_cfg.get("tools_allowed", [])
                    model = agent_cfg.get("model", "?")
                    prompt_version = agent_cfg.get("prompt_version", "?")
                    prompt = agent_cfg.get("system_prompt", "")[:150]
                    has_delegate = "delegate" in tools
                    has_web_search = "web_search" in tools
                    await self._app.client.chat_postMessage(
                        channel=channel,
                        text=(
                            f"*Agent Debug Info*\n"
                            f"Session: `{session_id}`\n"
                            f"Model: `{model}`\n"
                            f"Prompt version: `{prompt_version}`\n"
                            f"Prompt preview: _{prompt}_...\n"
                            f"Tools ({len(tools)}): `{', '.join(sorted(tools))}`\n"
                            f"Has `delegate`: {'Yes' if has_delegate else '*NO — orchestrator cannot delegate!*'}\n"
                            f"Has `web_search`: {'*YES — should be removed, research goes via delegate*' if has_web_search else 'No (correct — research via delegate)'}\n"
                        )
                    )
                else:
                    await self._app.client.chat_postMessage(
                        channel=channel, text="No gateway config found in DB."
                    )
            except Exception as e:
                await self._app.client.chat_postMessage(
                    channel=channel, text=f"Debug error: {str(e)[:200]}"
                )

        else:
            await self._app.client.chat_postMessage(
                channel=channel, text=f"Unknown command: `{cmd}`\nType `!help` for available commands."
            )

    async def _process_reaction(self, event: dict):
        """Process a reaction_added event — check if it's on a triage message."""
        reaction = event.get("reaction", "")
        user = event.get("user", "")
        item = event.get("item", {})
        channel = item.get("channel", "")
        message_ts = item.get("ts", "")

        if not channel or not message_ts:
            return

        # Only care about thumbs up/down
        if reaction not in ("+1", "thumbsup", "-1", "thumbsdown"):
            return

        try:
            from gateway.triage_feedback import record_feedback
            matched = await record_feedback(channel, message_ts, reaction, user)
            if matched:
                logger.info(f"Slack: triage feedback '{reaction}' recorded from {user}")
        except Exception as e:
            logger.debug(f"Slack: reaction processing failed: {e}")

    async def _maybe_send_session_reminder(self, session_id: str, channel: str):
        """Send a one-time reminder at the start of a new conversation."""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            import os
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            msg_count = await db.chat_messages.count_documents({"session_id": session_id})
            if msg_count == 0:
                await self._app.client.chat_postMessage(
                    channel=channel,
                    text="_Tip: `!clear` to reset history, `!status` to check connection, `!help` for all commands._"
                )
        except Exception as e:
            logger.debug(f"Session reminder check failed: {e}")

    async def _handle_message_async(self, text, channel, user, thread_ts):
        """Handle a message asynchronously in the background."""
        if self._on_message:
            try:
                # Check if this is a new session — send a reminder with available commands
                session_id = f"slack:{channel}:{user}"
                await self._maybe_send_session_reminder(session_id, channel)

                logger.info(f"Slack: calling agent for user={user} channel={channel}")
                response = await self._on_message(channel, user, text, thread_ts)
                if response:
                    formatted = markdown_to_slack(response)
                    chunks = chunk_text(formatted, 3000)
                    for chunk in chunks:
                        await self._app.client.chat_postMessage(channel=channel, text=chunk)
                    logger.info(f"Slack: sent {len(chunks)} chunk(s) to channel={channel}")
                else:
                    logger.warning(f"Slack: agent returned empty response for user={user}")
            except Exception as e:
                logger.exception("Slack: message handler error")
                try:
                    await self._app.client.chat_postMessage(
                        channel=channel,
                        text=f"Sorry, I encountered an error: {str(e)[:200]}"
                    )
                except Exception:
                    logger.error("Slack: failed to send error message back to channel")

    async def send_message(self, target: str, text: str, thread_id: Optional[str] = None) -> bool:
        if not self._app or not self._connected:
            return False
        try:
            formatted = markdown_to_slack(text)
            kwargs = {"channel": target, "text": formatted}
            if thread_id:
                kwargs["thread_ts"] = thread_id
            await self._app.client.chat_postMessage(**kwargs)
            return True
        except Exception as e:
            logger.error(f"Slack: send_message failed: {e}")
            return False

    async def teardown(self):
        if self._handler_task:
            self._handler_task.cancel()
            try:
                await self._handler_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._handler:
            try:
                await self._handler.close_async()
            except Exception:
                pass
        self._connected = False
        logger.info("Slack: disconnected")


def markdown_to_slack(text: str) -> str:
    """Convert standard Markdown to Slack mrkdwn format."""
    lines = text.split("\n")
    result = []
    for line in lines:
        # Headers: ## Header → *Header*
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            header_text = header_match.group(2)
            # Strip any existing bold markers to avoid ***text***
            header_text = re.sub(r'\*\*(.+?)\*\*', r'\1', header_text)
            result.append(f"*{header_text}*")
            continue
        # Horizontal rules: --- or *** → ─── divider
        if re.match(r'^[\-\*\_]{3,}\s*$', line):
            result.append("───")
            continue
        # Bold+Italic: ***text*** → *_text_* (bold+italic in Slack)
        line = re.sub(r'\*\*\*(.+?)\*\*\*', r'*_\1_*', line)
        # Bold: **text** → *text*
        line = re.sub(r'\*\*(.+?)\*\*', r'*\1*', line)
        # Italic: single *text* that isn't already bold → _text_
        # (skip this since Slack uses * for bold — markdown italic *x* becomes bold in Slack which is fine)
        # Links: [text](url) → <url|text>
        line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', line)
        # Images: ![alt](url) → <url|alt>
        line = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<\2|\1>', line)
        result.append(line)
    return "\n".join(result)


def chunk_text(text: str, max_len: int = 3000) -> list[str]:
    """Split text into chunks respecting paragraph boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > max_len:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current += ("\n\n" if current else "") + para

    if current:
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_len]]


# Auto-register
register_channel(SlackChannel())
