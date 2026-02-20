"""
Gmail OAuth 2.0 Integration — Handles auth flow and API operations.
Tokens stored in MongoDB for persistence across restarts.
"""
import os
import logging
import warnings
from datetime import datetime, timezone
from typing import Optional

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

logger = logging.getLogger("gateway.gmail")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.labels",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# In-memory state store for OAuth flow (short-lived)
_oauth_states: dict[str, dict] = {}
_db_ref = None


def set_gmail_db_ref(database):
    """Set DB reference for persistent OAuth state storage."""
    global _db_ref
    _db_ref = database


def _get_client_config() -> dict:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_redirect_uri() -> str:
    backend_url = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not backend_url:
        backend_url = os.environ.get("BACKEND_URL", "http://localhost:8001")
    return f"{backend_url}/api/oauth/gmail/callback"


def create_auth_url(user_id: str = "default") -> str:
    """Generate Google OAuth authorization URL."""
    flow = Flow.from_client_config(
        _get_client_config(),
        scopes=SCOPES,
        redirect_uri=get_redirect_uri(),
    )
    url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    _oauth_states[state] = {
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
    }
    # Also persist to DB for resilience across restarts
    if _db_ref is not None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_db_ref.oauth_states.replace_one(
                    {"state": state},
                    {"state": state, "user_id": user_id, "created_at": datetime.now(timezone.utc).isoformat()},
                    upsert=True,
                ))
        except Exception:
            pass
    return url


async def handle_callback(code: str, state: str, db) -> dict:
    """Exchange authorization code for tokens and store them."""
    import os
    # Allow Google to return fewer scopes than requested
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

    state_data = _oauth_states.pop(state, None)

    # Fallback: check DB for persisted state
    if not state_data and db:
        db_state = await db.oauth_states.find_one_and_delete({"state": state})
        if db_state:
            state_data = {"user_id": db_state.get("user_id", "default")}

    if not state_data:
        raise ValueError("Invalid or expired OAuth state")

    user_id = state_data["user_id"]

    flow = Flow.from_client_config(
        _get_client_config(),
        scopes=SCOPES,
        redirect_uri=get_redirect_uri(),
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        flow.fetch_token(code=code)

    creds = flow.credentials

    token_doc = {
        "user_id": user_id,
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        "expires_at": creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else None,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.gmail_tokens.replace_one(
        {"user_id": user_id},
        token_doc,
        upsert=True,
    )

    # Get user email for display
    try:
        # Try userinfo endpoint first (uses openid scope, more reliable)
        import httplib2
        http = creds.authorize(httplib2.Http())
        resp, content = http.request("https://www.googleapis.com/oauth2/v2/userinfo")
        if resp.status == 200:
            import json as _json
            info = _json.loads(content)
            email = info.get("email", "unknown")
        else:
            # Fallback to Gmail profile API
            service = build("gmail", "v1", credentials=creds)
            profile = service.users().getProfile(userId="me").execute()
            email = profile.get("emailAddress", "unknown")

        await db.gmail_tokens.update_one(
            {"user_id": user_id},
            {"$set": {"email": email}},
        )
        logger.info(f"Gmail connected for {email}")
        return {"ok": True, "email": email}
    except Exception as e:
        logger.warning(f"Could not fetch Gmail profile: {e}")
        return {"ok": True, "email": "connected"}


async def get_credentials(db, user_id: str = "default") -> Optional[Credentials]:
    """Get valid Gmail credentials, refreshing if needed."""
    token_doc = await db.gmail_tokens.find_one({"user_id": user_id}, {"_id": 0})
    if not token_doc:
        return None

    creds = Credentials(
        token=token_doc["access_token"],
        refresh_token=token_doc.get("refresh_token"),
        token_uri=token_doc.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_doc.get("client_id"),
        client_secret=token_doc.get("client_secret"),
    )

    # Check if expired and refresh
    if token_doc.get("expires_at"):
        from dateutil.parser import isoparse
        expires = isoparse(token_doc["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires:
            try:
                creds.refresh(GoogleRequest())
                await db.gmail_tokens.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "access_token": creds.token,
                        "expires_at": creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else None,
                    }},
                )
                logger.info("Gmail token refreshed")
            except Exception as e:
                logger.error(f"Gmail token refresh failed: {e}")
                return None

    return creds


async def get_gmail_status(db, user_id: str = "default") -> dict:
    """Check Gmail connection status."""
    token_doc = await db.gmail_tokens.find_one({"user_id": user_id}, {"_id": 0})
    if not token_doc:
        return {"connected": False}

    return {
        "connected": True,
        "email": token_doc.get("email", "unknown"),
        "connected_at": token_doc.get("connected_at"),
    }


def get_gmail_service(creds: Credentials):
    """Build Gmail API service."""
    return build("gmail", "v1", credentials=creds)


async def list_emails(db, user_id: str = "default", query: str = "", max_results: int = 10) -> list[dict]:
    """List emails from Gmail inbox."""
    creds = await get_credentials(db, user_id)
    if not creds:
        return [{"error": "Gmail not connected. Please connect via the dashboard."}]

    service = get_gmail_service(creds)

    try:
        result = service.users().messages().list(
            userId="me",
            q=query or "in:inbox",
            maxResults=min(max_results, 20),
        ).execute()

        messages = result.get("messages", [])
        emails = []

        for msg_stub in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_stub["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "thread_id": msg.get("threadId"),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "labels": msg.get("labelIds", []),
                "unread": "UNREAD" in msg.get("labelIds", []),
            })

        return emails

    except Exception as e:
        logger.exception("Failed to list emails")
        return [{"error": f"Gmail API error: {str(e)}"}]


async def read_email(db, message_id: str, user_id: str = "default") -> dict:
    """Read a specific email by ID."""
    creds = await get_credentials(db, user_id)
    if not creds:
        return {"error": "Gmail not connected."}

    service = get_gmail_service(creds)

    try:
        msg = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Extract body text
        body = _extract_body(msg.get("payload", {}))

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "body": body[:5000],
            "labels": msg.get("labelIds", []),
        }

    except Exception as e:
        logger.exception("Failed to read email")
        return {"error": f"Gmail API error: {str(e)}"}


def _extract_body(payload: dict) -> str:
    """Extract plain text body from email payload."""
    import base64

    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Recurse into multipart
        if part.get("parts"):
            result = _extract_body(part)
            if result:
                return result

    # Fallback to HTML if no plain text
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            # Strip HTML tags roughly
            import re
            return re.sub(r"<[^>]+>", "", html)[:5000]

    return ""


async def send_email(db, to: str, subject: str, body: str, user_id: str = "default") -> dict:
    """Send an email via Gmail."""
    creds = await get_credentials(db, user_id)
    if not creds:
        return {"error": "Gmail not connected."}

    service = get_gmail_service(creds)

    import base64
    from email.mime.text import MIMEText

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        sent = service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()

        return {
            "ok": True,
            "message_id": sent.get("id"),
            "thread_id": sent.get("threadId"),
        }

    except Exception as e:
        logger.exception("Failed to send email")
        return {"error": f"Gmail send error: {str(e)}"}
