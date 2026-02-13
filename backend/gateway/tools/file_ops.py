"""
File Operations Tools — read and write files within a workspace.
"""
import os
import logging
from pathlib import Path
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.file_ops")

WORKSPACE_DIR = Path("/app/workspace")
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

MAX_READ_SIZE = 50000  # 50KB max read
MAX_WRITE_SIZE = 50000


def safe_path(filepath: str) -> Path:
    """Resolve path within workspace, prevent directory traversal."""
    resolved = (WORKSPACE_DIR / filepath).resolve()
    if not str(resolved).startswith(str(WORKSPACE_DIR.resolve())):
        raise ValueError(f"Path escapes workspace: {filepath}")
    return resolved


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file from the workspace. Use this to inspect files, read data, or check configurations."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the workspace directory."
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to read (default: all).",
                "default": 0
            }
        },
        "required": ["path"]
    }

    async def execute(self, params: dict) -> str:
        filepath = params.get("path", "")
        max_lines = params.get("max_lines", 0)

        if not filepath:
            return "Error: path is required"

        try:
            resolved = safe_path(filepath)
            if not resolved.exists():
                return f"Error: File not found: {filepath}"
            if not resolved.is_file():
                return f"Error: Not a file: {filepath}"
            if resolved.stat().st_size > MAX_READ_SIZE:
                return f"Error: File too large ({resolved.stat().st_size} bytes). Max: {MAX_READ_SIZE}"

            content = resolved.read_text(encoding="utf-8", errors="replace")
            if max_lines > 0:
                lines = content.splitlines()
                content = "\n".join(lines[:max_lines])
                if len(lines) > max_lines:
                    content += f"\n... ({len(lines) - max_lines} more lines)"

            logger.info(f"File read: {filepath} ({len(content)} chars)")
            return content if content else "(empty file)"

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.exception(f"File read failed: {filepath}")
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file in the workspace. Creates the file if it doesn't exist, overwrites if it does."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the workspace directory."
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file."
            }
        },
        "required": ["path", "content"]
    }

    async def execute(self, params: dict) -> str:
        filepath = params.get("path", "")
        content = params.get("content", "")

        if not filepath:
            return "Error: path is required"
        if len(content) > MAX_WRITE_SIZE:
            return f"Error: Content too large ({len(content)} bytes). Max: {MAX_WRITE_SIZE}"

        try:
            resolved = safe_path(filepath)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            logger.info(f"File written: {filepath} ({len(content)} chars)")
            return f"File written: {filepath} ({len(content)} chars)"

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.exception(f"File write failed: {filepath}")
            return f"Error writing file: {str(e)}"


class ListFilesTool(Tool):
    name = "list_files"
    description = "List files and directories in the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path relative to workspace (default: root).",
                "default": "."
            }
        },
        "required": []
    }

    async def execute(self, params: dict) -> str:
        dirpath = params.get("path", ".")
        try:
            resolved = safe_path(dirpath)
            if not resolved.exists():
                return f"Error: Directory not found: {dirpath}"
            if not resolved.is_dir():
                return f"Error: Not a directory: {dirpath}"

            entries = []
            for item in sorted(resolved.iterdir()):
                rel = item.relative_to(WORKSPACE_DIR)
                if item.is_dir():
                    entries.append(f"  {rel}/")
                else:
                    size = item.stat().st_size
                    entries.append(f"  {rel}  ({size} bytes)")

            if not entries:
                return f"Directory '{dirpath}' is empty"

            return f"Contents of {dirpath}:\n" + "\n".join(entries)

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"


register_tool(ReadFileTool())
register_tool(WriteFileTool())
register_tool(ListFilesTool())
