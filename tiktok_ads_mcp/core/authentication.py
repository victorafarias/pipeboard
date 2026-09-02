"""Login-link tool for TikTok Ads OAuth."""

import json
import os
from typing import Optional

from .auth import auth_manager, is_configured
from .server import mcp_server
from .utils import logger

ENABLE_LOGIN_LINK = not bool(os.environ.get("TIKTOK_ADS_DISABLE_LOGIN_LINK", ""))


async def get_login_link(access_token: Optional[str] = None) -> str:
    """Get a clickable login link for TikTok Ads authentication.

    On a VPS without a local browser, set TIKTOK_ACCESS_TOKEN / TIKTOK_REFRESH_TOKEN instead.
    """
    if is_configured(access_token):
        return json.dumps(
            {
                "message": "Already Authenticated",
                "status": "TikTok Ads credentials are configured.",
                "ready_to_use": True,
            },
            indent=2,
        )

    missing = []
    for key in ("TIKTOK_APP_ID", "TIKTOK_APP_SECRET"):
        if not os.environ.get(key):
            missing.append(key)

    callback_disabled = bool(os.environ.get("TIKTOK_ADS_DISABLE_CALLBACK_SERVER", ""))
    if callback_disabled or missing:
        return json.dumps(
            {
                "message": "Authentication Required",
                "missing_env": missing,
                "how": [
                    "Create a TikTok Marketing API app and authorize an advertiser.",
                    "Generate tokens locally (`python -m tiktok_ads_mcp --login`).",
                    "Set TIKTOK_ACCESS_TOKEN and TIKTOK_REFRESH_TOKEN on the VPS.",
                ],
            },
            indent=2,
        )

    try:
        from .callback_server import start_callback_server

        port = start_callback_server()
        auth_manager.redirect_uri = f"http://localhost:{port}/callback"
        login_url = auth_manager.get_auth_url()
        logger.info(f"TikTok Ads login URL: {login_url}")
        return json.dumps(
            {
                "message": "Click to Authenticate",
                "login_url": login_url,
                "markdown_link": f"[Authenticate with TikTok Ads]({login_url})",
                "instructions": "Click the link, grant access, then retry the tool.",
                "server_info": f"Local callback server running on port {port}",
            },
            indent=2,
        )
    except Exception as e:
        logger.error(f"Failed to start TikTok OAuth callback server: {e}")
        return json.dumps(
            {
                "message": "Local Authentication Unavailable",
                "error": str(e),
                "how": "Set TIKTOK_ACCESS_TOKEN on the server instead.",
            },
            indent=2,
        )


if ENABLE_LOGIN_LINK:
    get_login_link = mcp_server.tool()(get_login_link)
