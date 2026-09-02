"""Ad group tools for Google Ads."""

from typing import Optional

from google.protobuf.field_mask_pb2 import FieldMask

from .api import google_api_tool, get_client, run_gaql, McpToolError
from .server import mcp_server
from .utils import currency_to_micros, normalize_customer_id


@mcp_server.tool()
@google_api_tool
async def get_ad_groups(
    customer_id: str,
    campaign_id: str = "",
    status_filter: str = "",
    limit: int = 50,
    access_token: Optional[str] = None,
) -> dict:
    """List ad groups for a customer, optionally filtered by campaign.

    Args:
        customer_id: Google Ads customer ID
        campaign_id: Optional campaign ID filter
        status_filter: Optional ENABLED, PAUSED, or REMOVED
        limit: Max rows (default 50)
    """
    cid = normalize_customer_id(customer_id)
    clauses = []
    if campaign_id:
        clauses.append(f"campaign.id = {int(campaign_id)}")
    if status_filter:
        clauses.append(f"ad_group.status = '{status_filter.upper()}'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT
          ad_group.id,
          ad_group.name,
          ad_group.status,
          ad_group.type,
          ad_group.cpc_bid_micros,
          campaign.id,
          campaign.name
        FROM ad_group
        {where}
        ORDER BY ad_group.id
        LIMIT {int(limit)}
    """
    rows = run_gaql(cid, query, access_token)
    return {"customer_id": cid, "count": len(rows), "ad_groups": rows}


@mcp_server.tool()
@google_api_tool
async def create_ad_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid: Optional[float] = None,
    status: str = "PAUSED",
    access_token: Optional[str] = None,
) -> dict:
    """Create an ad group. New ad groups start PAUSED unless status is overridden.

    Args:
        customer_id: Google Ads customer ID
        campaign_id: Parent campaign ID
        name: Ad group name
        cpc_bid: Optional CPC bid in account currency
        status: PAUSED (default) or ENABLED
    """
    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    ad_group_service = client.get_service("AdGroupService")
    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("AdGroupOperation")
    ad_group = operation.create
    ad_group.name = name
    ad_group.campaign = campaign_service.campaign_path(cid, campaign_id)
    ad_group.status = getattr(client.enums.AdGroupStatusEnum, (status or "PAUSED").upper())
    ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    if cpc_bid is not None:
        ad_group.cpc_bid_micros = currency_to_micros(cpc_bid)
    response = ad_group_service.mutate_ad_groups(customer_id=cid, operations=[operation])
    resource_name = response.results[0].resource_name
    return {
        "customer_id": cid,
        "ad_group_resource_name": resource_name,
        "ad_group_id": resource_name.split("/")[-1],
        "status": (status or "PAUSED").upper(),
        "message": "Ad group created. It starts PAUSED unless you passed status=ENABLED.",
    }


@mcp_server.tool()
@google_api_tool
async def update_ad_group(
    customer_id: str,
    ad_group_id: str,
    name: Optional[str] = None,
    status: Optional[str] = None,
    cpc_bid: Optional[float] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Update an ad group name, status, or CPC bid.

    Args:
        customer_id: Google Ads customer ID
        ad_group_id: Ad group ID
        name: Optional new name
        status: Optional ENABLED, PAUSED, or REMOVED
        cpc_bid: Optional CPC bid in account currency
    """
    if name is None and status is None and cpc_bid is None:
        raise McpToolError("Provide at least one of name, status, or cpc_bid")
    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    ad_group_service = client.get_service("AdGroupService")
    operation = client.get_type("AdGroupOperation")
    ad_group = operation.update
    ad_group.resource_name = ad_group_service.ad_group_path(cid, ad_group_id)
    paths = []
    updated = {}
    if name is not None:
        ad_group.name = name
        paths.append("name")
        updated["name"] = name
    if status is not None:
        ad_group.status = getattr(client.enums.AdGroupStatusEnum, status.upper())
        paths.append("status")
        updated["status"] = status.upper()
    if cpc_bid is not None:
        ad_group.cpc_bid_micros = currency_to_micros(cpc_bid)
        paths.append("cpc_bid_micros")
        updated["cpc_bid"] = cpc_bid
    operation.update_mask.CopyFrom(FieldMask(paths=paths))
    ad_group_service.mutate_ad_groups(customer_id=cid, operations=[operation])
    return {"customer_id": cid, "ad_group_id": str(ad_group_id), "updated": updated}
