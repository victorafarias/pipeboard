"""Performance metrics tools for Google Ads."""

from typing import Optional

from .api import google_api_tool, run_gaql
from .server import mcp_server
from .utils import normalize_customer_id


@mcp_server.tool()
@google_api_tool
async def get_campaign_metrics(
    customer_id: str,
    campaign_id: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
    access_token: Optional[str] = None,
) -> dict:
    """Get campaign performance metrics.

    Args:
        customer_id: Google Ads customer ID
        campaign_id: Optional campaign ID (omit for all campaigns)
        date_from: YYYY-MM-DD. If both dates empty, uses LAST_30_DAYS.
        date_to: YYYY-MM-DD
        limit: Max campaigns (default 50)
    """
    cid = normalize_customer_id(customer_id)
    clauses = []
    if campaign_id:
        clauses.append(f"campaign.id = {int(campaign_id)}")
    if date_from and date_to:
        clauses.append(f"segments.date BETWEEN '{date_from}' AND '{date_to}'")
        date_select = "segments.date,"
    else:
        clauses.append("segments.date DURING LAST_30_DAYS")
        date_select = "segments.date,"
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT
          {date_select}
          campaign.id,
          campaign.name,
          campaign.status,
          metrics.impressions,
          metrics.clicks,
          metrics.ctr,
          metrics.average_cpc,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value,
          metrics.cost_per_conversion
        FROM campaign
        {where}
        ORDER BY metrics.cost_micros DESC
        LIMIT {int(limit)}
    """
    rows = run_gaql(cid, query, access_token)
    return {"customer_id": cid, "count": len(rows), "metrics": rows}
