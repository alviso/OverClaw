"""
Developer Tools — Enhanced file and code management for the developer agent.
Provides: create_directory, patch_file, search_in_files
"""
import os
import re
import logging
from pathlib import Path
from gateway.tools import Tool, register_tool
from gateway.tools.file_ops import WORKSPACE_DIR, safe_path, MAX_READ_SIZE

logger = logging.getLogger("gateway.tools.developer_tools")


class CreateDirectoryTool(Tool):
    name = "create_directory"
    description = "Create a directory (and any parent directories) in the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path relative to the workspace (e.g. 'projects/my-app/src')",
            },
        },
        "required": ["path"],
    }

    async def execute(self, params: dict) -> str:
        dirpath = params.get("path", "").strip()
        if not dirpath:
            return "Error: 'path' is required"

        try:
            resolved = safe_path(dirpath)
            resolved.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory created: {dirpath}")
            return f"Directory created: {dirpath}"
        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error creating directory: {str(e)}"


class PatchFileTool(Tool):
    name = "patch_file"
    description = (
        "Apply line-based edits to an existing file. Supports insert, replace, and delete operations.\n"
        "Operations are applied in order. Line numbers are 1-based.\n\n"
        "Each operation is an object with:\n"
        "- `op`: 'insert' | 'replace' | 'delete'\n"
        "- `line`: Line number (for insert: inserts AFTER this line; use 0 for start)\n"
        "- `end_line`: (replace/delete only) End line number (inclusive)\n"
        "- `content`: (insert/replace only) New content to add\n"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the workspace",
            },
            "operations": {
                "type": "array",
                "description": "List of edit operations to apply",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["insert", "replace", "delete"],
                        },
                        "line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                        "content": {"type": "string"},
                    },
                    "required": ["op", "line"],
                },
            },
        },
        "required": ["path", "operations"],
    }

    async def execute(self, params: dict) -> str:
        filepath = params.get("path", "")
        operations = params.get("operations", [])

        if not filepath:
            return "Error: 'path' is required"
        if not operations:
            return "Error: 'operations' list is required"

        try:
            resolved = safe_path(filepath)
            if not resolved.exists():
                return f"Error: File not found: {filepath}"

            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            # Ensure lines end with newline
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"

            changes = 0
            # Apply operations in reverse order of line number to avoid offset issues
            sorted_ops = sorted(operations, key=lambda o: o.get("line", 0), reverse=True)

            for op in sorted_ops:
                action = op.get("op")
                line_num = op.get("line", 0)
                end_line = op.get("end_line", line_num)
                content = op.get("content", "")

                if action == "insert":
                    new_lines = content.splitlines(keepends=True)
                    if new_lines and not new_lines[-1].endswith("\n"):
                        new_lines[-1] += "\n"
                    lines[line_num:line_num] = new_lines
                    changes += 1

                elif action == "replace":
                    new_lines = content.splitlines(keepends=True)
                    if new_lines and not new_lines[-1].endswith("\n"):
                        new_lines[-1] += "\n"
                    start = max(0, line_num - 1)
                    end = min(len(lines), end_line)
                    lines[start:end] = new_lines
                    changes += 1

                elif action == "delete":
                    start = max(0, line_num - 1)
                    end = min(len(lines), end_line)
                    del lines[start:end]
                    changes += 1

            resolved.write_text("".join(lines), encoding="utf-8")
            total_lines = len(lines)
            logger.info(f"File patched: {filepath} ({changes} operations, {total_lines} lines)")
            return f"File patched: {filepath} — {changes} operations applied, {total_lines} lines total"

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.exception(f"Patch file failed: {filepath}")
            return f"Error patching file: {str(e)}"


class SearchInFilesTool(Tool):
    name = "search_in_files"
    description = (
        "Search for a pattern (regex or plain text) across files in the workspace.\n"
        "Returns matching lines with file paths and line numbers."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search pattern (regex supported)",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (relative to workspace, default: '.')",
                "default": ".",
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob pattern for filenames to include (e.g. '*.py', '*.js'). Default: '*'",
                "default": "*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matching lines to return. Default: 50",
                "default": 50,
            },
        },
        "required": ["pattern"],
    }

    async def execute(self, params: dict) -> str:
        pattern = params.get("pattern", "")
        search_path = params.get("path", ".")
        file_pattern = params.get("file_pattern", "*")
        max_results = min(params.get("max_results", 50), 200)

        if not pattern:
            return "Error: 'pattern' is required"

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Error: invalid regex pattern: {e}"

        try:
            resolved = safe_path(search_path)
            if not resolved.exists() or not resolved.is_dir():
                return f"Error: Directory not found: {search_path}"

            results = []
            files_searched = 0

            for fpath in sorted(resolved.rglob(file_pattern)):
                if not fpath.is_file():
                    continue
                if fpath.stat().st_size > MAX_READ_SIZE:
                    continue
                # Skip binary files
                try:
                    content = fpath.read_text(encoding="utf-8", errors="strict")
                except (UnicodeDecodeError, ValueError):
                    continue

                files_searched += 1
                rel_path = fpath.relative_to(WORKSPACE_DIR)

                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        results.append(f"{rel_path}:{i}: {line.rstrip()}")
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break

            if not results:
                return f"No matches found for '{pattern}' in {files_searched} files"

            header = f"Found {len(results)} matches in {files_searched} files searched:"
            truncated = f"\n(truncated at {max_results} results)" if len(results) >= max_results else ""
            return header + "\n" + "\n".join(results) + truncated

        except ValueError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            logger.exception("Search in files failed")
            return f"Error: {str(e)}"


register_tool(CreateDirectoryTool())
register_tool(PatchFileTool())
register_tool(SearchInFilesTool())
