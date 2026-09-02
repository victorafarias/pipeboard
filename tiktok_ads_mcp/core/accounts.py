"""Advertiser account tools for TikTok Ads."""

from typing import Optional
import json
import os

from .api import tiktok_api_tool, make_api_request
from .server import mcp_server


@mcp_server.tool()
@tiktok_api_tool
async def list_tiktok_advertisers(access_token: Optional[str] = None) -> dict:
    """List TikTok advertiser accounts authorized for the current access token."""
    app_id = os.environ.get("TIKTOK_APP_ID", "")
    secret = os.environ.get("TIKTOK_APP_SECRET", "")
    params = {}
    if app_id:
        params["app_id"] = app_id
    if secret:
        params["secret"] = secret
    return await make_api_request(
        "GET",
        "oauth2/advertiser/get/",
        access_token,
        params=params or None,
    )


@mcp_server.tool()
@tiktok_api_tool
async def get_tiktok_advertiser_info(
    advertiser_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Get details, currency, and balance for a TikTok advertiser account.

    Args:
        advertiser_id: TikTok advertiser ID
    """
    return await make_api_request(
        "GET",
        "advertiser/info/",
        access_token,
        params={"advertiser_ids": json.dumps([str(advertiser_id)])},
    )
