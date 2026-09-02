"""Campaign tools for TikTok Ads."""

from typing import Optional

from .api import tiktok_api_tool, make_api_request, McpToolError
from .server import mcp_server

CAMPAIGN_OBJECTIVES = {
    "TRAFFIC",
    "CONVERSIONS",
    "APP_INSTALL",
    "REACH",
    "VIDEO_VIEWS",
    "LEAD_GENERATION",
    "CATALOG_SALES",
    "COMMUNITY_INTERACTION",
}


@mcp_server.tool()
@tiktok_api_tool
async def get_tiktok_campaigns(
    advertiser_id: str,
    status_filter: str = "",
    page: int = 1,
    page_size: int = 20,
    access_token: Optional[str] = None,
) -> dict:
    """List TikTok campaigns with optional status filtering.

    Args:
        advertiser_id: TikTok advertiser ID
        status_filter: Optional CAMPAIGN_STATUS_ENABLE, CAMPAIGN_STATUS_DISABLE, or operation_status ENABLE/DISABLE
        page: Page number (default 1)
        page_size: Page size (default 20)
    """
    params = {
        "advertiser_id": str(advertiser_id),
        "page": page,
        "page_size": min(int(page_size), 1000),
    }
    if status_filter:
        import json

        status = status_filter.upper()
        if status in ("ENABLE", "DISABLE", "DELETE"):
            params["filtering"] = json.dumps({"operation_status": status})
        else:
            params["filtering"] = json.dumps({"primary_status": status})
    return await make_api_request("GET", "campaign/get/", access_token, params=params)


@mcp_server.tool()
@tiktok_api_tool
async def create_tiktok_campaign(
    advertiser_id: str,
    campaign_name: str,
    objective_type: str,
    budget: Optional[float] = None,
    budget_mode: str = "BUDGET_MODE_DAY",
    operation_status: str = "DISABLE",
    access_token: Optional[str] = None,
) -> dict:
    """Create a TikTok campaign. New campaigns start DISABLE (paused) unless overridden.

    Args:
        advertiser_id: TikTok advertiser ID
        campaign_name: Campaign name
        objective_type: TRAFFIC, CONVERSIONS, APP_INSTALL, REACH, VIDEO_VIEWS, LEAD_GENERATION, CATALOG_SALES, COMMUNITY_INTERACTION
        budget: Daily or lifetime budget in account currency (required unless BUDGET_MODE_INFINITE)
        budget_mode: BUDGET_MODE_DAY (default), BUDGET_MODE_TOTAL, BUDGET_MODE_INFINITE
        operation_status: DISABLE (paused, default) or ENABLE
    """
    objective = (objective_type or "").upper()
    if objective not in CAMPAIGN_OBJECTIVES:
        raise McpToolError(
            f"Unsupported objective_type '{objective_type}'. Use one of: {sorted(CAMPAIGN_OBJECTIVES)}"
        )
    body = {
        "advertiser_id": str(advertiser_id),
        "campaign_name": campaign_name,
        "objective_type": objective,
        "budget_mode": budget_mode,
        "operation_status": (operation_status or "DISABLE").upper(),
    }
    if budget is not None:
        body["budget"] = float(budget)
    result = await make_api_request("POST", "campaign/create/", access_token, json_body=body)
    if isinstance(result, dict) and "error" not in result:
        result["message"] = "Campaign created. It starts DISABLE (paused) unless you passed operation_status=ENABLE."
    return result


@mcp_server.tool()
@tiktok_api_tool
async def update_tiktok_campaign(
    advertiser_id: str,
    campaign_id: str,
    campaign_name: Optional[str] = None,
    budget: Optional[float] = None,
    budget_mode: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Update a TikTok campaign name or budget.

    Args:
        advertiser_id: TikTok advertiser ID
        campaign_id: Campaign ID
        campaign_name: Optional new name
        budget: Optional new budget
        budget_mode: Optional budget mode
    """
    if campaign_name is None and budget is None and budget_mode is None:
        raise McpToolError("Provide at least one of campaign_name, budget, or budget_mode")
    body = {
        "advertiser_id": str(advertiser_id),
        "campaign_id": str(campaign_id),
    }
    if campaign_name is not None:
        body["campaign_name"] = campaign_name
    if budget is not None:
        body["budget"] = float(budget)
    if budget_mode is not None:
        body["budget_mode"] = budget_mode
    return await make_api_request("POST", "campaign/update/", access_token, json_body=body)


@mcp_server.tool()
@tiktok_api_tool
async def update_tiktok_campaign_status(
    advertiser_id: str,
    campaign_id: str,
    operation_status: str,
    access_token: Optional[str] = None,
) -> dict:
    """Enable, disable, or delete TikTok campaigns.

    Args:
        advertiser_id: TikTok advertiser ID
        campaign_id: Campaign ID (or comma-separated IDs)
        operation_status: ENABLE, DISABLE, or DELETE
    """
    status = (operation_status or "").upper()
    if status not in {"ENABLE", "DISABLE", "DELETE"}:
        raise McpToolError("operation_status must be ENABLE, DISABLE, or DELETE")
    ids = [part.strip() for part in str(campaign_id).split(",") if part.strip()]
    body = {
        "advertiser_id": str(advertiser_id),
        "campaign_ids": ids,
        "operation_status": status,
    }
    return await make_api_request("POST", "campaign/status/update/", access_token, json_body=body)
