"""
Outlook Tool — Allows the agent to read, search, and send emails via Outlook/Microsoft 365.
Requires Azure AD OAuth 2.0 to be configured and authorized.
"""
import logging
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.outlook")

_db = None


def set_outlook_db(database):
    global _db
    _db = database


class OutlookTool(Tool):
    name = "outlook"
    description = (
        "Read, search, and send emails via Microsoft Outlook / Microsoft 365. "
        "Actions: list (recent emails), search (find specific emails), read (get full email by ID), send (compose and send). "
        "Use 'list' to check inbox, 'search' with a query like 'budget report' or 'from:boss@company.com', "
        "'read' with a message ID to see full content, 'send' to compose and send a new email."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search", "read", "send"],
                "description": (
                    "The email action to perform:\n"
                    "- list: Show recent inbox emails\n"
                    "- search: Search emails with a keyword/phrase query\n"
                    "- read: Read full content of a specific email by ID\n"
                    "- send: Send a new email"
                ),
            },
            "query": {
                "type": "string",
                "description": "For 'search': keyword or phrase to search across subject, body, sender. For 'list': ignored.",
            },
            "message_id": {
                "type": "string",
                "description": "For 'read': the email message ID to read.",
            },
            "to": {
                "type": "string",
                "description": "For 'send': recipient email address.",
            },
            "subject": {
                "type": "string",
                "description": "For 'send': email subject line.",
            },
            "body": {
                "type": "string",
                "description": "For 'send': email body text.",
            },
            "max_results": {
                "type": "integer",
                "description": "For 'list'/'search': maximum number of emails to return (default: 10, max: 20).",
            },
        },
        "required": ["action"],
    }

    async def execute(self, params: dict) -> str:
        if _db is None:
            return "Error: Outlook tool not initialized. Server needs restart."

        action = params.get("action", "")

        if action == "list":
            return await self._list_emails(params)
        elif action == "search":
            return await self._search_emails(params)
        elif action == "read":
            return await self._read_email(params)
        elif action == "send":
            return await self._send_email(params)
        else:
            return f"Unknown action: {action}. Use: list, search, read, send."

    async def _list_emails(self, params: dict) -> str:
        from gateway.outlook import list_emails
        max_results = min(params.get("max_results", 10), 20)

        emails = await list_emails(_db, max_results=max_results)

        if emails and "error" in emails[0]:
            return emails[0]["error"]

        if not emails:
            return "No emails found."

        lines = [f"Found {len(emails)} emails:\n"]
        for i, email in enumerate(emails, 1):
            unread = " [UNREAD]" if email.get("unread") else ""
            lines.append(
                f"{i}. {email['subject']}{unread}\n"
                f"   From: {email['from']}\n"
                f"   Date: {email['date']}\n"
                f"   Preview: {email['snippet'][:100]}\n"
                f"   ID: {email['id']}"
            )

        return "\n".join(lines)

    async def _search_emails(self, params: dict) -> str:
        from gateway.outlook import search_emails
        query = params.get("query", "")
        if not query:
            return "Error: 'query' is required for search. Examples: 'budget report', 'from:colleague@company.com'."

        max_results = min(params.get("max_results", 10), 20)
        emails = await search_emails(_db, query=query, max_results=max_results)

        if emails and "error" in emails[0]:
            return emails[0]["error"]

        if not emails:
            return f"No emails found matching: {query}"

        lines = [f"Found {len(emails)} emails matching '{query}':\n"]
        for i, email in enumerate(emails, 1):
            unread = " [UNREAD]" if email.get("unread") else ""
            lines.append(
                f"{i}. {email['subject']}{unread}\n"
                f"   From: {email['from']}\n"
                f"   Date: {email['date']}\n"
                f"   Preview: {email['snippet'][:100]}\n"
                f"   ID: {email['id']}"
            )

        return "\n".join(lines)

    async def _read_email(self, params: dict) -> str:
        from gateway.outlook import read_email
        message_id = params.get("message_id", "")
        if not message_id:
            return "Error: 'message_id' is required. Use 'list' or 'search' first to find email IDs."

        email = await read_email(_db, message_id)

        if "error" in email:
            return email["error"]

        # Index email into RAG + feed extractors (fire-and-forget)
        from gateway.email_memory import store_email_memory
        import asyncio
        asyncio.create_task(store_email_memory(_db, email, source="email/outlook"))

        return (
            f"Subject: {email['subject']}\n"
            f"From: {email['from']}\n"
            f"To: {email['to']}\n"
            f"Date: {email['date']}\n"
            f"Importance: {email.get('importance', 'normal')}\n\n"
            f"--- Body ---\n{email['body']}"
        )

    async def _send_email(self, params: dict) -> str:
        from gateway.outlook import send_email
        to = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")

        if not to:
            return "Error: 'to' (recipient email) is required."
        if not subject:
            return "Error: 'subject' is required."
        if not body:
            return "Error: 'body' is required."

        result = await send_email(_db, to=to, subject=subject, body=body)

        if "error" in result:
            return result["error"]

        return f"Email sent successfully to {to}."


register_tool(OutlookTool())
