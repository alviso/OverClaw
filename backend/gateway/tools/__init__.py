"""
Tool Framework — Phase 2
Defines the Tool interface, registry, and policy engine.
Inspired by OpenClaw's src/agents/tools/ and tool-policy.ts.
"""
import logging
from typing import Any

logger = logging.getLogger("gateway.tools")


class Tool:
    """Base class for all agent tools."""
    name: str = ""
    description: str = ""
    parameters: dict = {}  # JSON Schema

    async def execute(self, params: dict) -> str:
        raise NotImplementedError


# ── Registry ─────────────────────────────────────────────────────────────
_tools: dict[str, Tool] = {}


def register_tool(tool: Tool):
    _tools[tool.name] = tool
    logger.info(f"Tool registered: {tool.name}")


def get_tool(name: str) -> Tool | None:
    return _tools.get(name)


def list_tools() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in _tools.values()
    ]


def get_tools_for_openai() -> list[dict]:
    """Format tools for OpenAI function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
        }
        for t in _tools.values()
    ]


def get_tools_for_anthropic() -> list[dict]:
    """Format tools for Anthropic tool use."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in _tools.values()
    ]


# ── Policy Engine ────────────────────────────────────────────────────────
class ToolPolicy:
    """Simple allowlist-based tool policy."""

    def __init__(self, allowed: list[str] | None = None):
        self._allowed = set(allowed) if allowed else None

    def is_allowed(self, tool_name: str) -> bool:
        if self._allowed is None:
            return True  # No restriction
        return tool_name in self._allowed

    def filter_tools(self, tools: list[dict]) -> list[dict]:
        if self._allowed is None:
            return tools
        return [t for t in tools if t.get("name", t.get("function", {}).get("name", "")) in self._allowed]


DEFAULT_POLICY = ToolPolicy()  # Allow all tools


# ── Import all tools to auto-register ────────────────────────────────────
def init_tools():
    """Import tool modules to trigger registration."""
    from gateway.tools import web_search, execute_command, file_ops, memory_search  # noqa: F401
    from gateway.tools import browser, browser_use, process_mgmt, http_request  # noqa: F401
    from gateway.tools import vision, audio_transcribe, document_parse  # noqa: F401
    from gateway.tools import monitor  # noqa: F401
    from gateway.tools import gmail  # noqa: F401
    from gateway.tools import outlook  # noqa: F401
    from gateway.tools import delegate  # noqa: F401
    from gateway.tools import developer_tools  # noqa: F401
    from gateway.tools import create_tool  # noqa: F401
    from gateway.tools import process_manager  # noqa: F401
    from gateway.tools import slack_notify  # noqa: F401
    logger.info(f"Tools initialized: {len(_tools)} tools available")
