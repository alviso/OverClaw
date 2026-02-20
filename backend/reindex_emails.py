"""One-time: re-index sent emails into RAG (with embeddings) and extract people."""
import asyncio
import os
import sys
import base64
import re
import datetime
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway.email_memory import store_email_memory, _parse_email_addresses


def extract_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        if part.get("parts"):
            result = extract_body(part)
            if result:
                return result
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", "", html)[:5000]
    return ""


async def main():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client["test_database"]

    # Verify embedding works
    from gateway.memory import MemoryManager
    mgr = MemoryManager(db)
    try:
        test_emb = await mgr.embed_text("test")
        print(f"Embedding OK (vector dim: {len(test_emb)})")
    except Exception as e:
        print(f"ERROR: Embedding failed: {e}")
        return

    doc = await db.gmail_tokens.find_one({"user_id": "default"})
    if not doc:
        print("No Gmail token found")
        return

    user_email = doc.get("email", "")
    print(f"User: {user_email}")

    creds = Credentials(
        token=doc["access_token"],
        refresh_token=doc.get("refresh_token"),
        token_uri=doc.get("token_uri"),
        client_id=doc.get("client_id"),
        client_secret=doc.get("client_secret"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        await db.gmail_tokens.update_one(
            {"user_id": "default"}, {"$set": {"access_token": creds.token}},
        )

    service = build("gmail", "v1", credentials=creds)

    three_weeks_ago = (datetime.datetime.now() - datetime.timedelta(weeks=3)).strftime("%Y/%m/%d")
    query = f"in:sent after:{three_weeks_ago}"

    results = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    messages = results.get("messages", [])
    while results.get("nextPageToken"):
        results = service.users().messages().list(
            userId="me", q=query, maxResults=100, pageToken=results["nextPageToken"],
        ).execute()
        messages.extend(results.get("messages", []))

    print(f"Found {len(messages)} sent emails\n")

    for i, msg_ref in enumerate(messages):
        msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = extract_body(msg.get("payload", {}))

        email_data = {
            "id": msg["id"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "cc": headers.get("Cc", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "body": body[:5000],
            "labels": msg.get("labelIds", []),
        }

        print(f"[{i+1}/{len(messages)}] {email_data['subject'][:60]}")
        await store_email_memory(db, email_data, source="email/gmail")
        # Wait for background tasks to complete
        await asyncio.sleep(1.5)

    # Final stats
    mem_count = await db.memories.count_documents({"source": "email/gmail"})
    rel_count = await db.relationships.count_documents({})
    print(f"\nDone! Email memories in RAG: {mem_count}, People: {rel_count}")


if __name__ == "__main__":
    asyncio.run(main())
