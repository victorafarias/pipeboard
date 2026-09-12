"""Shared Graph API helpers for organic Facebook/Instagram publishing."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from dateutil import parser as date_parser

from meta_ads_mcp.core.api import make_api_request

from .utils import logger

_TOKEN_KEYS = frozenset({"access_token", "page_access_token"})

_MIN_SCHEDULE_LEAD_SECONDS = 10 * 60
_MAX_SCHEDULE_LEAD_SECONDS = 75 * 24 * 60 * 60


def tool_error(message: str, **extra: Any) -> Dict[str, Any]:
    """Structured error payload for MCP tool responses."""
    payload: Dict[str, Any] = {"error": {"message": message}}
    if extra:
        payload["error"].update(extra)
    return payload


def redact_tokens(obj: Any) -> Any:
    """Strip Graph access tokens before returning data to the MCP client."""
    if isinstance(obj, dict):
        redacted = {}
        for key, value in obj.items():
            if key in _TOKEN_KEYS:
                continue
            redacted[key] = redact_tokens(value)
        return redacted
    if isinstance(obj, list):
        return [redact_tokens(item) for item in obj]
    return obj


def require_http_url(url: str, field_name: str) -> Optional[Dict[str, Any]]:
    """Return an error dict if url is missing or not http(s), else None."""
    if not url or not str(url).strip():
        return tool_error(
            f"{field_name} is required",
            example=f"{field_name}='https://example.com/image.jpg'",
        )
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return tool_error(
            f"{field_name} must be a public http(s) URL that Meta can fetch",
            received=url,
            example=f"{field_name}='https://cdn.example.com/media.jpg'",
        )
    return None


def parse_unix_time(value: Any) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Parse a unix timestamp or ISO-8601 string. Returns (unix, error)."""
    if value is None or value == "":
        return None, None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value), None
    text = str(value).strip()
    if not text:
        return None, None
    if text.isdigit():
        return int(text), None
    try:
        return int(date_parser.isoparse(text).timestamp()), None
    except (ValueError, OverflowError, TypeError) as exc:
        return None, tool_error(
            "scheduled_publish_time must be a unix timestamp or ISO-8601 datetime",
            received=value,
            example="scheduled_publish_time='2026-09-13T09:00:00-03:00'",
            details=str(exc),
        )


def validate_facebook_schedule(unix_ts: int, now: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Facebook Page scheduled posts must be 10 minutes to 75 days ahead."""
    now = int(now if now is not None else time.time())
    lead = unix_ts - now
    if lead < _MIN_SCHEDULE_LEAD_SECONDS:
        return tool_error(
            "scheduled_publish_time must be at least 10 minutes in the future",
            scheduled_publish_time=unix_ts,
        )
    if lead > _MAX_SCHEDULE_LEAD_SECONDS:
        return tool_error(
            "scheduled_publish_time must be within 75 days",
            scheduled_publish_time=unix_ts,
        )
    return None


async def graph_request(
    endpoint: str,
    access_token: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET",
) -> Dict[str, Any]:
    """Call Graph API and redact tokens in the returned payload."""
    result = await make_api_request(endpoint, access_token, params, method=method)
    if not isinstance(result, dict):
        return {"data": result}
    return redact_tokens(result)


async def resolve_page_token(page_id: str, user_token: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Return a Page access token for publishing, without exposing it.

    Falls back to the user token if the Page token cannot be fetched.
    The Page token itself is never included in the error payload.
    """
    data = await make_api_request(page_id, user_token, {"fields": "id,name,access_token"})
    if isinstance(data, dict) and "error" in data:
        logger.warning("Could not fetch Page token for %s; using user token", page_id)
        return user_token, redact_tokens(data)
    page_token = ""
    if isinstance(data, dict):
        page_token = data.get("access_token") or ""
    if page_token:
        logger.debug("Using Page access token for page %s", page_id)
        return page_token, None
    return user_token, None
