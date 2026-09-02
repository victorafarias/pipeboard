"""Keyword tools for Google Ads."""

from typing import List, Optional

from .api import google_api_tool, get_client, run_gaql, McpToolError
from .server import mcp_server
from .utils import currency_to_micros, normalize_customer_id

MATCH_TYPES = {"EXACT", "PHRASE", "BROAD"}


def _match_enum(client, match_type: str):
    mt = (match_type or "BROAD").upper()
    if mt not in MATCH_TYPES:
        raise McpToolError(f"Unsupported match_type '{match_type}'. Use EXACT, PHRASE, or BROAD.")
    return getattr(client.enums.KeywordMatchTypeEnum, mt)


@mcp_server.tool()
@google_api_tool
async def get_keywords(
    customer_id: str,
    ad_group_id: str = "",
    campaign_id: str = "",
    limit: int = 100,
    access_token: Optional[str] = None,
) -> dict:
    """List keywords (ad group criteria of type KEYWORD).

    Args:
        customer_id: Google Ads customer ID
        ad_group_id: Optional ad group ID filter
        campaign_id: Optional campaign ID filter
        limit: Max rows (default 100)
    """
    cid = normalize_customer_id(customer_id)
    clauses = ["ad_group_criterion.type = KEYWORD"]
    if ad_group_id:
        clauses.append(f"ad_group.id = {int(ad_group_id)}")
    if campaign_id:
        clauses.append(f"campaign.id = {int(campaign_id)}")
    query = f"""
        SELECT
          ad_group_criterion.criterion_id,
          ad_group_criterion.keyword.text,
          ad_group_criterion.keyword.match_type,
          ad_group_criterion.status,
          ad_group_criterion.cpc_bid_micros,
          ad_group_criterion.quality_info.quality_score,
          ad_group.id,
          campaign.id
        FROM ad_group_criterion
        WHERE {' AND '.join(clauses)}
        ORDER BY ad_group_criterion.criterion_id
        LIMIT {int(limit)}
    """
    rows = run_gaql(cid, query, access_token)
    return {"customer_id": cid, "count": len(rows), "keywords": rows}


@mcp_server.tool()
@google_api_tool
async def add_keywords(
    customer_id: str,
    ad_group_id: str,
    keywords: List[str],
    match_type: str = "BROAD",
    cpc_bid: Optional[float] = None,
    status: str = "PAUSED",
    access_token: Optional[str] = None,
) -> dict:
    """Add keywords to an ad group. New keywords start PAUSED unless status is overridden.

    Args:
        customer_id: Google Ads customer ID
        ad_group_id: Ad group ID
        keywords: List of keyword texts
        match_type: EXACT, PHRASE, or BROAD (default BROAD)
        cpc_bid: Optional CPC bid in account currency
        status: PAUSED (default) or ENABLED
    """
    if not keywords:
        raise McpToolError("keywords must be a non-empty list")
    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    service = client.get_service("AdGroupCriterionService")
    ad_group_service = client.get_service("AdGroupService")
    match_enum = _match_enum(client, match_type)
    operations = []
    for text in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        criterion = op.create
        criterion.ad_group = ad_group_service.ad_group_path(cid, ad_group_id)
        criterion.status = getattr(
            client.enums.AdGroupCriterionStatusEnum, (status or "PAUSED").upper()
        )
        criterion.keyword.text = text
        criterion.keyword.match_type = match_enum
        if cpc_bid is not None:
            criterion.cpc_bid_micros = currency_to_micros(cpc_bid)
        operations.append(op)
    response = service.mutate_ad_group_criteria(customer_id=cid, operations=operations)
    return {
        "customer_id": cid,
        "ad_group_id": str(ad_group_id),
        "created": [r.resource_name for r in response.results],
        "status": (status or "PAUSED").upper(),
    }


@mcp_server.tool()
@google_api_tool
async def add_negative_keywords(
    customer_id: str,
    keywords: List[str],
    campaign_id: str = "",
    ad_group_id: str = "",
    match_type: str = "BROAD",
    access_token: Optional[str] = None,
) -> dict:
    """Add negative keywords at campaign or ad-group level.

    Args:
        customer_id: Google Ads customer ID
        keywords: List of negative keyword texts
        campaign_id: Campaign ID (campaign-level negatives)
        ad_group_id: Ad group ID (ad-group-level negatives). Provide one of campaign_id or ad_group_id.
        match_type: EXACT, PHRASE, or BROAD (default BROAD)
    """
    if not keywords:
        raise McpToolError("keywords must be a non-empty list")
    if not campaign_id and not ad_group_id:
        raise McpToolError("Provide campaign_id or ad_group_id")
    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    match_enum = _match_enum(client, match_type)
    created = []
    if ad_group_id:
        service = client.get_service("AdGroupCriterionService")
        ad_group_service = client.get_service("AdGroupService")
        operations = []
        for text in keywords:
            op = client.get_type("AdGroupCriterionOperation")
            criterion = op.create
            criterion.ad_group = ad_group_service.ad_group_path(cid, ad_group_id)
            criterion.negative = True
            criterion.keyword.text = text
            criterion.keyword.match_type = match_enum
            operations.append(op)
        response = service.mutate_ad_group_criteria(customer_id=cid, operations=operations)
        created = [r.resource_name for r in response.results]
    else:
        service = client.get_service("CampaignCriterionService")
        campaign_service = client.get_service("CampaignService")
        operations = []
        for text in keywords:
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = campaign_service.campaign_path(cid, campaign_id)
            criterion.negative = True
            criterion.keyword.text = text
            criterion.keyword.match_type = match_enum
            operations.append(op)
        response = service.mutate_campaign_criteria(customer_id=cid, operations=operations)
        created = [r.resource_name for r in response.results]
    return {
        "customer_id": cid,
        "campaign_id": campaign_id or None,
        "ad_group_id": ad_group_id or None,
        "created": created,
    }


@mcp_server.tool()
@google_api_tool
async def get_search_terms_report(
    customer_id: str,
    campaign_id: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    access_token: Optional[str] = None,
) -> dict:
    """Pull the search terms report (queries that triggered ads).

    Args:
        customer_id: Google Ads customer ID
        campaign_id: Optional campaign ID filter
        date_from: YYYY-MM-DD (default last 30 days via DURING LAST_30_DAYS if both empty)
        date_to: YYYY-MM-DD
        limit: Max rows (default 100)
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
          search_term_view.search_term,
          search_term_view.status,
          campaign.id,
          ad_group.id,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions
        FROM search_term_view
        {where}
        ORDER BY metrics.impressions DESC
        LIMIT {int(limit)}
    """
    rows = run_gaql(cid, query, access_token)
    return {"customer_id": cid, "count": len(rows), "search_terms": rows}
