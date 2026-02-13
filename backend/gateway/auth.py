"""
Token-based authentication for Gateway HTTP and WebSocket.
Inspired by OpenClaw's auth.ts.
"""
import os
import hmac


def get_gateway_token() -> str:
    """Get the gateway auth token from environment."""
    return os.environ.get("GATEWAY_TOKEN", "")


def verify_token(provided: str) -> bool:
    """Constant-time token comparison to prevent timing attacks."""
    expected = get_gateway_token()
    if not expected:
        return True  # No token configured = open access (dev mode)
    return hmac.compare_digest(provided, expected)


def extract_token_from_header(authorization: str) -> str:
    """Extract bearer token from Authorization header."""
    if not authorization:
        return ""
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()
