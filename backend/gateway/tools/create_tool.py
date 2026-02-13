"""
Create Tool — Meta-tool that allows the agent to create new tools at runtime.
The agent writes Python code for a tool, which is then dynamically loaded
and registered into the tool registry. Tool definitions are persisted in MongoDB
so they survive restarts.
"""
import os
import sys
import json
import importlib
import logging
import textwrap
from pathlib import Path
from gateway.tools import Tool, register_tool, get_tool

logger = logging.getLogger("gateway.tools.create_tool")

CUSTOM_TOOLS_DIR = Path("/app/workspace/custom_tools")
CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)

_db = None


def set_create_tool_db(db):
    global _db
    _db = db


async def _persist_tool(name: str, description: str, parameters: dict, code: str):
    """Store tool definition in MongoDB for reload on restart."""
    if _db is None:
        return
    await _db.custom_tools.update_one(
        {"name": name},
        {"$set": {
            "name": name,
            "description": description,
            "parameters": parameters,
            "code": code,
        }},
        upsert=True,
    )


async def load_persisted_tools():
    """Load all custom tools from MongoDB on startup."""
    if _db is None:
        return
    tools = await _db.custom_tools.find({}, {"_id": 0}).to_list(100)
    for tool_def in tools:
        try:
            _register_dynamic_tool(
                tool_def["name"],
                tool_def["description"],
                tool_def["parameters"],
                tool_def["code"],
            )
            logger.info(f"Loaded persisted custom tool: {tool_def['name']}")
        except Exception as e:
            logger.warning(f"Failed to load custom tool '{tool_def['name']}': {e}")


def _register_dynamic_tool(name: str, description: str, parameters: dict, code: str):
    """Create a Tool subclass from the provided code and register it."""
    # Write the code to a file for traceability
    file_path = CUSTOM_TOOLS_DIR / f"{name}.py"
    file_path.write_text(code, encoding="utf-8")

    # The code must define an async function called `execute(params: dict) -> str`
    # We compile and exec it in an isolated namespace
    namespace = {
        "os": os,
        "sys": sys,
        "json": json,
        "Path": Path,
        "logging": logging,
        "asyncio": __import__("asyncio"),
        "subprocess": __import__("subprocess"),
    }

    exec(compile(code, str(file_path), "exec"), namespace)

    if "execute" not in namespace:
        raise ValueError("Tool code must define an async function: `async def execute(params: dict) -> str`")

    execute_fn = namespace["execute"]

    # Create a dynamic Tool subclass
    tool_instance = type(
        f"CustomTool_{name}",
        (Tool,),
        {
            "name": name,
            "description": description,
            "parameters": parameters,
            "__custom__": True,
        },
    )()

    # Bind the execute method
    import types
    tool_instance.execute = types.MethodType(lambda self, params, _fn=execute_fn: _fn(params), tool_instance)

    register_tool(tool_instance)
    logger.info(f"Dynamic tool registered: {name}")
    return tool_instance


class CreateToolTool(Tool):
    name = "create_tool"
    description = (
        "Create a new tool that the agent can use. This is a meta-tool that lets you extend your own capabilities.\n\n"
        "You provide:\n"
        "- `name`: A unique snake_case tool name\n"
        "- `description`: What the tool does (shown to the LLM)\n"
        "- `parameters`: JSON Schema for the tool's input parameters\n"
        "- `code`: Python code defining an `async def execute(params: dict) -> str` function\n\n"
        "The code runs in an isolated namespace with access to: os, sys, json, Path, logging, asyncio, subprocess.\n"
        "The tool is immediately available after creation and persists across restarts.\n\n"
        "Example code:\n"
        '```python\n'
        'async def execute(params: dict) -> str:\n'
        '    name = params.get("name", "World")\n'
        '    return f"Hello, {name}!"\n'
        '```'
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique snake_case name for the tool (e.g. 'fetch_stock_price')",
            },
            "description": {
                "type": "string",
                "description": "Human-readable description of what the tool does",
            },
            "parameters_schema": {
                "type": "object",
                "description": "JSON Schema for the tool's input parameters",
            },
            "code": {
                "type": "string",
                "description": "Python code defining `async def execute(params: dict) -> str`",
            },
        },
        "required": ["name", "description", "parameters_schema", "code"],
    }

    async def execute(self, params: dict) -> str:
        name = params.get("name", "").strip()
        description = params.get("description", "").strip()
        parameters_schema = params.get("parameters_schema", {})
        code = params.get("code", "").strip()

        if not name:
            return "Error: 'name' is required"
        if not description:
            return "Error: 'description' is required"
        if not code:
            return "Error: 'code' is required"

        # Validate name format
        if not name.replace("_", "").isalnum():
            return "Error: tool name must be snake_case alphanumeric"

        # Prevent overwriting built-in tools
        existing = get_tool(name)
        if existing and not getattr(existing, "__custom__", False):
            return f"Error: cannot overwrite built-in tool '{name}'"

        # Validate code contains the required function
        if "async def execute" not in code:
            return "Error: code must define `async def execute(params: dict) -> str`"

        # Safety: block dangerous operations
        dangerous = ["import shutil", "rmtree", "os.remove", "os.unlink", "__import__('os').system"]
        for d in dangerous:
            if d in code:
                return f"Error: code contains blocked operation: '{d}'"

        try:
            _register_dynamic_tool(name, description, parameters_schema, code)
            await _persist_tool(name, description, parameters_schema, code)
            return f"Tool '{name}' created and registered successfully. It is now available for use."
        except Exception as e:
            logger.exception(f"Failed to create tool '{name}'")
            return f"Error creating tool: {str(e)}"


class ListCustomToolsTool(Tool):
    name = "list_custom_tools"
    description = "List all custom tools that have been created dynamically."
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, params: dict) -> str:
        if _db is None:
            return "Error: database not initialized"

        tools = await _db.custom_tools.find({}, {"_id": 0, "name": 1, "description": 1}).to_list(100)
        if not tools:
            return "No custom tools have been created yet."

        lines = ["## Custom Tools"]
        for t in tools:
            lines.append(f"- **{t['name']}**: {t.get('description', 'No description')}")
        return "\n".join(lines)


class DeleteCustomToolTool(Tool):
    name = "delete_custom_tool"
    description = "Delete a custom tool that was created dynamically."
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the custom tool to delete",
            },
        },
        "required": ["name"],
    }

    async def execute(self, params: dict) -> str:
        name = params.get("name", "").strip()
        if not name:
            return "Error: 'name' is required"

        existing = get_tool(name)
        if not existing:
            return f"Error: tool '{name}' not found"
        if not getattr(existing, "__custom__", False):
            return f"Error: '{name}' is a built-in tool and cannot be deleted"

        # Remove from registry
        from gateway.tools import _tools
        _tools.pop(name, None)

        # Remove from DB
        if _db is not None:
            await _db.custom_tools.delete_one({"name": name})

        # Remove file
        file_path = CUSTOM_TOOLS_DIR / f"{name}.py"
        if file_path.exists():
            file_path.unlink()

        return f"Custom tool '{name}' deleted successfully."


register_tool(CreateToolTool())
register_tool(ListCustomToolsTool())
register_tool(DeleteCustomToolTool())
