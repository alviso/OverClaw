"""
Memory Search Tool — lets the agent search its long-term memory.
"""
import logging
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.memory_search")

# Will be set by server.py at startup
_db = None


def set_memory_db(db):
    global _db
    _db = db


class MemorySearchTool(Tool):
    name = "memory_search"
    description = "Search your long-term memory for information from past conversations. Use this when the user refers to something discussed previously, or when you need to recall context from earlier sessions."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query — what are you trying to remember?"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 5).",
                "default": 5
            }
        },
        "required": ["query"]
    }

    async def execute(self, params: dict) -> str:
        query = params.get("query", "")
        max_results = params.get("max_results", 5)

        if not query:
            return "Error: query is required"

        if _db is None:
            return "Error: Memory system not initialized"

        try:
            from gateway.memory import MemoryManager
            mgr = MemoryManager(_db)
            results = await mgr.search_memory(query, top_k=max_results)

            if not results:
                return f"No memories found matching: {query}"

            output = f"Found {len(results)} relevant memories:\n\n"
            for i, r in enumerate(results, 1):
                output += f"--- Memory {i} (similarity: {r['similarity']}) ---\n"
                output += f"Session: {r['session_id']} | Agent: {r['agent_id']}\n"
                output += f"Date: {r['created_at'][:10] if r.get('created_at') else 'unknown'}\n"
                output += f"{r['content'][:600]}\n\n"

            logger.info(f"Memory search: '{query}' -> {len(results)} results")
            return output.strip()

        except Exception as e:
            logger.exception(f"Memory search failed: {query}")
            return f"Memory search failed: {str(e)}"


register_tool(MemorySearchTool())
