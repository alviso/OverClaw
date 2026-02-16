"""
Outlook OAuth 2.0 Integration — Handles auth flow and API operations.
Uses Microsoft Graph API with MSAL for OAuth and httpx for API calls.
Tokens stored in MongoDB for persistence across restarts.
Mirrors the Gmail integration pattern.
"""
import os
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional

import msal

logger = logging.getLogger("gateway.outlook")

SCOPES = [
    "User.Read",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "offline_access",
]

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_db_ref = None
_oauth_states: dict[str, dict] = {}


def set_outlook_db_ref(database):
    global _db_ref
    _db_ref = database


def _get_msal_app() -> msal.ConfidentialClientApplication:
    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    tenant_id = os.environ.get("AZURE_TENANT_ID", "common")

    if not client_id or not client_secret:
        raise ValueError("AZURE_CLIENT_ID and AZURE_CLIENT_SECRET must be set")

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )


def get_redirect_uri() -> str:
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not backend_url:
        backend_url = os.environ.get("BACKEND_URL", "http://localhost:8001")
    return f"{backend_url}/api/oauth/outlook/callback"


def create_auth_url(user_id: str = "default") -> str:
    """Generate Microsoft OAuth authorization URL."""
    app = _get_msal_app()
    flow = app.initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=get_redirect_uri(),
    )
    # Store the flow state for callback validation
    state = flow.get("state", "")
    _oauth_states[state] = {
        "user_id": user_id,
        "flow": flow,
        "created_at": datetime.now(timezone.utc),
    }
    return flow["auth_uri"]


async def handle_callback(code: str, state: str, full_url: str, db) -> dict:
    """Exchange authorization code for tokens and store them."""
    state_data = _oauth_states.pop(state, None)

    if not state_data:
        raise ValueError("Invalid or expired OAuth state")

    user_id = state_data["user_id"]
    flow = state_data["flow"]
    app = _get_msal_app()

    # MSAL needs the full callback URL with query params to complete the flow
    # We need to pass the auth_response dict
    import urllib.parse
    parsed = urllib.parse.urlparse(full_url)
    query_params = dict(urllib.parse.parse_qsl(parsed.query))

    result = app.acquire_token_by_auth_code_flow(flow, query_params)

    if "error" in result:
        raise ValueError(f"Token acquisition failed: {result.get('error_description', result['error'])}")

    token_doc = {
        "user_id": user_id,
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "id_token_claims": result.get("id_token_claims", {}),
        "expires_in": result.get("expires_in", 3600),
        "token_acquired_at": datetime.now(timezone.utc).isoformat(),
        "scopes": result.get("scope", "").split() if isinstance(result.get("scope"), str) else SCOPES,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.outlook_tokens.replace_one(
        {"user_id": user_id},
        token_doc,
        upsert=True,
    )

    # Get user email
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GRAPH_BASE}/me",
                headers={"Authorization": f"Bearer {result['access_token']}"},
            )
            if resp.status_code == 200:
                profile = resp.json()
                email = profile.get("mail") or profile.get("userPrincipalName", "unknown")
                await db.outlook_tokens.update_one(
                    {"user_id": user_id},
                    {"$set": {"email": email, "display_name": profile.get("displayName", "")}},
                )
                logger.info(f"Outlook connected for {email}")
                return {"ok": True, "email": email}
    except Exception as e:
        logger.warning(f"Could not fetch Outlook profile: {e}")

    return {"ok": True, "email": "connected"}


async def _get_valid_token(db, user_id: str = "default") -> Optional[str]:
    """Get a valid access token, refreshing via MSAL if needed."""
    token_doc = await db.outlook_tokens.find_one({"user_id": user_id}, {"_id": 0})
    if not token_doc:
        return None

    # Check if token is still valid (with 5 min buffer)
    from dateutil.parser import isoparse
    acquired_at = isoparse(token_doc["token_acquired_at"])
    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=timezone.utc)
    expires_in = token_doc.get("expires_in", 3600)
    from datetime import timedelta
    expires_at = acquired_at + timedelta(seconds=expires_in - 300)

    if datetime.now(timezone.utc) < expires_at:
        return token_doc["access_token"]

    # Token expired — try to refresh
    refresh_token = token_doc.get("refresh_token")
    if not refresh_token:
        logger.warning("Outlook token expired and no refresh token available")
        return None

    try:
        app = _get_msal_app()
        result = app.acquire_token_by_refresh_token(refresh_token, scopes=SCOPES)

        if "error" in result:
            logger.error(f"Outlook token refresh failed: {result.get('error_description', result['error'])}")
            return None

        await db.outlook_tokens.update_one(
            {"user_id": user_id},
            {"$set": {
                "access_token": result["access_token"],
                "refresh_token": result.get("refresh_token", refresh_token),
                "expires_in": result.get("expires_in", 3600),
                "token_acquired_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info("Outlook token refreshed")
        return result["access_token"]

    except Exception as e:
        logger.error(f"Outlook token refresh error: {e}")
        return None


async def get_outlook_status(db, user_id: str = "default") -> dict:
    """Check Outlook connection status."""
    token_doc = await db.outlook_tokens.find_one({"user_id": user_id}, {"_id": 0})
    if not token_doc:
        return {"connected": False}

    return {
        "connected": True,
        "email": token_doc.get("email", "unknown"),
        "display_name": token_doc.get("display_name", ""),
        "connected_at": token_doc.get("connected_at"),
    }


async def list_emails(db, user_id: str = "default", folder: str = "inbox", max_results: int = 10) -> list[dict]:
    """List emails from Outlook mailbox."""
    token = await _get_valid_token(db, user_id)
    if not token:
        return [{"error": "Outlook not connected. Please connect via the dashboard."}]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GRAPH_BASE}/me/mailFolders/{folder}/messages",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "$top": min(max_results, 20),
                    "$select": "id,subject,from,receivedDateTime,isRead,importance,hasAttachments,bodyPreview",
                    "$orderby": "receivedDateTime desc",
                },
            )

            if resp.status_code != 200:
                return [{"error": f"Outlook API error: {resp.status_code} {resp.text[:200]}"}]

            data = resp.json()
            emails = []
            for msg in data.get("value", []):
                from_addr = msg.get("from", {}).get("emailAddress", {})
                emails.append({
                    "id": msg["id"],
                    "subject": msg.get("subject", "(No Subject)"),
                    "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>",
                    "date": msg.get("receivedDateTime", ""),
                    "snippet": msg.get("bodyPreview", "")[:150],
                    "unread": not msg.get("isRead", True),
                    "importance": msg.get("importance", "normal"),
                    "has_attachments": msg.get("hasAttachments", False),
                })

            return emails

    except Exception as e:
        logger.exception("Failed to list Outlook emails")
        return [{"error": f"Outlook API error: {str(e)}"}]


async def search_emails(db, query: str, user_id: str = "default", max_results: int = 10) -> list[dict]:
    """Search Outlook emails using $search query."""
    token = await _get_valid_token(db, user_id)
    if not token:
        return [{"error": "Outlook not connected. Please connect via the dashboard."}]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GRAPH_BASE}/me/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "ConsistencyLevel": "eventual",
                },
                params={
                    "$search": f'"{query}"',
                    "$top": min(max_results, 20),
                    "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
                },
            )

            if resp.status_code != 200:
                return [{"error": f"Outlook search error: {resp.status_code} {resp.text[:200]}"}]

            data = resp.json()
            emails = []
            for msg in data.get("value", []):
                from_addr = msg.get("from", {}).get("emailAddress", {})
                emails.append({
                    "id": msg["id"],
                    "subject": msg.get("subject", "(No Subject)"),
                    "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>",
                    "date": msg.get("receivedDateTime", ""),
                    "snippet": msg.get("bodyPreview", "")[:150],
                    "unread": not msg.get("isRead", True),
                })

            return emails

    except Exception as e:
        logger.exception("Failed to search Outlook emails")
        return [{"error": f"Outlook search error: {str(e)}"}]


async def read_email(db, message_id: str, user_id: str = "default") -> dict:
    """Read a specific Outlook email by ID."""
    token = await _get_valid_token(db, user_id)
    if not token:
        return {"error": "Outlook not connected."}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GRAPH_BASE}/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "$select": "id,subject,from,toRecipients,receivedDateTime,body,importance,hasAttachments",
                },
            )

            if resp.status_code != 200:
                return {"error": f"Outlook API error: {resp.status_code}"}

            msg = resp.json()
            from_addr = msg.get("from", {}).get("emailAddress", {})
            to_list = [r.get("emailAddress", {}).get("address", "") for r in msg.get("toRecipients", [])]

            body_content = msg.get("body", {}).get("content", "")
            body_type = msg.get("body", {}).get("contentType", "text")

            # Strip HTML if needed
            if body_type.lower() == "html":
                import re
                body_content = re.sub(r"<[^>]+>", "", body_content)
                body_content = body_content.strip()[:5000]

            return {
                "id": msg["id"],
                "subject": msg.get("subject", "(No Subject)"),
                "from": f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>",
                "to": ", ".join(to_list),
                "date": msg.get("receivedDateTime", ""),
                "body": body_content,
                "importance": msg.get("importance", "normal"),
            }

    except Exception as e:
        logger.exception("Failed to read Outlook email")
        return {"error": f"Outlook API error: {str(e)}"}


async def send_email(db, to: str, subject: str, body: str, user_id: str = "default") -> dict:
    """Send an email via Outlook."""
    token = await _get_valid_token(db, user_id)
    if not token:
        return {"error": "Outlook not connected."}

    try:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": True,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GRAPH_BASE}/me/sendMail",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if resp.status_code == 202:
                logger.info(f"Outlook email sent to {to}")
                return {"ok": True, "message_id": "sent", "to": to}
            else:
                return {"error": f"Outlook send error: {resp.status_code} {resp.text[:200]}"}

    except Exception as e:
        logger.exception("Failed to send Outlook email")
        return {"error": f"Outlook send error: {str(e)}"}
