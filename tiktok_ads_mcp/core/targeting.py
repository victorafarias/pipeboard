"""Targeting lookup tools for TikTok Ads."""

from typing import Optional
import json

from .api import tiktok_api_tool, make_api_request
from .server import mcp_server


def json_list(value: str) -> str:
    if value.startswith("["):
        return value
    return json.dumps([value])


@mcp_server.tool()
@tiktok_api_tool
async def get_tiktok_targeting_regions(
    advertiser_id: str,
    objective_type: str = "TRAFFIC",
    placements: str = "PLACEMENT_TIKTOK",
    language: str = "en",
    access_token: Optional[str] = None,
) -> dict:
    """Look up location IDs for TikTok geo targeting.

    Args:
        advertiser_id: TikTok advertiser ID
        objective_type: Campaign objective used to filter available regions
        placements: Placement (default PLACEMENT_TIKTOK)
        language: Response language (default en)
    """
    params = {
        "advertiser_id": str(advertiser_id),
        "placements": json_list(placements),
        "objective_type": objective_type,
        "language": language,
    }
    return await make_api_request("GET", "tool/region/", access_token, params=params)


@mcp_server.tool()
@tiktok_api_tool
async def get_tiktok_interest_categories(
    advertiser_id: str,
    language: str = "en",
    version: str = "2.0",
    access_token: Optional[str] = None,
) -> dict:
    """Browse interest categories for TikTok targeting.

    Args:
        advertiser_id: TikTok advertiser ID
        language: Response language (default en)
        version: Interest taxonomy version (default 2.0)
    """
    params = {
        "advertiser_id": str(advertiser_id),
        "language": language,
        "version": version,
    }
    return await make_api_request("GET", "tool/interest_category/", access_token, params=params)
