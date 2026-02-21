"""
Delegate Tool — Agent-to-Agent Orchestration
Allows the orchestrator to delegate subtasks to specialist agents.
"""
import logging
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.delegate")

_agent_runner = None
_db = None


def set_delegate_context(db, agent_runner):
    """Wire up DB and AgentRunner after startup (avoids circular imports)."""
    global _agent_runner, _db
    _agent_runner = agent_runner
    _db = db


class DelegateTool(Tool):
    name = "delegate"
    description = (
        "Delegate a subtask to a specialist agent. Each specialist has its own expertise and tools. "
        "Use this to leverage the right agent for the job.\n\n"
        "IMPORTANT: Pass ALL necessary context in the 'task' field — the specialist has NO access "
        "to your conversation history. Include URLs, credentials, search terms, etc.\n\n"
        "If a specialist fails or gives a poor result, you can retry with a different agent or approach.\n\n"
        "Call list_agents first if you need to see available specialists."
    )
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "ID of the specialist agent to delegate to. Use list_agents to see available options.",
            },
            "task": {
                "type": "string",
                "description": (
                    "Clear, specific task for the specialist. Include ALL necessary context: "
                    "URLs, credentials, search queries, file paths, etc. "
                    "The specialist cannot see your conversation history."
                ),
            },
        },
        "required": ["agent_id", "task"],
    }

    async def execute(self, params: dict) -> str:
        if _agent_runner is None or _db is None:
            return "Error: delegate tool not initialized"

        agent_id = params.get("agent_id", "")
        task = params.get("task", "")

        if not agent_id or not task:
            return "Error: both 'agent_id' and 'task' are required"

        # Verify agent exists
        agent_doc = await _db.agents.find_one({"id": agent_id}, {"_id": 0})
        if not agent_doc:
            available = await _db.agents.find(
                {"id": {"$ne": "orchestrator"}}, {"_id": 0, "id": 1, "name": 1}
            ).to_list(20)
            names = [f"{a['id']} ({a.get('name', '')})" for a in available]
            return f"Error: agent '{agent_id}' not found. Available: {', '.join(names)}"

        # Prevent recursion — specialists cannot delegate
        if "delegate" in agent_doc.get("tools_allowed", []):
            return "Error: cannot delegate to an agent that has the delegate tool"

        logger.info(f"Delegating to '{agent_id}': {task[:100]}...")

        try:
            result = await _agent_runner.run_subtask(agent_id, task)
            logger.info(f"Delegation to '{agent_id}' complete: {len(result)} chars")
            return result
        except Exception as e:
            logger.exception(f"Delegation to '{agent_id}' failed")
            return f"Specialist agent '{agent_id}' failed: {str(e)}"


class ListAgentsTool(Tool):
    name = "list_agents"
    description = "List all available specialist agents with their capabilities. Use before delegating to choose the right agent."
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, params: dict) -> str:
        if not _db:
            return "Error: not initialized"

        agents = await _db.agents.find({}, {"_id": 0}).to_list(50)
        if not agents:
            return "No specialist agents configured."

        lines = []
        for a in agents:
            tools = ", ".join(a.get("tools_allowed", []))
            lines.append(
                f"- **{a['id']}** ({a.get('name', 'unnamed')}): "
                f"{a.get('description', 'No description')} | "
                f"Model: {a.get('model', 'default')} | Tools: {tools}"
            )
        return "Available specialist agents:\n" + "\n".join(lines)


register_tool(DelegateTool())
register_tool(ListAgentsTool())
