"""
Routing — Phase 5
Maps session keys to agent IDs based on routing rules.
Inspired by OpenClaw's src/routing/resolve-route.ts (simplified from 5-level priority to pattern matching).

Session key format: "channel:target:user"
  e.g. "slack:C012345:U098765" or "webchat:main:anonymous"

Route patterns use wildcards:
  "slack:C012345:*"  → matches any user in Slack channel C012345
  "slack:*:*"        → matches all Slack messages
  "webchat:*"        → matches all WebChat sessions
  "*"                → catch-all
"""
import fnmatch
import logging
from gateway.config_schema import RouteRule

logger = logging.getLogger("gateway.routing")

DEFAULT_AGENT_ID = "default"


def resolve_agent_id(session_id: str, routes: list[RouteRule]) -> str:
    """
    Resolve which agent should handle a session based on routing rules.
    Rules are evaluated in order — first match wins.
    """
    for rule in routes:
        if fnmatch.fnmatch(session_id, rule.pattern):
            logger.debug(f"Route match: '{session_id}' -> agent '{rule.agent_id}' (pattern: '{rule.pattern}')")
            return rule.agent_id

    return DEFAULT_AGENT_ID


def build_session_key(channel: str, target: str, user: str = "*") -> str:
    """Build a session key from components."""
    return f"{channel}:{target}:{user}"
