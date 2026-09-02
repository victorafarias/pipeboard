"""Ad tools for Google Ads (Responsive Search Ads)."""

from typing import List, Optional

from .api import google_api_tool, get_client, run_gaql, McpToolError
from .server import mcp_server
from .utils import normalize_customer_id


@mcp_server.tool()
@google_api_tool
async def get_ads(
    customer_id: str,
    campaign_id: str = "",
    ad_group_id: str = "",
    status_filter: str = "",
    limit: int = 50,
    access_token: Optional[str] = None,
) -> dict:
    """List ads for a customer, optionally filtered by campaign or ad group.

    Args:
        customer_id: Google Ads customer ID
        campaign_id: Optional campaign ID filter
        ad_group_id: Optional ad group ID filter
        status_filter: Optional ENABLED, PAUSED, or REMOVED
        limit: Max rows (default 50)
    """
    cid = normalize_customer_id(customer_id)
    clauses = []
    if campaign_id:
        clauses.append(f"campaign.id = {int(campaign_id)}")
    if ad_group_id:
        clauses.append(f"ad_group.id = {int(ad_group_id)}")
    if status_filter:
        clauses.append(f"ad_group_ad.status = '{status_filter.upper()}'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT
          ad_group_ad.ad.id,
          ad_group_ad.status,
          ad_group_ad.ad.type,
          ad_group_ad.ad.final_urls,
          ad_group_ad.ad.responsive_search_ad.headlines,
          ad_group_ad.ad.responsive_search_ad.descriptions,
          ad_group.id,
          campaign.id
        FROM ad_group_ad
        {where}
        ORDER BY ad_group_ad.ad.id
        LIMIT {int(limit)}
    """
    rows = run_gaql(cid, query, access_token)
    return {"customer_id": cid, "count": len(rows), "ads": rows}


@mcp_server.tool()
@google_api_tool
async def create_responsive_search_ad(
    customer_id: str,
    ad_group_id: str,
    headlines: List[str],
    descriptions: List[str],
    final_url: str,
    status: str = "PAUSED",
    path1: str = "",
    path2: str = "",
    access_token: Optional[str] = None,
) -> dict:
    """Create a Responsive Search Ad. New ads start PAUSED unless status is overridden.

    Args:
        customer_id: Google Ads customer ID
        ad_group_id: Parent ad group ID
        headlines: 3-15 headlines (max 30 chars each)
        descriptions: 2-4 descriptions (max 90 chars each)
        final_url: Landing page URL
        status: PAUSED (default) or ENABLED
        path1: Optional display-path segment
        path2: Optional second display-path segment
    """
    if not headlines or len(headlines) < 3:
        raise McpToolError("Responsive Search Ads require at least 3 headlines")
    if not descriptions or len(descriptions) < 2:
        raise McpToolError("Responsive Search Ads require at least 2 descriptions")
    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_service = client.get_service("AdGroupService")
    operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = operation.create
    ad_group_ad.ad_group = ad_group_service.ad_group_path(cid, ad_group_id)
    ad_group_ad.status = getattr(client.enums.AdGroupAdStatusEnum, (status or "PAUSED").upper())
    ad = ad_group_ad.ad
    ad.final_urls.append(final_url)
    for text in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ad.responsive_search_ad.headlines.append(asset)
    for text in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ad.responsive_search_ad.descriptions.append(asset)
    if path1:
        ad.responsive_search_ad.path1 = path1
    if path2:
        ad.responsive_search_ad.path2 = path2
    response = ad_group_ad_service.mutate_ad_group_ads(customer_id=cid, operations=[operation])
    resource_name = response.results[0].resource_name
    return {
        "customer_id": cid,
        "ad_resource_name": resource_name,
        "status": (status or "PAUSED").upper(),
        "message": "RSA created. It starts PAUSED unless you passed status=ENABLED.",
    }


async def _set_ad_status(customer_id: str, ad_group_id: str, ad_id: str, status: str, access_token: Optional[str]):
    from google.protobuf.field_mask_pb2 import FieldMask

    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    service = client.get_service("AdGroupAdService")
    operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = operation.update
    ad_group_ad.resource_name = service.ad_group_ad_path(cid, ad_group_id, ad_id)
    ad_group_ad.status = getattr(client.enums.AdGroupAdStatusEnum, status.upper())
    operation.update_mask.CopyFrom(FieldMask(paths=["status"]))
    service.mutate_ad_group_ads(customer_id=cid, operations=[operation])
    return {"customer_id": cid, "ad_id": str(ad_id), "ad_group_id": str(ad_group_id), "status": status.upper()}


@mcp_server.tool()
@google_api_tool
async def enable_ad(
    customer_id: str,
    ad_group_id: str,
    ad_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Enable a paused ad.

    Args:
        customer_id: Google Ads customer ID
        ad_group_id: Ad group ID that contains the ad
        ad_id: Ad ID
    """
    return await _set_ad_status(customer_id, ad_group_id, ad_id, "ENABLED", access_token)


@mcp_server.tool()
@google_api_tool
async def pause_ad(
    customer_id: str,
    ad_group_id: str,
    ad_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Pause an ad.

    Args:
        customer_id: Google Ads customer ID
        ad_group_id: Ad group ID that contains the ad
        ad_id: Ad ID
    """
    return await _set_ad_status(customer_id, ad_group_id, ad_id, "PAUSED", access_token)
