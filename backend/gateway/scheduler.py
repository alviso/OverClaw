"""
Task Scheduler / Heartbeat — Phase 8
Background task runner that executes agent turns on a schedule.
Inspired by OpenClaw's HEARTBEAT.md daemon.

Tasks are stored in MongoDB and run as regular agent turns with full tool access.
When a task detects something noteworthy, it creates a notification.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("gateway.scheduler")

# Minimum interval to prevent abuse
MIN_INTERVAL_SECONDS = 10
MAX_TASKS = 50


class TaskScheduler:
    """Manages and runs scheduled background tasks."""

    def __init__(self, db, agent_runner, notification_mgr, ws_manager):
        self.db = db
        self.agent_runner = agent_runner
        self.notification_mgr = notification_mgr
        self.ws_manager = ws_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Task scheduler started")

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task scheduler stopped")

    async def _loop(self):
        """Main scheduler loop — checks for due tasks every 5 seconds."""
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Scheduler tick error")
            await asyncio.sleep(5)

    async def _tick(self):
        """Check for tasks that are due and execute them."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # Safety: reset tasks stuck in 'running' for over 5 minutes
        five_min_ago = (now - timedelta(minutes=5)).isoformat()
        await self.db.tasks.update_many(
            {"running": True, "last_run": {"$lt": five_min_ago}},
            {"$set": {"running": False}},
        )

        # Find enabled tasks where next_run <= now
        due_tasks = await self.db.tasks.find({
            "enabled": True,
            "next_run": {"$lte": now_iso},
            "running": {"$ne": True},
        }, {"_id": 0}).to_list(10)

        for task in due_tasks:
            asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: dict):
        """Execute a single scheduled task."""
        task_id = task["id"]
        logger.info(f"Executing task: {task_id} ({task.get('name', '')})")

        # Mark as running
        await self.db.tasks.update_one(
            {"id": task_id},
            {"$set": {"running": True, "last_run": datetime.now(timezone.utc).isoformat()}},
        )

        session_id = f"task:{task_id}"
        agent_id = task.get("agent_id", "default")
        prompt = task.get("prompt", "")

        # Keep task session lean — clear old messages before each run
        # The task uses memory_search for recall, not chat history
        await self.db.chat_messages.delete_many({"session_id": session_id})

        try:
            response, tool_calls = await self.agent_runner.run_turn(
                session_id=session_id,
                user_text=prompt,
                agent_id=agent_id,
            )

            # Store execution result
            result_entry = {
                "task_id": task_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response": response[:2000],
                "tool_calls_count": len(tool_calls),
                "status": "success",
            }
            await self.db.task_history.insert_one(result_entry)

            # Check if we should notify — look for notification triggers
            should_notify = self._should_notify(task, response, tool_calls)
            if should_notify:
                await self.notification_mgr.create_notification(
                    title=task.get("name", task_id),
                    body=response[:500],
                    source=f"task:{task_id}",
                    level=task.get("notify_level", "info"),
                    task_id=task_id,
                )

            logger.info(f"Task {task_id} completed (notify={should_notify})")

        except Exception as e:
            logger.exception(f"Task {task_id} failed")
            result_entry = {
                "task_id": task_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response": str(e)[:500],
                "tool_calls_count": 0,
                "status": "error",
            }
            await self.db.task_history.insert_one(result_entry)

        finally:
            # Calculate next_run and unmark running
            interval = max(task.get("interval_seconds", 60), MIN_INTERVAL_SECONDS)
            next_run = datetime.now(timezone.utc).timestamp() + interval
            next_run_iso = datetime.fromtimestamp(next_run, tz=timezone.utc).isoformat()
            await self.db.tasks.update_one(
                {"id": task_id},
                {"$set": {"running": False, "next_run": next_run_iso}},
            )

    def _should_notify(self, task: dict, response: str, tool_calls: list) -> bool:
        """Determine if a task result should trigger a notification."""
        notify_mode = task.get("notify", "on_change")

        if notify_mode == "always":
            return True
        if notify_mode == "never":
            return False

        # "on_change" — notify if response contains change indicators
        change_indicators = [
            "changed", "new message", "notification", "alert", "detected",
            "different", "updated", "appeared", "found something",
            "NOTIFY:", "ALERT:", "CHANGED:",
        ]
        response_lower = response.lower()
        for indicator in change_indicators:
            if indicator.lower() in response_lower:
                return True

        # Also notify if any monitor tool detected a change
        for tc in tool_calls:
            if tc.get("tool") == "monitor_url":
                result = tc.get("result", "")
                if "change detected" in result.lower() or "changed" in result.lower():
                    return True

        return False

    # ── CRUD operations ──────────────────────────────────────────────────

    async def create_task(self, params: dict) -> dict:
        """Create a new scheduled task."""
        count = await self.db.tasks.count_documents({})
        if count >= MAX_TASKS:
            raise ValueError(f"Maximum of {MAX_TASKS} tasks reached")

        task_id = params.get("id") or f"task-{uuid.uuid4().hex[:8]}"
        interval = max(int(params.get("interval_seconds", 60)), MIN_INTERVAL_SECONDS)

        task = {
            "id": task_id,
            "name": params.get("name", task_id),
            "description": params.get("description", ""),
            "prompt": params.get("prompt", ""),
            "agent_id": params.get("agent_id", "default"),
            "interval_seconds": interval,
            "enabled": params.get("enabled", True),
            "notify": params.get("notify", "on_change"),
            "notify_level": params.get("notify_level", "info"),
            "running": False,
            "last_run": None,
            "next_run": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.db.tasks.insert_one({**task})
        logger.info(f"Task created: {task_id} (interval={interval}s)")
        return task

    async def list_tasks(self) -> list[dict]:
        return await self.db.tasks.find({}, {"_id": 0}).to_list(MAX_TASKS)

    async def get_task(self, task_id: str) -> dict | None:
        return await self.db.tasks.find_one({"id": task_id}, {"_id": 0})

    async def update_task(self, task_id: str, updates: dict) -> dict | None:
        allowed = {"name", "description", "prompt", "agent_id", "interval_seconds", "enabled", "notify", "notify_level"}
        update_doc = {k: v for k, v in updates.items() if k in allowed}
        if not update_doc:
            return None
        if "interval_seconds" in update_doc:
            update_doc["interval_seconds"] = max(int(update_doc["interval_seconds"]), MIN_INTERVAL_SECONDS)
        update_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.db.tasks.update_one({"id": task_id}, {"$set": update_doc})
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        result = await self.db.tasks.delete_one({"id": task_id})
        if result.deleted_count > 0:
            await self.db.task_history.delete_many({"task_id": task_id})
            logger.info(f"Task deleted: {task_id}")
            return True
        return False

    async def pause_task(self, task_id: str) -> bool:
        result = await self.db.tasks.update_one({"id": task_id}, {"$set": {"enabled": False}})
        return result.modified_count > 0

    async def resume_task(self, task_id: str) -> bool:
        next_run = datetime.now(timezone.utc).isoformat()
        result = await self.db.tasks.update_one(
            {"id": task_id},
            {"$set": {"enabled": True, "next_run": next_run}},
        )
        return result.modified_count > 0

    async def get_history(self, task_id: str, limit: int = 20) -> list[dict]:
        return await self.db.task_history.find(
            {"task_id": task_id}, {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)

    async def run_now(self, task_id: str) -> bool:
        """Trigger a task to run immediately."""
        task = await self.get_task(task_id)
        if not task:
            return False
        task["enabled"] = True
        asyncio.create_task(self._execute_task(task))
        return True
