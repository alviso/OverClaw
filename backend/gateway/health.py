"""
Gateway health state tracking.
Inspired by OpenClaw's server/health-state.ts.
"""
import time
import platform
import psutil
from datetime import datetime, timezone


_boot_time: float = time.time()
_version: str = "0.1.0"
_gateway_name: str = "OverClaw Gateway"


def get_health_snapshot() -> dict:
    now = time.time()
    uptime_seconds = int(now - _boot_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    mem = psutil.virtual_memory()

    return {
        "status": "healthy",
        "gateway": _gateway_name,
        "version": _version,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_seconds,
        "boot_time": datetime.fromtimestamp(_boot_time, tz=timezone.utc).isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.system(),
            "python": platform.python_version(),
            "memory_used_mb": round(mem.used / 1024 / 1024),
            "memory_total_mb": round(mem.total / 1024 / 1024),
            "memory_percent": mem.percent,
            "cpu_percent": psutil.cpu_percent(interval=0),
        },
    }


def get_gateway_info() -> dict:
    return {
        "name": _gateway_name,
        "version": _version,
        "boot_time": datetime.fromtimestamp(_boot_time, tz=timezone.utc).isoformat(),
    }
