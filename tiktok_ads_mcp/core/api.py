"""TikTok Marketing API REST client and tool decorator."""

from typing import Any, Callable, Dict, Optional
import functools
import json
import os

import httpx

from . import auth
from .auth import is_configured
from .utils import logger

TIKTOK_API_BASE = os.environ.get(
    "TIKTOK_API_BASE", "https://business-api.tiktok.com/open_api/v1.3"
)
USER_AGENT = "tiktok-ads-mcp/1.0"


class McpToolError(Exception):
    pass


def auth_required_payload() -> str:
    return json.dumps(
        {
            "error": {
                "message": "Authentication Required",
                "details": {
                    "description": "TikTok Ads credentials are missing.",
                    "required_env": [
                        "TIKTOK_APP_ID",
                        "TIKTOK_APP_SECRET",
                        "TIKTOK_ACCESS_TOKEN or TIKTOK_REFRESH_TOKEN",
                    ],
                    "http": "Pass the access token as Authorization: Bearer <token> or ?token=",
                    "action_required": "Call get_login_link or set TIKTOK_ACCESS_TOKEN",
                },
            }
        },
        indent=2,
    )


async def make_api_request(
    method: str,
    path: str,
    access_token: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{TIKTOK_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    if not url.endswith("/") and "?" not in path:
        url = url + "/"
    headers = {
        "Access-Token": access_token,
        "User-Agent": USER_AGENT,
    }
    if files is None:
        headers["Content-Type"] = "application/json"
    timeout = httpx.Timeout(60.0)
    form_data = None
    if files is not None and json_body:
        form_data = {}
        for key, value in json_body.items():
            if isinstance(value, (dict, list)):
                form_data[key] = json.dumps(value)
            elif isinstance(value, bool):
                form_data[key] = "true" if value else "false"
            else:
                form_data[key] = str(value)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            json=json_body if files is None else None,
            files=files,
            data=form_data,
        )
    try:
        payload = response.json()
    except Exception:
        payload = {"code": response.status_code, "message": response.text}
    if response.status_code >= 400:
        logger.error(f"TikTok HTTP {response.status_code}: {payload}")
        return {"error": payload, "http_status": response.status_code}
    # TikTok uses code == 0 for success
    if isinstance(payload, dict) and payload.get("code") not in (0, None):
        logger.error(f"TikTok API error: {payload}")
        return {"error": payload}
    return payload


def tiktok_api_tool(func: Callable):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            if not kwargs.get("access_token"):
                token = await auth.get_current_access_token()
                if token:
                    kwargs["access_token"] = token
            if not kwargs.get("access_token") and not is_configured():
                logger.warning("TikTok Ads is not configured")
                return auth_required_payload()
            if not kwargs.get("access_token"):
                return auth_required_payload()
            result = await func(*args, **kwargs)
            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            if isinstance(result, str):
                return result
            return json.dumps({"data": result}, indent=2)
        except McpToolError as e:
            return json.dumps({"error": {"message": str(e)}}, indent=2)
        except Exception as e:
            logger.error(f"TikTok tool error in {func.__name__}: {e}", exc_info=True)
            return json.dumps({"error": {"message": str(e)}}, indent=2)

    return wrapper
