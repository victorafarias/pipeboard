"""Authentication tool for Meta Posts MCP."""

import json
import os
from typing import Optional

from meta_ads_mcp.core.auth import auth_manager, start_callback_server
from meta_ads_mcp.core import auth as ads_auth

from .server import mcp_server
from .utils import POSTS_AUTH_SCOPE, logger

ENABLE_LOGIN_LINK = not bool(os.environ.get("META_ADS_DISABLE_LOGIN_LINK", ""))


def _posts_auth_url() -> str:
    original = ads_auth.AUTH_SCOPE
    ads_auth.AUTH_SCOPE = POSTS_AUTH_SCOPE
    try:
        return auth_manager.get_auth_url()
    finally:
        ads_auth.AUTH_SCOPE = original


async def get_login_link(access_token: Optional[str] = None) -> str:
    """Get a login link that requests Facebook/Instagram publishing permissions.

    Requires your own Meta app (META_APP_ID). The token must include
    pages_manage_posts and instagram_content_publish — ads-only tokens will
    fail when creating posts.

    Args:
        access_token: Meta API access token (optional)

    Example:
        get_login_link()
    """
    callback_server_disabled = bool(os.environ.get("META_ADS_DISABLE_CALLBACK_SERVER", ""))

    required = [
        "pages_show_list",
        "pages_manage_posts",
        "instagram_basic",
        "instagram_content_publish",
    ]

    if callback_server_disabled:
        logger.info("Callback server disabled — cannot run the local OAuth flow")
        return json.dumps(
            {
                "message": "Authentication Required",
                "reason": "The local callback server is disabled (META_ADS_DISABLE_CALLBACK_SERVER).",
                "required_permissions": required,
                "how": [
                    "Create a Meta app at https://developers.facebook.com/apps/",
                    "Generate a user token with pages_manage_posts and instagram_content_publish",
                    "Set META_ACCESS_TOKEN before starting this server",
                    "Or run locally: python -m meta_posts_mcp --login",
                ],
            },
            indent=2,
        )

    cached_token = auth_manager.get_access_token()
    if cached_token and not access_token:
        return json.dumps(
            {
                "message": "Already Authenticated",
                "status": "A Meta token is cached. Publishing still requires pages_manage_posts and instagram_content_publish on that token.",
                "required_permissions": required,
                "ready_to_use": True,
            },
            indent=2,
        )

    try:
        port = start_callback_server()
        auth_manager.redirect_uri = f"http://localhost:{port}/callback"
        login_url = _posts_auth_url()
        logger.info("Meta Posts login URL generated for port %s", port)
    except Exception as exc:
        logger.error("Failed to start callback server: %s", exc)
        return json.dumps(
            {
                "message": "Local Authentication Unavailable",
                "error": str(exc),
                "how": "Set META_ACCESS_TOKEN instead.",
                "required_permissions": required,
            },
            indent=2,
        )

    return json.dumps(
        {
            "message": "Click to Authenticate",
            "login_url": login_url,
            "markdown_link": f"[Authenticate with Meta for Page/Instagram publishing]({login_url})",
            "instructions": "Click the link, grant Page and Instagram publishing permissions, then retry.",
            "required_permissions": required,
            "server_info": f"Local callback server running on port {port}",
        },
        indent=2,
    )


if ENABLE_LOGIN_LINK:
    get_login_link = mcp_server.tool()(get_login_link)
