"""
OverClaw Gateway — Main Application
FastAPI + WebSocket control plane with JSON-RPC protocol.
"""
import json
import asyncio
import logging
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import httpx

from gateway.protocol import (
    success_response, error_response, event_message,
    AUTH_REQUIRED, AUTH_FAILED, METHOD_NOT_FOUND, INTERNAL_ERROR, PARSE_ERROR,
)
from gateway.auth import verify_token, get_gateway_token
from gateway.health import get_health_snapshot, get_gateway_info
from gateway.config_schema import AssistantConfig, validate_config, config_to_display
from gateway.ws_manager import WsManager
from gateway.methods import get_method, list_methods, MethodContext
from gateway.tools import init_tools
from gateway.channels import start_channels, stop_channels, get_channel
from gateway.agents_config import (
    ORCHESTRATOR_PROMPT, SPECIALIST_AGENTS,
    seed_specialist_agents, tool_preview,
)

# ── Setup ────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gateway")

# MongoDB
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

# Gateway state
ws_manager = WsManager()
gateway_config: AssistantConfig = AssistantConfig()
activity_log: list[dict] = []
task_scheduler = None
notification_mgr = None


def add_activity(event_type: str, detail: str):
    entry = {
        "type": event_type,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    activity_log.append(entry)
    if len(activity_log) > 200:
        activity_log.pop(0)


# ── App ──────────────────────────────────────────────────────────────────
app = FastAPI(title="OverClaw Gateway", version="0.1.0")
api_router = APIRouter(prefix="/api")


# ── Startup / Shutdown ───────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    global gateway_config
    logger.info("Gateway starting...")

    # Load any DB-stored secrets into environment (from previous wizard setup)
    from gateway.setup import load_secrets_to_env
    await load_secrets_to_env(db)

    # Load config from MongoDB (or create default)
    stored = await db.gateway_config.find_one({"_id": "main"}, {"_id": 0})
    if stored:
        try:
            gateway_config = validate_config(stored)
            logger.info("Config loaded from database")
        except Exception as e:
            logger.warning(f"Stored config invalid, using defaults: {e}")
            gateway_config = AssistantConfig()
    else:
        gateway_config = AssistantConfig()
        await db.gateway_config.replace_one(
            {"_id": "main"},
            {"_id": "main", **gateway_config.model_dump()},
            upsert=True,
        )
        logger.info("Default config saved to database")

    # Seed placeholder sessions
    count = await db.sessions.count_documents({})
    if count == 0:
        await db.sessions.insert_many([{
            "session_id": "main",
            "channel": "webchat",
            "agent_id": "default",
            "status": "idle",
            "messages": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_active": datetime.now(timezone.utc).isoformat(),
        }])

    add_activity("gateway.start", "Gateway started successfully")
    init_tools()

    # Initialize debug logger (captures WARNING+ to MongoDB)
    from gateway.debug_log import init_debug_logger
    init_debug_logger(db)

    # Recover processes from previous session
    from gateway.tools.process_manager import recover_processes
    recover_processes()

    # Wire tools to DB
    from gateway.tools.memory_search import set_memory_db
    from gateway.tools.monitor import set_monitor_db
    from gateway.tools.gmail import set_gmail_db
    from gateway.gmail import set_gmail_db_ref
    from gateway.tools.outlook import set_outlook_db
    from gateway.outlook import set_outlook_db_ref
    from gateway.tools.create_tool import set_create_tool_db, load_persisted_tools

    set_memory_db(db)
    set_monitor_db(db)
    set_gmail_db(db)
    set_gmail_db_ref(db)
    set_outlook_db(db)
    set_outlook_db_ref(db)
    set_create_tool_db(db)
    await load_persisted_tools()

    # Wire triage feedback to DB
    from gateway.triage_feedback import set_feedback_db
    set_feedback_db(db)

    # Seed specialist agents
    await seed_specialist_agents(db)

    # Migrate legacy model names in agents collection
    from gateway.agent import _MODEL_ALIASES
    async for agent_doc in db.agents.find({"model": {"$in": list(_MODEL_ALIASES.keys())}}):
        new_model = _MODEL_ALIASES[agent_doc["model"]]
        await db.agents.update_one({"_id": agent_doc["_id"]}, {"$set": {"model": new_model}})
        logger.info(f"Migrated agent '{agent_doc.get('id')}' model: {agent_doc['model']} -> {new_model}")

    # ── Enforce orchestrator tools and prompt (versioned) ────────────────
    # The orchestrator should NOT have web_search or browser_use:
    # - web_search: delegates to research specialist
    # - browser_use: broken (missing uvx) and should go through browser specialist
    # This list is DECLARATIVE: stored config is set to exactly this list.
    ORCHESTRATOR_TOOLS = [
        "memory_search", "system_info",
        "analyze_image", "transcribe_audio", "parse_document", "monitor_url",
        "gmail", "outlook", "delegate", "list_agents", "slack_notify",
        "create_directory", "patch_file", "search_in_files",
        "create_tool", "list_custom_tools", "delete_custom_tool",
        "start_process", "stop_process", "list_processes", "get_process_output",
        "read_file", "write_file", "list_files", "execute_command",
    ]
    ORCHESTRATOR_PROMPT_VERSION = 4  # Bump when prompt changes

    specialist_ids = [a["id"] for a in SPECIALIST_AGENTS]

    # Patch specialist agents to include new tools where appropriate
    non_delegate = [t for t in ORCHESTRATOR_TOOLS if t not in ("delegate", "list_agents")]
    for tool_name in non_delegate:
        await db.agents.update_many(
            {"tools_allowed": {"$exists": True, "$nin": [tool_name]}, "id": {"$nin": specialist_ids}},
            {"$addToSet": {"tools_allowed": tool_name}},
        )

    # Patch stored gateway config — DECLARATIVE tools + versioned prompt
    stored_cfg = await db.gateway_config.find_one({"_id": "main"})
    if stored_cfg:
        # Set tools to exact list (removes stale entries like web_search)
        stored_tools = stored_cfg.get("agent", {}).get("tools_allowed", [])
        if set(stored_tools) != set(ORCHESTRATOR_TOOLS):
            await db.gateway_config.update_one(
                {"_id": "main"}, {"$set": {"agent.tools_allowed": ORCHESTRATOR_TOOLS}}
            )
            gateway_config.agent.tools_allowed = ORCHESTRATOR_TOOLS
            removed = set(stored_tools) - set(ORCHESTRATOR_TOOLS)
            added = set(ORCHESTRATOR_TOOLS) - set(stored_tools)
            if removed:
                logger.info(f"Removed from orchestrator tools: {removed}")
            if added:
                logger.info(f"Added to orchestrator tools: {added}")

        # Migrate legacy model names to new naming scheme
        from gateway.agent import _MODEL_ALIASES
        stored_model = stored_cfg.get("agent", {}).get("model", "")
        if stored_model in _MODEL_ALIASES:
            new_model = _MODEL_ALIASES[stored_model]
            await db.gateway_config.update_one(
                {"_id": "main"}, {"$set": {"agent.model": new_model}}
            )
            gateway_config.agent.model = new_model
            logger.info(f"Migrated default agent model: {stored_model} -> {new_model}")

        # Versioned prompt update — always applies when version changes
        stored_version = stored_cfg.get("agent", {}).get("prompt_version", 1)
        if stored_version < ORCHESTRATOR_PROMPT_VERSION:
            await db.gateway_config.update_one(
                {"_id": "main"}, {"$set": {
                    "agent.system_prompt": ORCHESTRATOR_PROMPT,
                    "agent.prompt_version": ORCHESTRATOR_PROMPT_VERSION,
                }}
            )
            gateway_config.agent.system_prompt = ORCHESTRATOR_PROMPT
            logger.info(f"Orchestrator prompt updated to version {ORCHESTRATOR_PROMPT_VERSION}")

    # Seed default skills
    from gateway.skills import seed_default_skills
    await seed_default_skills(db)

    # Setup Slack channel + agent runner
    from gateway.channels.slack_channel import SlackChannel  # noqa: F401
    from gateway.agent import AgentRunner

    slack = get_channel("slack")
    if slack:
        agent_runner = AgentRunner(db, gateway_config)

        from gateway.tools.delegate import set_delegate_context
        set_delegate_context(db, agent_runner)

        async def handle_slack_message(channel, user, text, thread_ts):
            session_id = f"slack:{channel}:{user}"

            cmd = text.strip().lower()
            if cmd in ("reset", "clear", "clear history", "new chat", "start over"):
                await db.chat_messages.delete_many({"session_id": session_id})
                await db.sessions.update_one(
                    {"session_id": session_id},
                    {"$set": {"messages": 0, "status": "idle"}},
                )
                return "Chat history cleared. Starting fresh!"

            # Broadcast to webchat: user message arrived from Slack
            await ws_manager.broadcast(event_message("chat.event", {
                "session_id": session_id,
                "type": "slack.message",
                "role": "user",
                "text": text[:200],
                "channel": channel,
                "user": user,
            }))

            async def on_tool_call(tool_name, tool_args, status):
                if status == "executing":
                    preview = tool_preview(tool_name, tool_args)
                    label = f":gear: `{tool_name}`"
                    if preview:
                        label += f"  {preview}"
                    try:
                        await slack._app.client.chat_postMessage(channel=channel, text=label)
                    except Exception:
                        pass

            response, tool_calls = await agent_runner.run_turn(
                session_id, text, on_tool_call=on_tool_call
            )
            add_activity("slack.message", f"Slack [{user[:8]}]: {text[:40]}... -> {len(tool_calls)} tools")

            # Broadcast to webchat: agent response for Slack session
            await ws_manager.broadcast(event_message("chat.event", {
                "session_id": session_id,
                "type": "slack.response",
                "role": "assistant",
                "text": response[:500],
                "tool_calls_count": len(tool_calls),
            }))

            return response

        slack.set_message_handler(handle_slack_message)

    await start_channels(gateway_config)

    # Seed email triage task with improved prompt
    from gateway.email_triage import seed_email_triage_task
    await seed_email_triage_task(db)

    # Init scheduler + notifications
    from gateway.notifications import NotificationManager
    from gateway.scheduler import TaskScheduler

    global notification_mgr, task_scheduler
    notification_mgr = NotificationManager(db, ws_manager)
    scheduler_runner = AgentRunner(db, gateway_config)
    task_scheduler = TaskScheduler(db, scheduler_runner, notification_mgr, ws_manager)
    await task_scheduler.start()
    logger.info("Task scheduler started")

    token = get_gateway_token()
    if token:
        logger.info(f"Auth: token required (****{token[-4:]})")
    else:
        logger.warning("Auth: NO TOKEN SET — gateway is open")
    logger.info(f"Gateway v{get_gateway_info()['version']} ready")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Gateway shutting down...")
    if task_scheduler:
        await task_scheduler.stop()
    await stop_channels()
    mongo_client.close()



# ── HTTP Endpoints ───────────────────────────────────────────────────────
@api_router.get("/setup/status")
async def setup_status():
    from gateway.setup import get_setup_status
    return await get_setup_status(db)


@api_router.post("/setup/save")
async def setup_save(request: Request):
    from gateway.setup import save_setup
    data = await request.json()
    return await save_setup(db, data)


@api_router.get("/health")
async def http_health():
    snapshot = get_health_snapshot()
    snapshot["connected_clients"] = ws_manager.client_count
    return snapshot


@api_router.get("/")
async def root():
    return {
        "gateway": get_gateway_info()["name"],
        "version": get_gateway_info()["version"],
        "status": "running",
        "methods": list_methods(),
    }


@api_router.get("/config")
async def http_config_get():
    return config_to_display(gateway_config)


@api_router.get("/analysis", response_class=HTMLResponse)
async def get_analysis():
    html_path = Path(__file__).parent.parent / "memory" / "openclaw-analysis.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(), status_code=200)
    return HTMLResponse(content="<h1>Analysis not found</h1>", status_code=404)


# ── File Upload ──────────────────────────────────────────────────────────
UPLOAD_DIR = Path("/tmp/gateway_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg",
    ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".webm", ".mpga", ".mpeg",
    ".pdf", ".docx", ".doc", ".txt", ".csv", ".json", ".xml", ".md",
    ".yaml", ".yml", ".log", ".py", ".js", ".ts", ".html", ".css",
    ".zip",
}


@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse(status_code=400, content={"error": "No filename provided"})

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(status_code=400, content={"error": f"Unsupported file type '{ext}'"})

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        return JSONResponse(status_code=400, content={"error": f"File too large ({len(contents) / 1e6:.1f} MB)"})

    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as f:
        f.write(contents)

    file_type = "unknown"
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}:
        file_type = "image"
    elif ext in {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".webm", ".mpga", ".mpeg"}:
        file_type = "audio"
    elif ext in {".pdf", ".docx", ".doc", ".txt", ".csv", ".json", ".xml", ".md", ".yaml", ".yml", ".log"}:
        file_type = "document"

    logger.info(f"File uploaded: {file.filename} -> {file_path} ({len(contents)} bytes)")
    return {"ok": True, "file_path": str(file_path), "original_name": file.filename, "size": len(contents), "type": file_type}


# ── Gmail OAuth ──────────────────────────────────────────────────────────
@api_router.get("/oauth/gmail/login")
async def gmail_oauth_login(user_id: str = "default"):
    try:
        from gateway.gmail import create_auth_url
        url = create_auth_url(user_id)
        from starlette.responses import RedirectResponse
        return RedirectResponse(url=url)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@api_router.get("/oauth/gmail/callback")
async def gmail_oauth_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return HTMLResponse(
            content=f"<html><body><h2>Gmail Authorization Failed</h2><p>{error}</p>"
                    f"<script>setTimeout(()=>window.close(),3000)</script></body></html>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(content="<html><body><h2>Missing authorization code</h2></body></html>", status_code=400)
    try:
        from gateway.gmail import handle_callback
        result = await handle_callback(code, state, db)
        email = result.get("email", "connected")
        return HTMLResponse(
            content=f"<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                    f"<h2>Gmail Connected!</h2><p>Connected: <b>{email}</b></p>"
                    f"<script>setTimeout(()=>window.close(),3000)</script></body></html>",
        )
    except Exception as e:
        logger.exception("Gmail OAuth callback failed")
        return HTMLResponse(content=f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>", status_code=500)


@api_router.get("/oauth/gmail/status")
async def gmail_status(user_id: str = "default"):
    from gateway.gmail import get_gmail_status
    return await get_gmail_status(db, user_id)


@api_router.post("/oauth/gmail/disconnect")
async def gmail_disconnect(user_id: str = "default"):
    result = await db.gmail_tokens.delete_one({"user_id": user_id})
    if result.deleted_count > 0:
        return {"ok": True, "message": "Gmail disconnected"}
    return {"ok": False, "message": "No Gmail connection found"}


# ── Outlook OAuth ─────────────────────────────────────────────────────────
@api_router.get("/oauth/outlook/login")
async def outlook_oauth_login(user_id: str = "default"):
    try:
        from gateway.outlook import create_auth_url
        url = create_auth_url(user_id)
        from starlette.responses import RedirectResponse
        return RedirectResponse(url=url)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@api_router.get("/oauth/outlook/callback")
async def outlook_oauth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error:
        return HTMLResponse(
            content=f"<html><body><h2>Outlook Authorization Failed</h2><p>{error}</p>"
                    f"<script>setTimeout(()=>window.close(),3000)</script></body></html>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(content="<html><body><h2>Missing authorization code</h2></body></html>", status_code=400)
    try:
        from gateway.outlook import handle_callback
        full_url = str(request.url)
        result = await handle_callback(code, state, full_url, db)
        email = result.get("email", "connected")
        return HTMLResponse(
            content=f"<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                    f"<h2>Outlook Connected!</h2><p>Connected: <b>{email}</b></p>"
                    f"<script>setTimeout(()=>window.close(),3000)</script></body></html>",
        )
    except Exception as e:
        logger.exception("Outlook OAuth callback failed")
        return HTMLResponse(content=f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>", status_code=500)


@api_router.get("/oauth/outlook/status")
async def outlook_status(user_id: str = "default"):
    from gateway.outlook import get_outlook_status
    return await get_outlook_status(db, user_id)


@api_router.post("/oauth/outlook/disconnect")
async def outlook_disconnect(user_id: str = "default"):
    result = await db.outlook_tokens.delete_one({"user_id": user_id})
    if result.deleted_count > 0:
        return {"ok": True, "message": "Outlook disconnected"}
    return {"ok": False, "message": "No Outlook connection found"}


# ── WebSocket Gateway ────────────────────────────────────────────────────
@api_router.websocket("/gateway")
async def websocket_gateway(ws: WebSocket):
    await ws.accept()
    client = ws_manager.add(ws)
    add_activity("client.connect", f"Client {client.client_id} connected")

    keepalive_active = True

    async def ws_keepalive():
        while keepalive_active:
            await asyncio.sleep(20)
            if keepalive_active:
                try:
                    await ws.send_text('{"jsonrpc":"2.0","method":"gateway.ping"}')
                except Exception:
                    break

    keepalive_task = asyncio.create_task(ws_keepalive())

    try:
        await ws.send_json(event_message("gateway.welcome", {
            "gateway": get_gateway_info(),
            "auth_required": bool(get_gateway_token()),
        }))

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json(error_response(None, PARSE_ERROR, "Invalid JSON"))
                continue

            request_id = msg.get("id")
            method = msg.get("method", "")
            params = msg.get("params", {})

            if method == "ping":
                await ws.send_json(event_message("pong", {}))
                continue

            if method == "connect":
                token = params.get("token", "")
                if verify_token(token):
                    client.authenticated = True
                    client.client_type = params.get("client_type", "dashboard")
                    add_activity("client.auth", f"Client {client.client_id} authenticated")
                    await ws.send_json(success_response(request_id, {
                        "ok": True, "client_id": client.client_id, "gateway": get_gateway_info(),
                    }))
                else:
                    await ws.send_json(error_response(request_id, AUTH_FAILED, "Invalid token"))
                continue

            if not client.authenticated and get_gateway_token():
                await ws.send_json(error_response(request_id, AUTH_REQUIRED, "Authentication required"))
                continue

            handler = get_method(method)
            if not handler:
                await ws.send_json(error_response(request_id, METHOD_NOT_FOUND, f"Unknown method: {method}"))
                continue

            try:
                ctx = MethodContext(db, ws_manager, gateway_config, activity_log, scheduler=task_scheduler, notification_mgr=notification_mgr)
                result = await handler(params, client, ctx)
                try:
                    await ws.send_json(success_response(request_id, result))
                except Exception:
                    logger.warning(f"Client {client.client_id} disconnected before response")
            except Exception as e:
                logger.exception(f"Error in method {method}")
                try:
                    await ws.send_json(error_response(request_id, INTERNAL_ERROR, str(e)))
                except Exception:
                    pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error for {client.client_id}: {e}")
    finally:
        keepalive_active = False
        keepalive_task.cancel()
        # Clean up any process stream subscriptions
        from gateway.methods import cleanup_client_streams
        cleanup_client_streams(client.client_id)
        add_activity("client.disconnect", f"Client {client.client_id} disconnected")
        ws_manager.remove(client.client_id)


# ── Workspace Preview Proxy ──────────────────────────────────────────────
# Reverse-proxies requests from /api/preview/{port}/... to localhost:{port}/...
# so workspace processes running HTTP servers are accessible externally.
PREVIEW_ALLOWED_PORTS = range(3001, 9999)
_preview_client = httpx.AsyncClient(timeout=30, follow_redirects=True)


@api_router.api_route("/preview/{port:int}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def preview_proxy(port: int, path: str, request: Request):
    if port not in PREVIEW_ALLOWED_PORTS:
        return JSONResponse(status_code=400, content={"error": f"Port {port} not allowed (range: 3001-9998)"})

    target = f"http://127.0.0.1:{port}/{path}"
    query = str(request.url.query)
    if query:
        target += f"?{query}"

    headers = dict(request.headers)
    # Remove hop-by-hop headers
    for h in ("host", "connection", "transfer-encoding"):
        headers.pop(h, None)

    body = await request.body()

    try:
        resp = await _preview_client.request(
            method=request.method,
            url=target,
            headers=headers,
            content=body if body else None,
        )
        # Stream response back
        resp_headers = dict(resp.headers)
        for h in ("transfer-encoding", "connection", "content-encoding"):
            resp_headers.pop(h, None)

        return StreamingResponse(
            content=iter([resp.content]),
            status_code=resp.status_code,
            headers=resp_headers,
        )
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"error": f"Cannot connect to port {port} — is the process running?"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Proxy error: {str(e)}"})


# Also serve the root path for a port (no trailing path)
@api_router.api_route("/preview/{port:int}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def preview_proxy_root(port: int, request: Request):
    # Redirect to trailing slash so relative URLs in proxied pages work correctly
    from starlette.responses import RedirectResponse
    if request.method == "GET" and not str(request.url).endswith("/"):
        return RedirectResponse(url=f"/api/preview/{port}/", status_code=307)
    return await preview_proxy(port, "", request)


# ── Mount ────────────────────────────────────────────────────────────────

# ── Static proposals ─────────────────────────────────────────────────────
from fastapi.responses import FileResponse

@api_router.get("/proposals/{filename}")
async def serve_proposal(filename: str):
    filepath = ROOT_DIR / "static" / filename
    if filepath.exists() and filepath.suffix in (".html", ".pdf"):
        media = "text/html" if filepath.suffix == ".html" else "application/pdf"
        return FileResponse(filepath, media_type=media)
    return JSONResponse({"error": "not found"}, status_code=404)


@api_router.get("/cast/receiver")
async def cast_receiver():
    """Google Cast custom receiver page."""
    filepath = ROOT_DIR / "static" / "cast_receiver.html"
    if filepath.exists():
        return FileResponse(filepath, media_type="text/html")
    return JSONResponse({"error": "not found"}, status_code=404)


# ── Brain Export/Import ──────────────────────────────────────────────────
@api_router.get("/brain/stats")
async def brain_stats():
    from gateway.brain import get_brain_stats
    stats = await get_brain_stats(db)
    return stats

@api_router.get("/brain/export")
async def brain_export():
    from gateway.brain import export_brain
    brain = await export_brain(db)
    return JSONResponse(
        content=brain,
        headers={"Content-Disposition": "attachment; filename=overclaw-brain.json"},
    )

@api_router.post("/brain/import")
async def brain_import(file: UploadFile = File(...)):
    import json as _json
    from gateway.brain import import_brain
    try:
        content = await file.read()
        brain_data = _json.loads(content)
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON file"}, status_code=400)
    result = await import_brain(db, brain_data)
    return result



# ── People Management ────────────────────────────────────────────────────
from pydantic import BaseModel
from typing import List

class MergePeopleRequest(BaseModel):
    keep_id: str
    merge_ids: List[str]

@api_router.post("/people/merge")
async def merge_people(req: MergePeopleRequest):
    """Merge multiple people entries into one. Combines mention counts and context."""
    from bson import ObjectId
    try:
        keep = await db.relationships.find_one({"_id": ObjectId(req.keep_id)})
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid keep_id"}, status_code=400)
    if not keep:
        return JSONResponse({"ok": False, "error": "Person not found"}, status_code=404)

    merged_count = 0
    for mid in req.merge_ids:
        if mid == req.keep_id:
            continue
        try:
            other = await db.relationships.find_one({"_id": ObjectId(mid)})
        except Exception:
            continue
        if not other:
            continue

        # Merge data into keep entry
        update = {}
        if not keep.get("email_address") and other.get("email_address"):
            update["email_address"] = other["email_address"]
        if not keep.get("role") and other.get("role"):
            update["role"] = other["role"]
        if not keep.get("team") and other.get("team"):
            update["team"] = other["team"]

        # Merge context histories
        other_ctx = other.get("context_history", [])
        if other_ctx:
            await db.relationships.update_one(
                {"_id": keep["_id"]},
                {"$push": {"context_history": {"$each": other_ctx, "$slice": -15}}}
            )

        # Add mention counts
        inc = other.get("mention_count", 0)
        update_ops = {"$inc": {"mention_count": inc}}
        if update:
            update_ops["$set"] = update
        await db.relationships.update_one({"_id": keep["_id"]}, update_ops)

        # Also add aliases for future matching
        other_name = other.get("name", "")
        if other_name:
            await db.relationships.update_one(
                {"_id": keep["_id"]},
                {"$addToSet": {"aliases": other_name}}
            )

        # Delete the merged entry
        await db.relationships.delete_one({"_id": other["_id"]})
        merged_count += 1

    return {"ok": True, "merged": merged_count}

@api_router.delete("/people/{person_id}")
async def delete_person(person_id: str):
    """Remove a person from the relationships collection."""
    from bson import ObjectId
    try:
        result = await db.relationships.delete_one({"_id": ObjectId(person_id)})
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid ID"}, status_code=400)
    return {"ok": True, "deleted": result.deleted_count}


@api_router.patch("/people/{person_id}")
async def update_person(person_id: str, request: Request):
    """Update a person's fields (e.g. email_address)."""
    from bson import ObjectId
    data = await request.json()
    allowed = {"email_address", "role", "team", "relationship"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return JSONResponse({"ok": False, "error": "No valid fields"}, status_code=400)
    try:
        result = await db.relationships.update_one({"_id": ObjectId(person_id)}, {"$set": update})
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid ID"}, status_code=400)
    return {"ok": True, "modified": result.modified_count}



app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
