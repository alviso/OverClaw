"""
Process Manager Tool — Start, monitor, and stop long-running background processes.
Used by the developer agent to run servers, scripts, and build processes.
"""
import asyncio
import json as _json
import logging
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.process_manager")

# Global process registry
_processes: dict[str, dict] = {}
_output_buffers: dict[str, list[str]] = {}
_MAX_BUFFER_LINES = 200

# Subscribers: proc_id -> set of asyncio.Queue (one per subscriber)
_subscribers: dict[str, set] = {}

# Persistence file for surviving restarts
_PERSIST_FILE = Path("/app/workspace/.processes.json")


def _is_pid_alive(pid: int) -> bool:
    """Check if a PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _save_process_state():
    """Persist process metadata so we can recover after restart."""
    data = {}
    for pid, info in _processes.items():
        data[pid] = {
            "pid": info["pid"],
            "name": info["name"],
            "command": info["command"],
            "cwd": info["cwd"],
            "status": info["status"],
            "started_at": info["started_at"],
            "stopped_at": info.get("stopped_at"),
            "exit_code": info.get("exit_code"),
        }
    try:
        _PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PERSIST_FILE.write_text(_json.dumps(data, indent=2))
    except Exception as e:
        logger.warning(f"Failed to persist process state: {e}")


def cleanup_dead_processes():
    """Remove dead/stale process entries from the registry.
    Called on startup and can be called anytime to prune the registry."""
    to_remove = []
    for pid_str, info in _processes.items():
        if info["status"] == "running" and not _is_pid_alive(info["pid"]):
            info["status"] = "exited"
            info["stopped_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"Cleaned up dead process: {info['name']} (pid={pid_str})")
        # Remove non-running entries older than this session (they clutter the list)
        if info["status"] in ("exited", "stopped"):
            to_remove.append(pid_str)

    for pid_str in to_remove:
        _processes.pop(pid_str, None)
        _output_buffers.pop(pid_str, None)

    if to_remove:
        _save_process_state()
        logger.info(f"Pruned {len(to_remove)} stale process entries from registry")


def recover_processes():
    """On startup, re-discover processes that are still alive from a previous run.
    Dead processes from previous runs are discarded (not loaded into registry)."""
    if not _PERSIST_FILE.exists():
        return
    try:
        data = _json.loads(_PERSIST_FILE.read_text())
    except Exception as e:
        logger.warning(f"Failed to read process state file: {e}")
        # Remove corrupt state file
        try:
            _PERSIST_FILE.unlink()
        except Exception:
            pass
        return

    recovered = 0
    for pid_str, info in data.items():
        pid_int = int(pid_str)

        if _is_pid_alive(pid_int):
            _processes[pid_str] = {
                "pid": pid_int,
                "name": info["name"],
                "command": info["command"],
                "cwd": info["cwd"],
                "status": "running",
                "started_at": info["started_at"],
                "_proc": None,
            }
            _output_buffers[pid_str] = [f"[sys] Process recovered after server restart (PID {pid_int})"]
            recovered += 1
        # Dead processes from previous runs are simply not loaded

    if recovered:
        logger.info(f"Recovered {recovered} running process(es) from previous session")
    else:
        logger.info("No surviving processes from previous session")

    # Write clean state (only truly alive processes)
    _save_process_state()


def subscribe_to_process(proc_id: str) -> asyncio.Queue:
    """Subscribe to real-time output from a process. Returns a Queue that receives new lines."""
    q = asyncio.Queue(maxsize=500)
    _subscribers.setdefault(proc_id, set()).add(q)
    return q


def unsubscribe_from_process(proc_id: str, q: asyncio.Queue):
    """Remove a subscriber queue."""
    subs = _subscribers.get(proc_id)
    if subs:
        subs.discard(q)
        if not subs:
            del _subscribers[proc_id]


async def _notify_subscribers(proc_id: str, line: str):
    """Push a new line to all subscribers of a process."""
    subs = _subscribers.get(proc_id)
    if not subs:
        return
    dead = []
    for q in subs:
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        subs.discard(q)


async def _read_stream(proc_id: str, stream, label: str):
    """Read from a process stream and buffer output."""
    buf = _output_buffers.setdefault(proc_id, [])
    try:
        async for line in stream:
            text = line.decode("utf-8", errors="replace").rstrip()
            formatted = f"[{label}] {text}"
            buf.append(formatted)
            if len(buf) > _MAX_BUFFER_LINES:
                buf.pop(0)
            await _notify_subscribers(proc_id, formatted)
    except Exception:
        pass


class StartProcessTool(Tool):
    name = "start_process"
    description = (
        "Start a long-running background process (e.g., a web server, build watcher, script).\n"
        "Returns a process ID that you can use to monitor or stop the process later.\n"
        "The process runs in the background and its output is buffered for later retrieval."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to run (e.g., 'python3 server.py', 'node app.js')",
            },
            "working_directory": {
                "type": "string",
                "description": "Working directory for the process (relative to /app/workspace)",
                "default": ".",
            },
            "name": {
                "type": "string",
                "description": "Human-readable name for this process (e.g., 'web-server', 'build-watcher')",
            },
        },
        "required": ["command", "name"],
    }

    async def execute(self, params: dict) -> str:
        command = params.get("command", "").strip()
        cwd = params.get("working_directory", ".").strip()
        name = params.get("name", "").strip()

        if not command:
            return "Error: 'command' is required"
        if not name:
            return "Error: 'name' is required"

        # Resolve working directory
        workspace = "/app/workspace"
        work_dir = os.path.normpath(os.path.join(workspace, cwd))
        if not work_dir.startswith(workspace):
            return "Error: working_directory must be within workspace"
        if not os.path.isdir(work_dir):
            return f"Error: directory not found: {cwd}"

        # Check for duplicate names
        for pid, info in _processes.items():
            if info["name"] == name and info["status"] == "running":
                return f"Error: process '{name}' is already running (pid={pid})"

        try:
            # Set PYTHONUNBUFFERED for Python processes so output appears immediately
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                preexec_fn=os.setsid,
                env=env,
            )

            proc_id = str(proc.pid)
            _processes[proc_id] = {
                "pid": proc.pid,
                "name": name,
                "command": command,
                "cwd": cwd,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "_proc": proc,
            }
            _output_buffers[proc_id] = []
            _save_process_state()

            # Start reading stdout/stderr in background
            asyncio.create_task(_read_stream(proc_id, proc.stdout, "out"))
            asyncio.create_task(_read_stream(proc_id, proc.stderr, "err"))

            # Monitor for exit
            async def _watch():
                await proc.wait()
                if proc_id in _processes:
                    _processes[proc_id]["status"] = "exited"
                    _processes[proc_id]["exit_code"] = proc.returncode
                    _processes[proc_id]["stopped_at"] = datetime.now(timezone.utc).isoformat()
                    _save_process_state()

            asyncio.create_task(_watch())

            logger.info(f"Process started: {name} (pid={proc.pid}) cmd='{command}'")
            return f"Process '{name}' started (pid={proc_id}). Use `list_processes` to check status or `get_process_output` to see logs."

        except Exception as e:
            logger.exception(f"Failed to start process: {command}")
            return f"Error starting process: {str(e)}"


class StopProcessTool(Tool):
    name = "stop_process"
    description = "Stop a running background process by its PID or name."
    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "string",
                "description": "Process ID (PID) to stop",
            },
            "name": {
                "type": "string",
                "description": "Process name to stop (alternative to PID)",
            },
        },
    }

    async def execute(self, params: dict) -> str:
        pid = params.get("pid", "").strip()
        name = params.get("name", "").strip()

        if not pid and not name:
            return "Error: provide either 'pid' or 'name'"

        # Find by name if pid not given
        if not pid and name:
            for p_id, info in _processes.items():
                if info["name"] == name and info["status"] == "running":
                    pid = p_id
                    break
            if not pid:
                return f"Error: no running process found with name '{name}'"

        info = _processes.get(pid)
        if not info:
            return f"Error: process {pid} not found"
        if info["status"] != "running":
            return f"Process {pid} ({info['name']}) already {info['status']}"

        proc = info.get("_proc")
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    await proc.wait()
            except ProcessLookupError:
                pass
        else:
            # Recovered process without asyncio handle — kill by PID directly
            try:
                os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
                await asyncio.sleep(1)
                try:
                    os.killpg(os.getpgid(int(pid)), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

        info["status"] = "stopped"
        info["stopped_at"] = datetime.now(timezone.utc).isoformat()
        info["exit_code"] = proc.returncode if proc else None
        _save_process_state()

        logger.info(f"Process stopped: {info['name']} (pid={pid})")
        return f"Process '{info['name']}' (pid={pid}) stopped."


class ListProcessesTool(Tool):
    name = "list_processes"
    description = "List all managed background processes and their status."
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, params: dict) -> str:
        if not _processes:
            return "No managed processes."

        lines = ["## Managed Processes"]
        for pid, info in _processes.items():
            status_icon = "running" if info["status"] == "running" else info["status"]
            exit_info = f" (exit={info.get('exit_code', '?')})" if info["status"] != "running" else ""
            lines.append(
                f"- **{info['name']}** (pid={pid}) [{status_icon}{exit_info}]\n"
                f"  cmd: `{info['command']}`  cwd: `{info['cwd']}`  started: {info['started_at']}"
            )
        return "\n".join(lines)


class GetProcessOutputTool(Tool):
    name = "get_process_output"
    description = "Get the recent output (stdout + stderr) of a managed background process."
    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "string",
                "description": "Process ID to get output from",
            },
            "name": {
                "type": "string",
                "description": "Process name (alternative to PID)",
            },
            "tail": {
                "type": "integer",
                "description": "Number of lines to return from the end (default: 50)",
                "default": 50,
            },
        },
    }

    async def execute(self, params: dict) -> str:
        pid = params.get("pid", "").strip()
        name = params.get("name", "").strip()
        tail = min(params.get("tail", 50), _MAX_BUFFER_LINES)

        if not pid and not name:
            return "Error: provide either 'pid' or 'name'"

        if not pid and name:
            for p_id, info in _processes.items():
                if info["name"] == name:
                    pid = p_id
                    break
            if not pid:
                return f"Error: no process found with name '{name}'"

        buf = _output_buffers.get(pid, [])
        if not buf:
            info = _processes.get(pid)
            if not info:
                return f"Error: process {pid} not found"
            return f"No output yet for '{info['name']}' (pid={pid})"

        lines = buf[-tail:]
        return "\n".join(lines)


register_tool(StartProcessTool())
register_tool(StopProcessTool())
register_tool(ListProcessesTool())
register_tool(GetProcessOutputTool())
