"""
Gmail Tool — Allows the agent to read, search, and send emails via Gmail.
Requires Gmail OAuth 2.0 to be configured and authorized.
"""
import json
import logging
from gateway.tools import Tool, register_tool

logger = logging.getLogger("gateway.tools.gmail")

# DB reference set by server.py at startup
_db = None


def set_gmail_db(database):
    global _db
    _db = database


class GmailTool(Tool):
    name = "gmail"
    description = (
        "Read, search, and send emails via Gmail. "
        "Actions: list (recent emails), search (find specific emails), read (get full email by ID), send (compose and send). "
        "Use 'list' to check inbox, 'search' with a query like 'from:boss@work.com' or 'subject:meeting', "
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
                    "- search: Search emails with a Gmail query\n"
                    "- read: Read full content of a specific email by ID\n"
                    "- send: Send a new email"
                ),
            },
            "query": {
                "type": "string",
                "description": "For 'search': Gmail search query (e.g., 'from:user@example.com', 'subject:meeting', 'is:unread'). For 'list': optional filter.",
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
            return "Error: Gmail tool not initialized. Server needs restart."

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
        from gateway.gmail import list_emails
        query = params.get("query", "in:inbox")
        max_results = min(params.get("max_results", 10), 20)

        emails = await list_emails(_db, query=query, max_results=max_results)

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
        from gateway.gmail import list_emails
        query = params.get("query", "")
        if not query:
            return "Error: 'query' is required for search. Examples: 'from:user@example.com', 'subject:report', 'is:unread'."

        max_results = min(params.get("max_results", 10), 20)
        emails = await list_emails(_db, query=query, max_results=max_results)

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
        from gateway.gmail import read_email
        message_id = params.get("message_id", "")
        if not message_id:
            return "Error: 'message_id' is required. Use 'list' or 'search' first to find email IDs."

        email = await read_email(_db, message_id)

        if "error" in email:
            return email["error"]

        # Index email into RAG + feed extractors (fire-and-forget)
        from gateway.email_memory import store_email_memory
        import asyncio
        asyncio.create_task(store_email_memory(_db, email, source="email/gmail"))

        return (
            f"Subject: {email['subject']}\n"
            f"From: {email['from']}\n"
            f"To: {email['to']}\n"
            f"Date: {email['date']}\n"
            f"Labels: {', '.join(email.get('labels', []))}\n\n"
            f"--- Body ---\n{email['body']}"
        )

    async def _send_email(self, params: dict) -> str:
        from gateway.gmail import send_email
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

        # Index the sent email into memory (captures outgoing context + people)
        from gateway.email_memory import store_email_memory
        import asyncio
        sent_email = {
            "subject": subject,
            "from": "me",
            "to": to,
            "date": "",
            "body": body,
            "labels": ["SENT"],
        }
        asyncio.create_task(store_email_memory(_db, sent_email, source="email/gmail"))

        return f"Email sent successfully to {to}. Message ID: {result['message_id']}"


register_tool(GmailTool())
