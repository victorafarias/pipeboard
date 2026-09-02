"""Insights / reporting tools for TikTok Ads."""

from typing import List, Optional
import json
from datetime import date, timedelta

from .api import tiktok_api_tool, make_api_request
from .server import mcp_server

DEFAULT_METRICS = [
    "spend",
    "impressions",
    "clicks",
    "ctr",
    "cpc",
    "cpm",
    "conversion",
    "cost_per_conversion",
]

DATA_LEVELS = {
    "campaign": "AUCTION_CAMPAIGN",
    "adgroup": "AUCTION_ADGROUP",
    "ad": "AUCTION_AD",
    "AUCTION_CAMPAIGN": "AUCTION_CAMPAIGN",
    "AUCTION_ADGROUP": "AUCTION_ADGROUP",
    "AUCTION_AD": "AUCTION_AD",
}


@mcp_server.tool()
@tiktok_api_tool
async def get_tiktok_insights(
    advertiser_id: str,
    data_level: str = "campaign",
    start_date: str = "",
    end_date: str = "",
    metrics: Optional[List[str]] = None,
    page: int = 1,
    page_size: int = 100,
    access_token: Optional[str] = None,
) -> dict:
    """Get TikTok performance metrics with date range and breakdowns.

    Args:
        advertiser_id: TikTok advertiser ID
        data_level: campaign, adgroup, or ad (default campaign)
        start_date: YYYY-MM-DD (default 7 days ago)
        end_date: YYYY-MM-DD (default today)
        metrics: Optional metric list. Defaults to spend/impressions/clicks/conversions.
        page: Page number
        page_size: Page size
    """
    level = DATA_LEVELS.get((data_level or "campaign"), "AUCTION_CAMPAIGN")
    if not end_date:
        end_date = date.today().isoformat()
    if not start_date:
        start_date = (date.today() - timedelta(days=7)).isoformat()
    dimension_map = {
        "AUCTION_CAMPAIGN": ["campaign_id"],
        "AUCTION_ADGROUP": ["adgroup_id"],
        "AUCTION_AD": ["ad_id"],
    }
    params = {
        "advertiser_id": str(advertiser_id),
        "report_type": "BASIC",
        "data_level": level,
        "dimensions": json.dumps(dimension_map[level]),
        "metrics": json.dumps(metrics or DEFAULT_METRICS),
        "start_date": start_date,
        "end_date": end_date,
        "page": page,
        "page_size": min(int(page_size), 1000),
    }
    return await make_api_request("GET", "report/integrated/get/", access_token, params=params)
