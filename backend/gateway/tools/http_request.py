"""
HTTP Request Tool — Make arbitrary HTTP calls to APIs and webhooks.
"""
import json
import logging
import httpx
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.http_request")

TIMEOUT = 20
MAX_RESPONSE_SIZE = 10000


class HttpRequestTool(Tool):
    name = "http_request"
    description = (
        "Make HTTP requests to any URL (APIs, webhooks, REST endpoints). "
        "Supports GET, POST, PUT, PATCH, DELETE. "
        "Use this to interact with external services, fetch API data, or trigger webhooks."
    )
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method.",
                "default": "GET",
            },
            "url": {
                "type": "string",
                "description": "The full URL to request.",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs (e.g., {\"Authorization\": \"Bearer xxx\"}).",
            },
            "body": {
                "type": "object",
                "description": "Optional JSON request body (for POST/PUT/PATCH).",
            },
            "params": {
                "type": "object",
                "description": "Optional URL query parameters as key-value pairs.",
            },
        },
        "required": ["url"],
    }

    async def execute(self, params: dict) -> str:
        method = params.get("method", "GET").upper()
        url = params.get("url", "")
        headers = params.get("headers") or {}
        body = params.get("body")
        query_params = params.get("params")

        if not url:
            return "Error: url is required"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                kwargs = {"headers": headers}
                if query_params:
                    kwargs["params"] = query_params
                if body and method in ("POST", "PUT", "PATCH"):
                    kwargs["json"] = body

                response = await client.request(method, url, **kwargs)

            status = response.status_code
            resp_headers = dict(response.headers)
            content_type = resp_headers.get("content-type", "")

            # Try to parse as JSON
            try:
                resp_body = response.json()
                body_str = json.dumps(resp_body, indent=2)
            except Exception:
                body_str = response.text

            # Truncate large responses
            if len(body_str) > MAX_RESPONSE_SIZE:
                body_str = body_str[:MAX_RESPONSE_SIZE] + f"\n\n... (truncated, total {len(response.text)} chars)"

            result = f"**{method} {url}**\n"
            result += f"**Status:** {status}\n"
            result += f"**Content-Type:** {content_type}\n\n"
            result += f"**Response:**\n```\n{body_str}\n```"

            logger.info(f"HTTP {method} {url} -> {status}")
            return result

        except httpx.TimeoutException:
            return f"Error: Request to {url} timed out after {TIMEOUT}s"
        except Exception as e:
            logger.exception(f"HTTP request error: {method} {url}")
            return f"Error making HTTP request: {str(e)}"


register_tool(HttpRequestTool())
