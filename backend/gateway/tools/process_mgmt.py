"""
Process Management Tool — System info, process listing, resource monitoring.
"""
import logging
import psutil
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.process_mgmt")


class SystemInfoTool(Tool):
    name = "system_info"
    description = (
        "Get system information: CPU usage, memory usage, disk space, "
        "running processes, or network connections. Use this to diagnose "
        "performance issues or check system health."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["overview", "processes", "disk", "network"],
                "description": (
                    "'overview' = CPU, memory, uptime summary. "
                    "'processes' = top processes by CPU/memory. "
                    "'disk' = disk usage per partition. "
                    "'network' = active network connections."
                ),
                "default": "overview",
            },
            "top_n": {
                "type": "integer",
                "description": "Number of top processes to return (for 'processes' action). Default 15.",
                "default": 15,
            },
        },
        "required": [],
    }

    async def execute(self, params: dict) -> str:
        action = params.get("action", "overview")
        top_n = min(params.get("top_n", 15), 50)

        try:
            if action == "overview":
                return self._overview()
            elif action == "processes":
                return self._processes(top_n)
            elif action == "disk":
                return self._disk()
            elif action == "network":
                return self._network()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.exception("System info error")
            return f"Error getting system info: {str(e)}"

    def _overview(self) -> str:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        boot = psutil.boot_time()

        import datetime
        uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(boot)
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)

        lines = [
            "## System Overview",
            f"- **CPU Usage:** {cpu}% ({psutil.cpu_count()} cores)",
            f"- **Memory:** {mem.used / 1e9:.1f} GB / {mem.total / 1e9:.1f} GB ({mem.percent}%)",
            f"- **Swap:** {swap.used / 1e9:.1f} GB / {swap.total / 1e9:.1f} GB ({swap.percent}%)",
            f"- **Uptime:** {hours}h {minutes}m",
            f"- **Processes:** {len(psutil.pids())} running",
        ]
        return "\n".join(lines)

    def _processes(self, top_n: int) -> str:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda x: (x.get("cpu_percent") or 0) + (x.get("memory_percent") or 0), reverse=True)

        lines = [f"## Top {top_n} Processes (by CPU + Memory)", "| PID | Name | CPU% | Mem% | Status |", "|-----|------|------|------|--------|"]
        for p in procs[:top_n]:
            lines.append(f"| {p['pid']} | {p['name'][:25]} | {p.get('cpu_percent', 0):.1f} | {p.get('memory_percent', 0):.1f} | {p.get('status', '?')} |")
        return "\n".join(lines)

    def _disk(self) -> str:
        lines = ["## Disk Usage", "| Mount | Total | Used | Free | Usage |", "|-------|-------|------|------|-------|"]
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                lines.append(
                    f"| {part.mountpoint} | {usage.total / 1e9:.1f} GB | "
                    f"{usage.used / 1e9:.1f} GB | {usage.free / 1e9:.1f} GB | {usage.percent}% |"
                )
            except PermissionError:
                continue
        return "\n".join(lines)

    def _network(self) -> str:
        conns = psutil.net_connections(kind="inet")
        lines = [f"## Network Connections ({len(conns)} total)", "| Proto | Local | Remote | Status |", "|-------|-------|--------|--------|"]
        for c in conns[:30]:
            local = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "?"
            remote = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
            proto = "TCP" if c.type == 1 else "UDP"
            lines.append(f"| {proto} | {local} | {remote} | {c.status} |")
        if len(conns) > 30:
            lines.append(f"\n*...and {len(conns) - 30} more connections*")
        return "\n".join(lines)


register_tool(SystemInfoTool())
