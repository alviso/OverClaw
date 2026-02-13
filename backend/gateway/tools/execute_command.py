"""
Execute Command Tool — runs shell commands with safety restrictions.
"""
import asyncio
import logging
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.execute_command")

# Commands that are allowed to execute
ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "grep", "find", "echo",
    "date", "whoami", "pwd", "env", "uname", "df", "du", "free",
    "ps", "uptime", "curl", "wget", "python3", "pip", "node", "npm",
}

# Commands that are explicitly blocked
BLOCKED_PATTERNS = {"rm -rf /", "sudo", "chmod 777", "mkfs", "dd if=", "> /dev/"}

MAX_OUTPUT_LEN = 4000
TIMEOUT_SECONDS = 30


class ExecuteCommandTool(Tool):
    name = "execute_command"
    description = "Execute a shell command on the gateway host. Only approved commands are allowed. Use this for system checks, file inspection, or running scripts."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute."
            },
            "working_directory": {
                "type": "string",
                "description": "Working directory for the command (optional).",
                "default": "/tmp"
            }
        },
        "required": ["command"]
    }

    async def execute(self, params: dict) -> str:
        command = params.get("command", "").strip()
        cwd = params.get("working_directory", "/tmp")

        if not command:
            return "Error: command is required"

        # Safety check: blocked patterns
        for blocked in BLOCKED_PATTERNS:
            if blocked in command:
                return f"Error: Command blocked for safety. Pattern '{blocked}' is not allowed."

        # Safety check: first word must be in allowed list
        first_word = command.split()[0].split("/")[-1] if command.split() else ""
        if first_word not in ALLOWED_COMMANDS:
            return f"Error: Command '{first_word}' is not in the allowed list. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=TIMEOUT_SECONDS
            )

            output = ""
            if stdout:
                out_text = stdout.decode("utf-8", errors="replace")
                output += out_text[:MAX_OUTPUT_LEN]
                if len(out_text) > MAX_OUTPUT_LEN:
                    output += "\n... (output truncated)"

            if stderr:
                err_text = stderr.decode("utf-8", errors="replace")
                if err_text.strip():
                    output += f"\n[stderr] {err_text[:1000]}"

            exit_code = process.returncode
            output += f"\n[exit code: {exit_code}]"

            logger.info(f"Command executed: '{command}' -> exit {exit_code}")
            return output.strip() if output.strip() else "(no output)"

        except asyncio.TimeoutError:
            return f"Error: Command timed out after {TIMEOUT_SECONDS}s"
        except Exception as e:
            logger.exception(f"Command execution failed: {command}")
            return f"Error: {str(e)}"


register_tool(ExecuteCommandTool())
