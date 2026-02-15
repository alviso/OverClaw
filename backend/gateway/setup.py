"""
Setup / Onboarding — first-run configuration wizard.
Stores API keys and secrets in MongoDB so they persist across container restarts.
Keys in MongoDB take priority over .env values (unless .env has a real key).
"""
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.setup")

# Keys that look like placeholders (not real keys)
_PLACEHOLDER_PATTERNS = [
    "sk-your-", "your-", "change-me", "xxx", "placeholder", "example",
    "put-your", "insert-your", "add-your",
]

# The secrets we manage
SETUP_FIELDS = {
    "openai_api_key": {
        "env_var": "OPENAI_API_KEY",
        "required": False,
        "label": "OpenAI API Key",
    },
    "anthropic_api_key": {
        "env_var": "ANTHROPIC_API_KEY",
        "required": False,
        "label": "Anthropic API Key",
    },
    "gateway_token": {
        "env_var": "GATEWAY_TOKEN",
        "required": True,
        "label": "Gateway Token",
    },
    "google_client_id": {
        "env_var": "GOOGLE_CLIENT_ID",
        "required": False,
        "label": "Google Client ID",
    },
    "google_client_secret": {
        "env_var": "GOOGLE_CLIENT_SECRET",
        "required": False,
        "label": "Google Client Secret",
    },
    "slack_bot_token": {
        "env_var": "SLACK_BOT_TOKEN",
        "required": False,
        "label": "Slack Bot Token",
    },
    "slack_app_token": {
        "env_var": "SLACK_APP_TOKEN",
        "required": False,
        "label": "Slack App Token",
    },
}


def _is_placeholder(value: str) -> bool:
    """Check if a value looks like a placeholder rather than a real key."""
    if not value:
        return True
    lower = value.lower().strip()
    return any(p in lower for p in _PLACEHOLDER_PATTERNS)


def _mask_key(value: str) -> str:
    """Mask a key for display: show first 4 and last 4 chars."""
    if not value or len(value) < 12:
        return "****"
    return value[:4] + "****" + value[-4:]


async def get_setup_status(db) -> dict:
    """Check which keys are configured (from DB or env)."""
    stored = await db.setup_secrets.find_one({"_id": "main"}, {"_id": 0}) or {}

    fields = {}
    has_any_llm = False
    needs_setup = False

    for field_id, field_def in SETUP_FIELDS.items():
        # DB value takes priority
        db_value = stored.get(field_id, "")
        env_value = os.environ.get(field_def["env_var"], "")

        effective = db_value or env_value
        is_set = bool(effective) and not _is_placeholder(effective)

        fields[field_id] = {
            "label": field_def["label"],
            "is_set": is_set,
            "source": "database" if db_value and not _is_placeholder(db_value) else ("environment" if is_set else "none"),
            "masked_value": _mask_key(effective) if is_set else "",
            "required": field_def["required"],
        }

        if field_id in ("openai_api_key", "anthropic_api_key") and is_set:
            has_any_llm = True

    # Setup is needed if: no LLM key at all, or gateway token is placeholder
    if not has_any_llm:
        needs_setup = True
    gateway_set = fields.get("gateway_token", {}).get("is_set", False)
    if not gateway_set:
        needs_setup = True

    return {
        "needs_setup": needs_setup,
        "has_any_llm": has_any_llm,
        "fields": fields,
    }


async def save_setup(db, data: dict) -> dict:
    """Save setup secrets to MongoDB and update os.environ for immediate effect."""
    now = datetime.now(timezone.utc).isoformat()
    update_fields = {"updated_at": now}
    applied = []

    for field_id, field_def in SETUP_FIELDS.items():
        value = data.get(field_id, "").strip()
        if not value:
            continue

        update_fields[field_id] = value
        # Also update the running process's env so keys take effect immediately
        os.environ[field_def["env_var"]] = value
        applied.append(field_id)

    if not applied:
        return {"ok": False, "error": "No values provided"}

    await db.setup_secrets.update_one(
        {"_id": "main"},
        {"$set": update_fields},
        upsert=True,
    )

    logger.info(f"Setup saved: {applied}")
    return {"ok": True, "applied": applied}


async def resolve_api_key(db, env_var: str) -> str:
    """Resolve an API key: check MongoDB first, then fall back to env var."""
    # Map env_var back to field_id
    field_id = None
    for fid, fdef in SETUP_FIELDS.items():
        if fdef["env_var"] == env_var:
            field_id = fid
            break

    if field_id:
        stored = await db.setup_secrets.find_one({"_id": "main"}, {"_id": 0})
        if stored:
            db_value = stored.get(field_id, "")
            if db_value and not _is_placeholder(db_value):
                return db_value

    env_value = os.environ.get(env_var, "")
    if env_value and not _is_placeholder(env_value):
        return env_value

    return ""


async def load_secrets_to_env(db):
    """On startup, load any DB-stored secrets into os.environ."""
    stored = await db.setup_secrets.find_one({"_id": "main"}, {"_id": 0})
    if not stored:
        return

    count = 0
    for field_id, field_def in SETUP_FIELDS.items():
        db_value = stored.get(field_id, "")
        if db_value and not _is_placeholder(db_value):
            current_env = os.environ.get(field_def["env_var"], "")
            if not current_env or _is_placeholder(current_env):
                os.environ[field_def["env_var"]] = db_value
                count += 1

    if count:
        logger.info(f"Loaded {count} secret(s) from database into environment")
