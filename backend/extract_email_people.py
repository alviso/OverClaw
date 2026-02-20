"""One-time script to extract people from the last 3 weeks of sent emails."""
import asyncio
import os
import sys
import base64
import re
import datetime
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

from motor.motor_asyncio import AsyncIOMotorClient
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

# Add parent to path for gateway imports
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
            {"user_id": "default"},
            {"$set": {"access_token": creds.token}},
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

    people_found = {}
    for i, msg_ref in enumerate(messages):
        msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = extract_body(msg.get("payload", {}))

        email_data = {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "cc": headers.get("Cc", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "body": body[:5000],
            "labels": msg.get("labelIds", []),
        }

        to_addrs = _parse_email_addresses(email_data["to"])
        cc_addrs = _parse_email_addresses(email_data.get("cc", ""))
        all_contacts = [c for c in to_addrs + cc_addrs if c["email"] != user_email.lower()]

        for c in all_contacts:
            if c["email"] not in people_found:
                people_found[c["email"]] = c["name"]

        print(f"[{i+1}/{len(messages)}] {email_data['subject'][:60]}")
        if all_contacts:
            print(f"        -> {', '.join(c['name'] for c in all_contacts)}")

        # Run the full extraction pipeline
        await store_email_memory(db, email_data, source="email/gmail")

        # Small delay to avoid overwhelming things
        await asyncio.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"Done! Processed {len(messages)} sent emails")
    print(f"Unique contacts found: {len(people_found)}")
    for email_addr, name in sorted(people_found.items()):
        print(f"  {name:30s} {email_addr}")

    # Show updated relationships count
    count = await db.relationships.count_documents({})
    print(f"\nTotal people in relationships collection: {count}")


if __name__ == "__main__":
    asyncio.run(main())
