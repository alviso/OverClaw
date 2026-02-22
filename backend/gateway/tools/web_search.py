"""
Web Search Tool — uses DuckDuckGo (ddgs) for search results.
"""
import logging
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.web_search")


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for current information. Returns a summary of search results with titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web."
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5).",
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

        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(r)

            if not results:
                return f"No results found for: {query}"

            output = f"Search results for: {query}\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r.get('title', 'No title')}\n"
                output += f"   URL: {r.get('href', 'N/A')}\n"
                output += f"   {r.get('body', 'No description')}\n\n"

            logger.info(f"Web search: '{query}' -> {len(results)} results")
            return output.strip()

        except Exception as e:
            logger.exception(f"Web search failed: {query}")
            return f"Search failed: {str(e)}"


register_tool(WebSearchTool())
