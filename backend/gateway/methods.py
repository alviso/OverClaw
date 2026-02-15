"""
RPC method handlers for the Gateway.
Inspired by OpenClaw's server-methods/ directory.
Each handler receives (params, client, context) and returns a result dict.
"""
import asyncio
import logging
from gateway.health import get_health_snapshot, get_gateway_info
from gateway.config_schema import validate_config, config_to_display, AssistantConfig
from gateway.agent import AgentRunner
from gateway.protocol import event_message

logger = logging.getLogger("gateway.methods")


# ── Method registry ──────────────────────────────────────────────────────
_methods: dict = {}


def register_method(name: str):
    """Decorator to register an RPC method handler."""
    def decorator(fn):
        _methods[name] = fn
        return fn
    return decorator


def get_method(name: str):
    return _methods.get(name)


def list_methods() -> list[str]:
    return list(_methods.keys())


# ── Context object passed to all handlers ────────────────────────────────
class MethodContext:
    def __init__(self, db, ws_manager, config: AssistantConfig, activity_log: list, scheduler=None, notification_mgr=None):
        self.db = db
        self.ws_manager = ws_manager
        self.config = config
        self.activity_log = activity_log
        self._agent_runner = None
        self.scheduler = scheduler
        self.notification_mgr = notification_mgr

    @property
    def agent_runner(self) -> AgentRunner:
        if not self._agent_runner:
            self._agent_runner = AgentRunner(self.db, self.config)
            # Wire delegate tool for orchestration
            from gateway.tools.delegate import set_delegate_context
            set_delegate_context(self.db, self._agent_runner)
        return self._agent_runner


# ── Handlers ─────────────────────────────────────────────────────────────

@register_method("health.get")
async def handle_health_get(params: dict, client, ctx: MethodContext) -> dict:
    snapshot = get_health_snapshot()
    snapshot["connected_clients"] = ctx.ws_manager.client_count
    return snapshot


@register_method("config.get")
async def handle_config_get(params: dict, client, ctx: MethodContext) -> dict:
    return config_to_display(ctx.config)


@register_method("config.set")
async def handle_config_set(params: dict, client, ctx: MethodContext) -> dict:
    path = params.get("path", "")
    value = params.get("value")
    if not path:
        return {"error": "path is required"}

    # Update config in MongoDB
    config_dict = ctx.config.model_dump()
    keys = path.split(".")
    target = config_dict
    for key in keys[:-1]:
        if key not in target or not isinstance(target[key], dict):
            return {"error": f"Invalid config path: {path}"}
        target = target[key]
    target[keys[-1]] = value

    try:
        new_config = validate_config(config_dict)
        ctx.config.__dict__.update(new_config.__dict__)
        await ctx.db.gateway_config.replace_one(
            {"_id": "main"},
            {"_id": "main", **new_config.model_dump()},
            upsert=True,
        )
        logger.info(f"Config updated: {path} = {value}")
        return {"ok": True, "config": config_to_display(new_config)}
    except Exception as e:
        return {"error": f"Validation failed: {str(e)}"}


@register_method("sessions.list")
async def handle_sessions_list(params: dict, client, ctx: MethodContext) -> dict:
    sessions = await ctx.db.sessions.find({}, {"_id": 0}).to_list(100)
    return {
        "sessions": sessions,
        "count": len(sessions),
    }


@register_method("channels.status")
async def handle_channels_status(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.channels import list_channels as get_all_channels
    channels = get_all_channels()
    # Always include WebChat
    channels.append({
        "id": "webchat",
        "name": "WebChat",
        "connected": True,
        "status": "active",
        "enabled": True,
    })
    return {"channels": channels}


@register_method("gateway.info")
async def handle_gateway_info(params: dict, client, ctx: MethodContext) -> dict:
    info = get_gateway_info()
    info["connected_clients"] = ctx.ws_manager.client_count
    info["methods"] = list_methods()
    return info


@register_method("activity.recent")
async def handle_activity_recent(params: dict, client, ctx: MethodContext) -> dict:
    limit = params.get("limit", 20)
    return {"events": ctx.activity_log[-limit:]}


# ── Chat Methods (Phase 1) ──────────────────────────────────────────────

@register_method("chat.send")
async def handle_chat_send(params: dict, client, ctx: MethodContext) -> dict:
    """
    Send a message to the agent. Runs the agent turn with tool calling,
    streams chat.event messages back, then returns full response.
    """
    session_id = params.get("session_id", "main")
    text = (params.get("text") or params.get("message") or "").strip()
    agent_id = params.get("agent_id")  # Optional: explicit agent override
    if not text:
        return {"error": "text is required"}

    runner = ctx.agent_runner

    from datetime import datetime as dt, timezone as tz

    def now():
        return dt.now(tz.utc).isoformat()

    async def safe_send(data):
        """Send to WS, swallow errors if client disconnected."""
        try:
            await client.ws.send_json(data)
        except Exception:
            pass  # Client gone — agent turn will still complete & persist

    ctx.activity_log.append({
        "type": "chat.send",
        "detail": f"Message to '{session_id}': {text[:60]}{'...' if len(text) > 60 else ''}",
        "timestamp": now(),
    })

    await safe_send(event_message("chat.event", {
        "session_id": session_id,
        "type": "status",
        "status": "thinking",
    }))

    async def on_tool_call(tool_name, tool_args, status):
        """Callback to stream tool execution events to client."""
        await safe_send(event_message("chat.event", {
            "session_id": session_id,
            "type": "tool_call",
            "tool": tool_name,
            "args": tool_args,
            "status": status,
        }))

    # Keepalive: send periodic pings during long agent turns
    keepalive_running = True

    async def keepalive():
        while keepalive_running:
            await asyncio.sleep(8)
            if keepalive_running:
                await safe_send(event_message("chat.event", {
                    "session_id": session_id,
                    "type": "status",
                    "status": "thinking",
                }))

    keepalive_task = asyncio.create_task(keepalive())

    try:
        try:
            response, tool_calls = await runner.run_turn(session_id, text, on_tool_call=on_tool_call, agent_id=agent_id)
        finally:
            keepalive_running = False
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass

        await safe_send(event_message("chat.event", {
            "session_id": session_id,
            "type": "text.done",
            "text": response,
            "tool_calls": tool_calls,
        }))

        ctx.activity_log.append({
            "type": "chat.response",
            "detail": f"Response for '{session_id}' ({len(tool_calls)} tools): {response[:60]}{'...' if len(response) > 60 else ''}",
            "timestamp": now(),
        })

        return {
            "ok": True,
            "session_id": session_id,
            "response": response,
            "tool_calls": tool_calls,
        }

    except Exception as e:
        logger.exception(f"chat.send error for session {session_id}")
        await safe_send(event_message("chat.event", {
            "session_id": session_id,
            "type": "error",
            "error": str(e),
        }))
        return {"error": str(e)}


@register_method("chat.history")
async def handle_chat_history(params: dict, client, ctx: MethodContext) -> dict:
    """Get chat history for a session."""
    session_id = params.get("session_id", "main")
    limit = params.get("limit", 50)
    messages = await ctx.db.chat_messages.find(
        {"session_id": session_id},
        {"_id": 0}
    ).sort("timestamp", 1).to_list(limit)
    return {"session_id": session_id, "messages": messages}


@register_method("chat.clear")
async def handle_chat_clear(params: dict, client, ctx: MethodContext) -> dict:
    session_id = params.get("session_id", "main")
    runner = ctx.agent_runner
    await runner.session_mgr.clear_session(session_id)

    from datetime import datetime as dt, timezone as tz
    ctx.activity_log.append({
        "type": "chat.clear",
        "detail": f"Session '{session_id}' cleared",
        "timestamp": dt.now(tz.utc).isoformat(),
    })

    return {"ok": True, "session_id": session_id}


@register_method("chat.delete")
async def handle_chat_delete(params: dict, client, ctx: MethodContext) -> dict:
    """Delete a session and all its messages."""
    session_id = params.get("session_id", "")
    if not session_id:
        return {"error": "session_id is required"}
    await ctx.db.chat_messages.delete_many({"session_id": session_id})
    await ctx.db.sessions.delete_one({"session_id": session_id})

    from datetime import datetime as dt, timezone as tz
    ctx.activity_log.append({
        "type": "chat.delete",
        "detail": f"Session '{session_id}' deleted",
        "timestamp": dt.now(tz.utc).isoformat(),
    })
    return {"ok": True, "deleted": session_id}


@register_method("models.list")
async def handle_models_list(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.agent import PROVIDER_MAP
    models = []
    for key, (provider, model_id, _) in PROVIDER_MAP.items():
        models.append({"id": key, "provider": provider, "model": model_id})
    return {"models": models, "current": ctx.config.agent.model}


@register_method("tools.list")
async def handle_tools_list(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.tools import list_tools
    return {"tools": list_tools()}


@register_method("channels.restart")
async def handle_channels_restart(params: dict, client, ctx: MethodContext) -> dict:
    """Restart all channels (re-read config, reconnect)."""
    from gateway.channels import stop_channels, start_channels, list_channels as get_all_channels, get_channel
    from gateway.agent import AgentRunner

    await stop_channels()

    # Re-wire Slack message handler
    slack = get_channel("slack")
    if slack:
        agent_runner = AgentRunner(ctx.db, ctx.config)

        async def handle_slack_message(channel, user, text, thread_ts):
            session_id = f"slack:{channel}:{user}"
            response, tool_calls = await agent_runner.run_turn(session_id, text)
            return response

        slack.set_message_handler(handle_slack_message)

    await start_channels(ctx.config)

    from datetime import datetime as dt, timezone as tz
    ctx.activity_log.append({
        "type": "channels.restart",
        "detail": "Channels restarted",
        "timestamp": dt.now(tz.utc).isoformat(),
    })

    return {"ok": True, "channels": get_all_channels()}


# ── Agent Management (Phase 5) ──────────────────────────────────────────

@register_method("agents.list")
async def handle_agents_list(params: dict, client, ctx: MethodContext) -> dict:
    """List all agent definitions."""
    agents = await ctx.db.agents.find({}, {"_id": 0}).to_list(100)
    # Always include the default agent
    has_default = any(a["id"] == "default" for a in agents)
    if not has_default:
        agents.insert(0, {
            "id": "default",
            "name": "Default Agent",
            "description": "General-purpose assistant",
            "model": ctx.config.agent.model,
            "system_prompt": ctx.config.agent.system_prompt,
            "max_context_messages": ctx.config.agent.max_context_messages,
            "tools_allowed": ctx.config.agent.tools_allowed,
            "enabled": True,
        })
    return {"agents": agents}


@register_method("agents.get")
async def handle_agents_get(params: dict, client, ctx: MethodContext) -> dict:
    agent_id = params.get("id", "")
    if not agent_id:
        return {"error": "id is required"}
    if agent_id == "default":
        return {
            "id": "default", "name": "Default Agent",
            "description": "General-purpose assistant",
            "model": ctx.config.agent.model,
            "system_prompt": ctx.config.agent.system_prompt,
            "max_context_messages": ctx.config.agent.max_context_messages,
            "tools_allowed": ctx.config.agent.tools_allowed,
            "enabled": True,
        }
    agent = await ctx.db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        return {"error": f"Agent not found: {agent_id}"}
    return agent


@register_method("agents.create")
async def handle_agents_create(params: dict, client, ctx: MethodContext) -> dict:
    """Create a new agent definition."""
    agent_id = params.get("id", "").strip().lower().replace(" ", "-")
    if not agent_id or agent_id == "default":
        return {"error": "id is required and cannot be 'default'"}

    existing = await ctx.db.agents.find_one({"id": agent_id})
    if existing:
        return {"error": f"Agent '{agent_id}' already exists"}

    agent = {
        "id": agent_id,
        "name": params.get("name", agent_id),
        "description": params.get("description", ""),
        "model": params.get("model", ctx.config.agent.model),
        "system_prompt": params.get("system_prompt", "You are a helpful assistant."),
        "max_context_messages": params.get("max_context_messages", 50),
        "tools_allowed": params.get("tools_allowed", ["web_search", "read_file", "list_files"]),
        "enabled": params.get("enabled", True),
    }
    await ctx.db.agents.insert_one({**agent})

    from datetime import datetime as dt, timezone as tz
    ctx.activity_log.append({
        "type": "agent.create",
        "detail": f"Agent created: {agent_id} ({agent.get('name')})",
        "timestamp": dt.now(tz.utc).isoformat(),
    })
    return {"ok": True, "agent": agent}


@register_method("agents.update")
async def handle_agents_update(params: dict, client, ctx: MethodContext) -> dict:
    """Update an existing agent definition."""
    agent_id = params.get("id", "")
    if not agent_id:
        return {"error": "id is required"}
    if agent_id == "default":
        # Update global config for default agent
        updates = {}
        for key in ["model", "system_prompt", "max_context_messages", "tools_allowed"]:
            if key in params:
                updates[f"agent.{key}"] = params[key]
        if updates:
            for path, value in updates.items():
                keys = path.split(".")
                config_dict = ctx.config.model_dump()
                target = config_dict
                for k in keys[:-1]:
                    target = target[k]
                target[keys[-1]] = value
                new_config = validate_config(config_dict)
                ctx.config.__dict__.update(new_config.__dict__)
            await ctx.db.gateway_config.replace_one(
                {"_id": "main"}, {"_id": "main", **ctx.config.model_dump()}, upsert=True
            )
        return {"ok": True, "agent": {"id": "default", **ctx.config.agent.model_dump()}}

    update_fields = {}
    for key in ["name", "description", "model", "system_prompt", "max_context_messages", "tools_allowed", "enabled"]:
        if key in params:
            update_fields[key] = params[key]

    if not update_fields:
        return {"error": "No fields to update"}

    result = await ctx.db.agents.update_one({"id": agent_id}, {"$set": update_fields})
    if result.matched_count == 0:
        return {"error": f"Agent not found: {agent_id}"}

    agent = await ctx.db.agents.find_one({"id": agent_id}, {"_id": 0})
    return {"ok": True, "agent": agent}


@register_method("agents.delete")
async def handle_agents_delete(params: dict, client, ctx: MethodContext) -> dict:
    agent_id = params.get("id", "")
    if not agent_id or agent_id == "default":
        return {"error": "Cannot delete the default agent"}

    result = await ctx.db.agents.delete_one({"id": agent_id})
    if result.deleted_count == 0:
        return {"error": f"Agent not found: {agent_id}"}

    from datetime import datetime as dt, timezone as tz
    ctx.activity_log.append({
        "type": "agent.delete",
        "detail": f"Agent deleted: {agent_id}",
        "timestamp": dt.now(tz.utc).isoformat(),
    })
    return {"ok": True, "deleted": agent_id}


# ── Routing (Phase 5) ───────────────────────────────────────────────────

@register_method("routing.list")
async def handle_routing_list(params: dict, client, ctx: MethodContext) -> dict:
    return {"routes": [r.model_dump() for r in ctx.config.routing]}


@register_method("routing.set")
async def handle_routing_set(params: dict, client, ctx: MethodContext) -> dict:
    """Replace all routing rules."""
    routes = params.get("routes", [])
    config_dict = ctx.config.model_dump()
    config_dict["routing"] = routes
    new_config = validate_config(config_dict)
    ctx.config.__dict__.update(new_config.__dict__)
    await ctx.db.gateway_config.replace_one(
        {"_id": "main"}, {"_id": "main", **new_config.model_dump()}, upsert=True
    )
    return {"ok": True, "routes": [r.model_dump() for r in new_config.routing]}


# ── Skills (Phase 6) ─────────────────────────────────────────────────────

@register_method("skills.list")
async def handle_skills_list(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.skills import SkillManager
    mgr = SkillManager(ctx.db)
    skills = await mgr.list_skills()
    return {"skills": skills}


@register_method("skills.get")
async def handle_skills_get(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.skills import SkillManager
    skill_id = params.get("id", "")
    if not skill_id:
        return {"error": "id is required"}
    mgr = SkillManager(ctx.db)
    skill = await mgr.get_skill(skill_id)
    if not skill:
        return {"error": f"Skill not found: {skill_id}"}
    return skill


@register_method("skills.create")
async def handle_skills_create(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.skills import SkillManager
    mgr = SkillManager(ctx.db)
    try:
        skill = await mgr.create_skill(params)
        from datetime import datetime as dt, timezone as tz
        ctx.activity_log.append({
            "type": "skill.create",
            "detail": f"Skill created: {skill['id']}",
            "timestamp": dt.now(tz.utc).isoformat(),
        })
        return {"ok": True, "skill": skill}
    except ValueError as e:
        return {"error": str(e)}


@register_method("skills.update")
async def handle_skills_update(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.skills import SkillManager
    skill_id = params.get("id", "")
    if not skill_id:
        return {"error": "id is required"}
    mgr = SkillManager(ctx.db)
    skill = await mgr.update_skill(skill_id, params)
    if not skill:
        return {"error": f"Skill not found or no fields to update: {skill_id}"}
    return {"ok": True, "skill": skill}


@register_method("skills.delete")
async def handle_skills_delete(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.skills import SkillManager
    skill_id = params.get("id", "")
    if not skill_id:
        return {"error": "id is required"}
    mgr = SkillManager(ctx.db)
    deleted = await mgr.delete_skill(skill_id)
    if not deleted:
        return {"error": f"Skill not found: {skill_id}"}
    return {"ok": True, "deleted": skill_id}


# ── Memory (Phase 7) ─────────────────────────────────────────────────────

@register_method("memory.search")
async def handle_memory_search(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.memory import MemoryManager
    query = params.get("query", "")
    if not query:
        return {"error": "query is required"}
    agent_id = params.get("agent_id")
    top_k = params.get("top_k", 5)

    mgr = MemoryManager(ctx.db)
    results = await mgr.search_memory(query, agent_id=agent_id, top_k=top_k)
    return {"results": results, "count": len(results)}


@register_method("memory.list")
async def handle_memory_list(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.memory import MemoryManager
    limit = params.get("limit", 50)
    agent_id = params.get("agent_id")
    mgr = MemoryManager(ctx.db)
    memories = await mgr.list_memories(limit=limit, agent_id=agent_id)
    count = await mgr.get_memory_count(agent_id=agent_id)
    return {"memories": memories, "total": count}


@register_method("memory.store")
async def handle_memory_store(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.memory import MemoryManager
    content = params.get("content", "")
    if not content:
        return {"error": "content is required"}
    mgr = MemoryManager(ctx.db)
    mem = await mgr.store_memory(
        content=content,
        session_id=params.get("session_id", "manual"),
        agent_id=params.get("agent_id", "default"),
        source="manual",
    )
    return {"ok": True, "memory": mem}


@register_method("memory.clear")
async def handle_memory_clear(params: dict, client, ctx: MethodContext) -> dict:
    from gateway.memory import MemoryManager
    agent_id = params.get("agent_id")
    mgr = MemoryManager(ctx.db)
    count = await mgr.clear_memories(agent_id=agent_id)
    return {"ok": True, "cleared": count}



# ── Tasks / Scheduler (Phase 8) ──────────────────────────────────────────

@register_method("tasks.list")
async def handle_tasks_list(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    tasks = await ctx.scheduler.list_tasks()
    return {"tasks": tasks, "count": len(tasks)}


@register_method("tasks.get")
async def handle_tasks_get(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    task_id = params.get("id", "")
    if not task_id:
        return {"error": "id is required"}
    task = await ctx.scheduler.get_task(task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    return task


@register_method("tasks.create")
async def handle_tasks_create(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    try:
        task = await ctx.scheduler.create_task(params)
        from datetime import datetime as dt, timezone as tz
        ctx.activity_log.append({
            "type": "task.create",
            "detail": f"Task created: {task['id']} ({task.get('name', '')})",
            "timestamp": dt.now(tz.utc).isoformat(),
        })
        return {"ok": True, "task": task}
    except ValueError as e:
        return {"error": str(e)}


@register_method("tasks.update")
async def handle_tasks_update(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    task_id = params.get("id", "")
    if not task_id:
        return {"error": "id is required"}
    task = await ctx.scheduler.update_task(task_id, params)
    if not task:
        return {"error": f"Task not found or no fields to update: {task_id}"}
    return {"ok": True, "task": task}


@register_method("tasks.delete")
async def handle_tasks_delete(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    task_id = params.get("id", "")
    if not task_id:
        return {"error": "id is required"}
    deleted = await ctx.scheduler.delete_task(task_id)
    if not deleted:
        return {"error": f"Task not found: {task_id}"}
    return {"ok": True, "deleted": task_id}


@register_method("tasks.pause")
async def handle_tasks_pause(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    task_id = params.get("id", "")
    if not task_id:
        return {"error": "id is required"}
    ok = await ctx.scheduler.pause_task(task_id)
    return {"ok": ok}


@register_method("tasks.resume")
async def handle_tasks_resume(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    task_id = params.get("id", "")
    if not task_id:
        return {"error": "id is required"}
    ok = await ctx.scheduler.resume_task(task_id)
    return {"ok": ok}


@register_method("tasks.run_now")
async def handle_tasks_run_now(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    task_id = params.get("id", "")
    if not task_id:
        return {"error": "id is required"}
    ok = await ctx.scheduler.run_now(task_id)
    return {"ok": ok}


@register_method("tasks.history")
async def handle_tasks_history(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.scheduler:
        return {"error": "Scheduler not available"}
    task_id = params.get("id", "")
    if not task_id:
        return {"error": "id is required"}
    limit = params.get("limit", 20)
    history = await ctx.scheduler.get_history(task_id, limit=limit)
    return {"history": history, "count": len(history)}


# ── Notifications (Phase 8) ──────────────────────────────────────────────

@register_method("notifications.list")
async def handle_notifications_list(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.notification_mgr:
        return {"error": "Notifications not available"}
    limit = params.get("limit", 50)
    unread_only = params.get("unread_only", False)
    notifs = await ctx.notification_mgr.list_notifications(limit=limit, unread_only=unread_only)
    unread_count = await ctx.notification_mgr.get_unread_count()
    return {"notifications": notifs, "unread_count": unread_count}


@register_method("notifications.mark_read")
async def handle_notifications_mark_read(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.notification_mgr:
        return {"error": "Notifications not available"}
    notif_id = params.get("id", "")
    if notif_id:
        ok = await ctx.notification_mgr.mark_read(notif_id)
        return {"ok": ok}
    else:
        count = await ctx.notification_mgr.mark_all_read()
        return {"ok": True, "marked": count}


@register_method("notifications.clear")
async def handle_notifications_clear(params: dict, client, ctx: MethodContext) -> dict:
    if not ctx.notification_mgr:
        return {"error": "Notifications not available"}
    count = await ctx.notification_mgr.clear_notifications()
    return {"ok": True, "cleared": count}



# ── Workspace Explorer ────────────────────────────────────────────────────

@register_method("workspace.files")
async def handle_workspace_files(params: dict, client, ctx: MethodContext) -> dict:
    """Browse files in the workspace directory."""
    import os
    base = "/app/workspace"
    rel_path = params.get("path", ".")
    full_path = os.path.normpath(os.path.join(base, rel_path))

    if not full_path.startswith(base):
        return {"error": "Path must be within workspace"}

    if not os.path.exists(full_path):
        return {"error": f"Path not found: {rel_path}", "items": [], "current_path": rel_path}

    if os.path.isfile(full_path):
        try:
            content = open(full_path, "r", errors="replace").read(50000)
            stat = os.stat(full_path)
            return {
                "type": "file",
                "path": rel_path,
                "name": os.path.basename(full_path),
                "content": content,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        except Exception as e:
            return {"error": f"Cannot read file: {e}"}

    items = []
    try:
        for entry in sorted(os.scandir(full_path), key=lambda e: (not e.is_dir(), e.name.lower())):
            stat = entry.stat(follow_symlinks=False)
            items.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size if entry.is_file() else 0,
                "modified": stat.st_mtime,
                "path": os.path.relpath(entry.path, base),
            })
    except PermissionError:
        return {"error": "Permission denied", "items": [], "current_path": rel_path}

    return {"type": "directory", "items": items, "current_path": rel_path}


@register_method("workspace.processes")
async def handle_workspace_processes(params: dict, client, ctx: MethodContext) -> dict:
    """Get status of all managed background processes."""
    import re as _re
    from gateway.tools.process_manager import _processes, _output_buffers
    processes = []
    for pid, info in _processes.items():
        # Try to detect port from command or output
        port = None
        # Check command for common port patterns
        cmd = info["command"]
        port_match = _re.search(r'(?:--port|--bind|:)[\s=]*(\d{4,5})', cmd)
        if port_match:
            port = int(port_match.group(1))
        # Also scan output buffer for "running on" patterns
        if not port:
            for line in _output_buffers.get(pid, [])[-20:]:
                m = _re.search(r'(?:port|listening|running on|http://[\w.]*:)[\s:]*(\d{4,5})', line, _re.IGNORECASE)
                if m:
                    port = int(m.group(1))
                    break

        proc_data = {
            "pid": pid,
            "name": info["name"],
            "command": info["command"],
            "cwd": info["cwd"],
            "status": info["status"],
            "started_at": info["started_at"],
            "stopped_at": info.get("stopped_at"),
            "exit_code": info.get("exit_code"),
            "output_lines": len(_output_buffers.get(pid, [])),
            "port": port,
        }
        processes.append(proc_data)
    return {"processes": processes, "count": len(processes)}


@register_method("workspace.process_output")
async def handle_workspace_process_output(params: dict, client, ctx: MethodContext) -> dict:
    """Get output from a managed process."""
    from gateway.tools.process_manager import _processes, _output_buffers
    pid = params.get("pid", "")
    tail = min(params.get("tail", 50), 200)
    if not pid:
        return {"error": "pid is required"}
    info = _processes.get(pid)
    if not info:
        return {"error": f"Process {pid} not found"}
    buf = _output_buffers.get(pid, [])
    return {
        "pid": pid,
        "name": info["name"],
        "status": info["status"],
        "lines": buf[-tail:],
    }


@register_method("workspace.tools")
async def handle_workspace_tools(params: dict, client, ctx: MethodContext) -> dict:
    """List custom tools created by the developer agent."""
    tools = await ctx.db.custom_tools.find({}, {"_id": 0}).to_list(100)
    return {"tools": tools, "count": len(tools)}


@register_method("workspace.tool_delete")
async def handle_workspace_tool_delete(params: dict, client, ctx: MethodContext) -> dict:
    """Delete a custom tool."""
    name = params.get("name", "").strip()
    if not name:
        return {"error": "name is required"}

    from gateway.tools import get_tool as _get_tool, _tools
    existing = _get_tool(name)
    if not existing:
        return {"error": f"Tool '{name}' not found"}
    if not getattr(existing, "__custom__", False):
        return {"error": f"Cannot delete built-in tool '{name}'"}

    _tools.pop(name, None)
    await ctx.db.custom_tools.delete_one({"name": name})

    import os
    from pathlib import Path
    file_path = Path("/app/workspace/custom_tools") / f"{name}.py"
    if file_path.exists():
        file_path.unlink()

    return {"ok": True, "deleted": name}


@register_method("workspace.start_process")
async def handle_workspace_start_process(params: dict, client, ctx: MethodContext) -> dict:
    """Start a new managed background process from the workspace explorer UI."""
    from gateway.tools.process_manager import StartProcessTool
    command = params.get("command", "").strip()
    name = params.get("name", "").strip()
    cwd = params.get("working_directory", ".").strip()

    if not command:
        return {"error": "command is required"}
    if not name:
        return {"error": "name is required"}

    tool = StartProcessTool()
    result = await tool.execute({"command": command, "name": name, "working_directory": cwd})
    return {"ok": "Error" not in result, "message": result}


@register_method("workspace.projects")
async def handle_workspace_projects(params: dict, client, ctx: MethodContext) -> dict:
    """List all projects in the workspace with their live status."""
    import os
    import re as _re
    from gateway.tools.process_manager import _processes, _output_buffers

    base = "/app/workspace/projects"
    if not os.path.isdir(base):
        return {"projects": []}

    projects = []
    for entry in sorted(os.scandir(base), key=lambda e: e.name.lower()):
        if not entry.is_dir():
            continue

        name = entry.name
        full = entry.path
        files = set(os.listdir(full))

        # Detect project type
        project_type = None
        entry_point = None
        if "package.json" in files:
            project_type = "node"
            for c in ["index.js", "server.js", "app.js", "main.js"]:
                if c in files:
                    entry_point = c
                    break
        else:
            for c in ["app.py", "main.py", "server.py", "run.py"]:
                if c in files:
                    entry_point = c
                    project_type = "python"
                    break
            if not project_type:
                py = [f for f in files if f.endswith(".py")]
                if py:
                    project_type = "python"
                    entry_point = py[0]

        has_deps = "requirements.txt" in files or "package.json" in files
        has_venv = "venv" in files and os.path.isdir(os.path.join(full, "venv"))

        # Cross-reference with running processes
        running_proc = None
        port = None
        for pid, info in _processes.items():
            proj_cwd = info.get("cwd", "")
            if (proj_cwd == f"projects/{name}" or proj_cwd.endswith(f"/{name}")) and info["status"] == "running":
                running_proc = {"pid": pid, "name": info["name"], "started_at": info["started_at"]}
                # Detect port
                cmd = info["command"]
                pm = _re.search(r'(?:--port|--bind|:)[\s=]*(\d{4,5})', cmd)
                if pm:
                    port = int(pm.group(1))
                if not port:
                    for line in _output_buffers.get(pid, [])[-20:]:
                        m = _re.search(r'(?:port|listening|running on|http://[\w.]*:)[\s:]*(\d{4,5})', line, _re.IGNORECASE)
                        if m:
                            port = int(m.group(1))
                            break
                # Also check PORT= in command
                if not port:
                    pm2 = _re.search(r'PORT=(\d{4,5})', cmd)
                    if pm2:
                        port = int(pm2.group(1))
                break

        # Last modified
        stat = entry.stat()
        last_modified = stat.st_mtime
        # Check most recent file modification in project
        try:
            for f in os.scandir(full):
                if f.is_file():
                    fm = f.stat().st_mtime
                    if fm > last_modified:
                        last_modified = fm
        except Exception:
            pass

        file_count = sum(1 for f in files if not f.startswith(".") and f != "__pycache__" and f != "venv" and f != "node_modules")

        projects.append({
            "name": name,
            "path": f"projects/{name}",
            "project_type": project_type,
            "entry_point": entry_point,
            "has_deps": has_deps,
            "has_venv": has_venv,
            "status": "running" if running_proc else "stopped",
            "process": running_proc,
            "port": port,
            "last_modified": last_modified,
            "file_count": file_count,
        })

    return {"projects": projects, "count": len(projects)}


@register_method("workspace.detect_project")
async def handle_workspace_detect_project(params: dict, client, ctx: MethodContext) -> dict:
    """Detect project type, entry point, and whether venv/deps are needed."""
    import os
    base = "/app/workspace"
    rel_path = params.get("path", ".").strip()
    full_path = os.path.normpath(os.path.join(base, rel_path))

    if not full_path.startswith(base):
        return {"error": "Path must be within workspace"}
    if not os.path.isdir(full_path):
        return {"error": f"Not a directory: {rel_path}"}

    files = set(os.listdir(full_path))
    project_type = None
    entry_point = None
    has_requirements = False
    has_venv = False
    has_node_modules = False
    suggested_command = None
    suggested_name = os.path.basename(full_path) or "project"

    # Python detection
    py_entries = ["app.py", "main.py", "server.py", "run.py", "manage.py"]
    for candidate in py_entries:
        if candidate in files:
            entry_point = candidate
            project_type = "python"
            break
    if not entry_point:
        # Check for any .py file
        py_files = [f for f in files if f.endswith(".py")]
        if py_files:
            project_type = "python"
            entry_point = py_files[0]

    has_requirements = "requirements.txt" in files
    has_venv = "venv" in files and os.path.isdir(os.path.join(full_path, "venv"))

    # Node detection (takes priority if package.json exists)
    if "package.json" in files:
        project_type = "node"
        has_node_modules = "node_modules" in files and os.path.isdir(os.path.join(full_path, "node_modules"))
        for candidate in ["index.js", "server.js", "app.js", "main.js"]:
            if candidate in files:
                entry_point = candidate
                break

    # Build suggested command
    if project_type == "python":
        parts = []
        if has_requirements and not has_venv:
            parts.append("python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt &&")
        elif has_venv:
            parts.append(". venv/bin/activate &&")
        elif has_requirements:
            parts.append("python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt &&")
        if entry_point:
            if has_venv or has_requirements:
                parts.append(f"python3 {entry_point}")
            else:
                parts.append(f"python3 {entry_point}")
        suggested_command = " ".join(parts) if parts else None
    elif project_type == "node":
        parts = []
        if not has_node_modules:
            parts.append("npm install &&")
        if entry_point:
            parts.append(f"node {entry_point}")
        else:
            parts.append("npm start")
        suggested_command = " ".join(parts)

    # Try to detect port from entry point source code
    suggested_port = None
    if entry_point:
        try:
            import re
            src = open(os.path.join(full_path, entry_point), "r", errors="replace").read(10000)
            # Match: port=5000, PORT = 3000, .listen(8080), --port 5000, get('PORT', 5000)
            m = re.search(r"(?:port\s*[=:]\s*|\.listen\s*\(\s*|['\"]PORT['\"],\s*)(\d{4,5})", src, re.IGNORECASE)
            if m:
                suggested_port = int(m.group(1))
        except Exception:
            pass

    return {
        "project_type": project_type,
        "entry_point": entry_point,
        "has_requirements": has_requirements,
        "has_venv": has_venv,
        "has_node_modules": has_node_modules,
        "suggested_command": suggested_command,
        "suggested_name": suggested_name,
        "suggested_port": suggested_port,
        "path": rel_path,
    }


@register_method("workspace.install_deps")
async def handle_workspace_install_deps(params: dict, client, ctx: MethodContext) -> dict:
    """Install project dependencies (venv + pip install for Python, npm install for Node)."""
    from gateway.tools.process_manager import StartProcessTool
    import os

    rel_path = params.get("path", "").strip()
    if not rel_path:
        return {"error": "path is required"}

    base = "/app/workspace"
    full_path = os.path.normpath(os.path.join(base, rel_path))
    if not full_path.startswith(base) or not os.path.isdir(full_path):
        return {"error": f"Invalid project path: {rel_path}"}

    files = set(os.listdir(full_path))
    project_name = os.path.basename(full_path) or "project"

    if "requirements.txt" in files:
        has_venv = "venv" in files and os.path.isdir(os.path.join(full_path, "venv"))
        if has_venv:
            command = "bash -c '. venv/bin/activate && pip install -r requirements.txt'"
        else:
            command = "bash -c 'python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt'"
        dep_type = "python"
    elif "package.json" in files:
        command = "npm install"
        dep_type = "node"
    else:
        return {"error": "No requirements.txt or package.json found in this directory"}

    tool = StartProcessTool()
    proc_name = f"install-{project_name}"
    result = await tool.execute({
        "command": command,
        "name": proc_name,
        "working_directory": rel_path,
    })

    from datetime import datetime as dt, timezone as tz
    ctx.activity_log.append({
        "type": "workspace.install_deps",
        "detail": f"Installing {dep_type} deps for '{project_name}' at {rel_path}",
        "timestamp": dt.now(tz.utc).isoformat(),
    })

    return {"ok": "Error" not in result, "message": result, "dep_type": dep_type, "process_name": proc_name}


@register_method("workspace.run_project")
async def handle_workspace_run_project(params: dict, client, ctx: MethodContext) -> dict:
    """Run a project with automatic venv creation and dependency installation."""
    from gateway.tools.process_manager import StartProcessTool
    import os

    rel_path = params.get("path", "").strip()
    command = params.get("command", "").strip()
    name = params.get("name", "").strip()
    port = params.get("port")  # Optional port override

    if not rel_path:
        return {"error": "path is required"}
    if not command:
        return {"error": "command is required"}
    if not name:
        return {"error": "name is required"}

    base = "/app/workspace"
    full_path = os.path.normpath(os.path.join(base, rel_path))
    if not full_path.startswith(base) or not os.path.isdir(full_path):
        return {"error": f"Invalid project path: {rel_path}"}

    # Inject PORT env var if user specified a port
    if port:
        command = f"PORT={port} {command}"

    # Use bash -c to handle chained commands (venv creation, pip install, etc.)
    shell_command = f"bash -c '{command}'"

    tool = StartProcessTool()
    result = await tool.execute({
        "command": shell_command,
        "name": name,
        "working_directory": rel_path,
    })

    from datetime import datetime as dt, timezone as tz
    ctx.activity_log.append({
        "type": "workspace.run_project",
        "detail": f"Project '{name}' started at {rel_path}",
        "timestamp": dt.now(tz.utc).isoformat(),
    })

    return {"ok": "Error" not in result, "message": result}


@register_method("workspace.stop_process")
async def handle_workspace_stop_process(params: dict, client, ctx: MethodContext) -> dict:
    """Stop a managed background process."""
    from gateway.tools.process_manager import StopProcessTool
    pid = params.get("pid", "").strip()
    name = params.get("name", "").strip()

    tool = StopProcessTool()
    result = await tool.execute({"pid": pid, "name": name})
    return {"ok": "Error" not in result, "message": result}



# ── Process streaming subscriptions (keyed by client_id) ──────────────────
_stream_tasks: dict[str, asyncio.Task] = {}


@register_method("workspace.process_subscribe")
async def handle_process_subscribe(params: dict, client, ctx: MethodContext) -> dict:
    """Subscribe to real-time output streaming from a process."""
    import asyncio
    from gateway.tools.process_manager import (
        _processes, _output_buffers, subscribe_to_process, unsubscribe_from_process,
    )
    from gateway.protocol import event_message

    pid = params.get("pid", "")
    if not pid:
        return {"error": "pid is required"}
    if pid not in _processes:
        return {"error": f"Process {pid} not found"}

    # Cancel existing subscription for this client
    sub_key = f"{client.client_id}:{pid}"
    old_task = _stream_tasks.pop(sub_key, None)
    if old_task:
        old_task.cancel()

    q = subscribe_to_process(pid)

    # Send existing buffer as initial payload
    buf = _output_buffers.get(pid, [])
    initial_lines = buf[-100:]  # last 100 lines

    async def stream_loop():
        try:
            while True:
                line = await q.get()
                try:
                    await client.ws.send_json(event_message("workspace.stream", {
                        "pid": pid,
                        "line": line,
                    }))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe_from_process(pid, q)

    task = asyncio.create_task(stream_loop())
    _stream_tasks[sub_key] = task

    return {
        "ok": True,
        "pid": pid,
        "name": _processes[pid]["name"],
        "status": _processes[pid]["status"],
        "initial_lines": initial_lines,
    }


@register_method("workspace.process_unsubscribe")
async def handle_process_unsubscribe(params: dict, client, ctx: MethodContext) -> dict:
    """Unsubscribe from process output streaming."""
    pid = params.get("pid", "")
    if not pid:
        return {"error": "pid is required"}

    sub_key = f"{client.client_id}:{pid}"
    task = _stream_tasks.pop(sub_key, None)
    if task:
        task.cancel()
        return {"ok": True, "unsubscribed": pid}
    return {"ok": True, "message": "No active subscription"}


@register_method("profile.get")
async def handle_profile_get(params: dict, client, ctx: MethodContext) -> dict:
    """Get the accumulated user profile."""
    from gateway.user_profile import get_profile
    return await get_profile(ctx.db)



@register_method("relationships.list")
async def handle_relationships_list(params: dict, client, ctx: MethodContext) -> dict:
    """Get all discovered relationships."""
    from gateway.relationship_memory import get_relationships
    people = await get_relationships(ctx.db)
    return {"people": people}




def cleanup_client_streams(client_id: str):
    """Cancel all stream subscriptions for a disconnected client."""
    to_remove = [k for k in _stream_tasks if k.startswith(f"{client_id}:")]
    for k in to_remove:
        task = _stream_tasks.pop(k, None)
        if task:
            task.cancel()
