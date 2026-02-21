"""
Setup / Onboarding — first-run configuration wizard.
Stores API keys and secrets in MongoDB so they persist across container restarts.

Secret precedence (per field):
  1. Real (non-placeholder) .env value  →  always wins
  2. DB-stored value                    →  fills in when .env is empty/placeholder
  3. Nothing                            →  field is unset

GATEWAY_TOKEN is special: .env is ALWAYS the single source of truth.
DB values for gateway_token are ignored during load to prevent silent auth overrides.
"""
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.setup")

_PLACEHOLDER_PATTERNS = [
    "sk-your-", "your-", "change-me", "xxx", "placeholder", "example",
    "put-your", "insert-your", "add-your",
]

# Fields that must NEVER be overridden by DB values at startup.
# These are security-sensitive; the .env / docker-compose is the source of truth.
_ENV_ONLY_FIELDS = {"gateway_token"}

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
        "required": False,
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
    "azure_client_id": {
        "env_var": "AZURE_CLIENT_ID",
        "required": False,
        "label": "Azure Client ID",
    },
    "azure_client_secret": {
        "env_var": "AZURE_CLIENT_SECRET",
        "required": False,
        "label": "Azure Client Secret",
    },
    "azure_tenant_id": {
        "env_var": "AZURE_TENANT_ID",
        "required": False,
        "label": "Azure Tenant ID",
    },
}


def _is_placeholder(value: str) -> bool:
    if not value:
        return True
    lower = value.lower().strip()
    return any(p in lower for p in _PLACEHOLDER_PATTERNS)


def _mask_key(value: str) -> str:
    if not value or len(value) < 12:
        return "****"
    return value[:4] + "****" + value[-4:]


async def get_setup_status(db) -> dict:
    """Check which keys are configured (from DB or env)."""
    stored = await db.setup_secrets.find_one({"_id": "main"}, {"_id": 0}) or {}

    fields = {}
    has_any_llm = False

    for field_id, field_def in SETUP_FIELDS.items():
        db_value = stored.get(field_id, "")
        env_value = os.environ.get(field_def["env_var"], "")

        # For env-only fields, ignore DB values in status display
        if field_id in _ENV_ONLY_FIELDS:
            effective = env_value
            source = "environment" if (effective and not _is_placeholder(effective)) else "none"
        else:
            effective = db_value or env_value
            source = (
                "database" if db_value and not _is_placeholder(db_value)
                else ("environment" if env_value and not _is_placeholder(env_value) else "none")
            )

        is_set = bool(effective) and not _is_placeholder(effective)

        fields[field_id] = {
            "label": field_def["label"],
            "is_set": is_set,
            "source": source,
            "masked_value": _mask_key(effective) if is_set else "",
            "required": field_def["required"],
        }

        if field_id in ("openai_api_key", "anthropic_api_key") and is_set:
            has_any_llm = True

    return {
        "needs_setup": not has_any_llm,
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
    """Resolve an API key: check env first (if real), then DB, then empty."""
    field_id = None
    for fid, fdef in SETUP_FIELDS.items():
        if fdef["env_var"] == env_var:
            field_id = fid
            break

    # Env always wins if it has a real value
    env_value = os.environ.get(env_var, "")
    if env_value and not _is_placeholder(env_value):
        return env_value

    # For env-only fields, stop here
    if field_id and field_id in _ENV_ONLY_FIELDS:
        return ""

    # Fall back to DB
    if field_id:
        stored = await db.setup_secrets.find_one({"_id": "main"}, {"_id": 0})
        if stored:
            db_value = stored.get(field_id, "")
            if db_value and not _is_placeholder(db_value):
                return db_value

    return ""


async def load_secrets_to_env(db):
    """
    On startup, load DB-stored secrets into os.environ.
    Only fills in keys that are currently empty or placeholder in the environment.
    Skips _ENV_ONLY_FIELDS (e.g. gateway_token) to prevent silent auth overrides.
    """
    stored = await db.setup_secrets.find_one({"_id": "main"}, {"_id": 0})
    if not stored:
        return

    loaded = []
    skipped = []
    for field_id, field_def in SETUP_FIELDS.items():
        db_value = stored.get(field_id, "")
        if not db_value or _is_placeholder(db_value):
            continue

        # Never override env-only fields from DB
        if field_id in _ENV_ONLY_FIELDS:
            skipped.append(field_id)
            continue

        current_env = os.environ.get(field_def["env_var"], "")
        if current_env and not _is_placeholder(current_env):
            continue  # env already has a real value

        os.environ[field_def["env_var"]] = db_value
        loaded.append(field_id)

    if loaded:
        logger.info(f"Loaded {len(loaded)} secret(s) from DB: {loaded}")
    if skipped:
        logger.info(f"Skipped env-only field(s) from DB (not overriding): {skipped}")
