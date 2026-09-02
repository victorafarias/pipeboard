"""Ad group tools for TikTok Ads."""

from typing import List, Optional

from .api import tiktok_api_tool, make_api_request, McpToolError
from .server import mcp_server


@mcp_server.tool()
@tiktok_api_tool
async def get_tiktok_adgroups(
    advertiser_id: str,
    campaign_id: str = "",
    page: int = 1,
    page_size: int = 20,
    access_token: Optional[str] = None,
) -> dict:
    """List TikTok ad groups with targeting and budget details.

    Args:
        advertiser_id: TikTok advertiser ID
        campaign_id: Optional campaign ID filter
        page: Page number (default 1)
        page_size: Page size (default 20)
    """
    import json

    params = {
        "advertiser_id": str(advertiser_id),
        "page": page,
        "page_size": min(int(page_size), 1000),
    }
    if campaign_id:
        params["filtering"] = json.dumps({"campaign_ids": [str(campaign_id)]})
    return await make_api_request("GET", "adgroup/get/", access_token, params=params)


@mcp_server.tool()
@tiktok_api_tool
async def create_tiktok_adgroup(
    advertiser_id: str,
    campaign_id: str,
    adgroup_name: str,
    location_ids: List[str],
    budget: float,
    budget_mode: str = "BUDGET_MODE_DAY",
    optimization_goal: str = "CLICK",
    bid_type: str = "BID_TYPE_NO_BID",
    billing_event: str = "CPC",
    placement_type: str = "PLACEMENT_TYPE_AUTOMATIC",
    gender: str = "GENDER_UNLIMITED",
    operation_status: str = "DISABLE",
    schedule_type: str = "SCHEDULE_FROM_NOW",
    schedule_start_time: str = "",
    access_token: Optional[str] = None,
) -> dict:
    """Create a TikTok ad group. Starts DISABLE (paused) unless overridden.

    Args:
        advertiser_id: TikTok advertiser ID
        campaign_id: Parent campaign ID
        adgroup_name: Ad group name
        location_ids: Location IDs from get_tiktok_targeting_regions (required)
        budget: Daily/lifetime budget
        budget_mode: BUDGET_MODE_DAY (default) or BUDGET_MODE_TOTAL
        optimization_goal: CLICK, CONVERT, REACH, VIDEO_VIEW, etc.
        bid_type: BID_TYPE_NO_BID (default) or BID_TYPE_CUSTOM
        billing_event: CPC, CPM, OCPM, etc.
        placement_type: PLACEMENT_TYPE_AUTOMATIC (default) or PLACEMENT_TYPE_NORMAL
        gender: GENDER_UNLIMITED, GENDER_MALE, GENDER_FEMALE
        operation_status: DISABLE (paused, default) or ENABLE
        schedule_type: SCHEDULE_FROM_NOW or SCHEDULE_START_END
        schedule_start_time: UTC timestamp YYYY-MM-DD HH:MM:SS (required for some APIs)
    """
    if not location_ids:
        raise McpToolError("location_ids is required — use get_tiktok_targeting_regions first")
    body = {
        "advertiser_id": str(advertiser_id),
        "campaign_id": str(campaign_id),
        "adgroup_name": adgroup_name,
        "location_ids": [str(x) for x in location_ids],
        "budget": float(budget),
        "budget_mode": budget_mode,
        "optimization_goal": optimization_goal,
        "bid_type": bid_type,
        "billing_event": billing_event,
        "placement_type": placement_type,
        "gender": gender,
        "operation_status": (operation_status or "DISABLE").upper(),
        "schedule_type": schedule_type,
    }
    if schedule_start_time:
        body["schedule_start_time"] = schedule_start_time
    result = await make_api_request("POST", "adgroup/create/", access_token, json_body=body)
    if isinstance(result, dict) and "error" not in result:
        result["message"] = "Ad group created. It starts DISABLE (paused) unless you passed operation_status=ENABLE."
    return result


@mcp_server.tool()
@tiktok_api_tool
async def update_tiktok_adgroup(
    advertiser_id: str,
    adgroup_id: str,
    adgroup_name: Optional[str] = None,
    budget: Optional[float] = None,
    location_ids: Optional[List[str]] = None,
    bid_price: Optional[float] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Update a TikTok ad group name, budget, targeting, or bid.

    Args:
        advertiser_id: TikTok advertiser ID
        adgroup_id: Ad group ID
        adgroup_name: Optional new name
        budget: Optional new budget
        location_ids: Optional new location IDs
        bid_price: Optional bid
    """
    body = {
        "advertiser_id": str(advertiser_id),
        "adgroup_id": str(adgroup_id),
    }
    if adgroup_name is not None:
        body["adgroup_name"] = adgroup_name
    if budget is not None:
        body["budget"] = float(budget)
    if location_ids is not None:
        body["location_ids"] = [str(x) for x in location_ids]
    if bid_price is not None:
        body["bid_price"] = float(bid_price)
    if len(body) <= 2:
        raise McpToolError("Provide at least one field to update")
    return await make_api_request("POST", "adgroup/update/", access_token, json_body=body)


@mcp_server.tool()
@tiktok_api_tool
async def update_tiktok_adgroup_status(
    advertiser_id: str,
    adgroup_id: str,
    operation_status: str,
    access_token: Optional[str] = None,
) -> dict:
    """Enable, disable, or delete TikTok ad groups.

    Args:
        advertiser_id: TikTok advertiser ID
        adgroup_id: Ad group ID (or comma-separated IDs)
        operation_status: ENABLE, DISABLE, or DELETE
    """
    status = (operation_status or "").upper()
    if status not in {"ENABLE", "DISABLE", "DELETE"}:
        raise McpToolError("operation_status must be ENABLE, DISABLE, or DELETE")
    ids = [part.strip() for part in str(adgroup_id).split(",") if part.strip()]
    body = {
        "advertiser_id": str(advertiser_id),
        "adgroup_ids": ids,
        "operation_status": status,
    }
    return await make_api_request("POST", "adgroup/status/update/", access_token, json_body=body)
