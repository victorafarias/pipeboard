"""Ad tools for TikTok Ads."""

from typing import List, Optional

from .api import tiktok_api_tool, make_api_request, McpToolError
from .server import mcp_server

AD_FORMATS = {"SINGLE_VIDEO", "SINGLE_IMAGE", "CAROUSEL"}


async def _default_identity(advertiser_id: str, access_token: str) -> dict:
    payload = await make_api_request(
        "GET",
        "identity/get/",
        access_token,
        params={"advertiser_id": str(advertiser_id)},
    )
    identities = ((payload.get("data") or {}).get("identity_list")) or []
    if not identities:
        return {}
    first = identities[0]
    return {
        "identity_id": first.get("identity_id"),
        "identity_type": first.get("identity_type") or "CUSTOMIZED_USER",
    }


@mcp_server.tool()
@tiktok_api_tool
async def get_tiktok_ads(
    advertiser_id: str,
    campaign_id: str = "",
    adgroup_id: str = "",
    page: int = 1,
    page_size: int = 20,
    access_token: Optional[str] = None,
) -> dict:
    """List TikTok ads with creative details and status.

    Args:
        advertiser_id: TikTok advertiser ID
        campaign_id: Optional campaign ID filter
        adgroup_id: Optional ad group ID filter
        page: Page number
        page_size: Page size
    """
    import json

    params = {
        "advertiser_id": str(advertiser_id),
        "page": page,
        "page_size": min(int(page_size), 1000),
    }
    filtering = {}
    if campaign_id:
        filtering["campaign_ids"] = [str(campaign_id)]
    if adgroup_id:
        filtering["adgroup_ids"] = [str(adgroup_id)]
    if filtering:
        params["filtering"] = json.dumps(filtering)
    return await make_api_request("GET", "ad/get/", access_token, params=params)


@mcp_server.tool()
@tiktok_api_tool
async def create_tiktok_ad(
    advertiser_id: str,
    adgroup_id: str,
    ad_name: str,
    ad_format: str,
    ad_text: str,
    landing_page_url: str,
    call_to_action: str = "LEARN_MORE",
    video_id: str = "",
    image_ids: Optional[List[str]] = None,
    identity_id: str = "",
    identity_type: str = "",
    operation_status: str = "DISABLE",
    access_token: Optional[str] = None,
) -> dict:
    """Create a TikTok video, image, or carousel ad. Starts DISABLE (paused) unless overridden.

    Args:
        advertiser_id: TikTok advertiser ID
        adgroup_id: Parent ad group ID
        ad_name: Ad name
        ad_format: SINGLE_VIDEO, SINGLE_IMAGE, or CAROUSEL
        ad_text: Ad copy
        landing_page_url: Destination URL
        call_to_action: LEARN_MORE, SHOP_NOW, SIGN_UP, DOWNLOAD, etc.
        video_id: Required for SINGLE_VIDEO (from upload_tiktok_video)
        image_ids: Required for SINGLE_IMAGE (1 id) or CAROUSEL (2-10 ids)
        identity_id: Optional identity; first available identity is used if omitted
        identity_type: Optional identity type
        operation_status: DISABLE (paused, default) or ENABLE
    """
    fmt = (ad_format or "").upper()
    if fmt not in AD_FORMATS:
        raise McpToolError(f"ad_format must be one of {sorted(AD_FORMATS)}")
    creative = {
        "ad_name": ad_name,
        "ad_format": fmt,
        "ad_text": ad_text,
        "call_to_action": call_to_action,
        "landing_page_url": landing_page_url,
        "operation_status": (operation_status or "DISABLE").upper(),
    }
    if fmt == "SINGLE_VIDEO":
        if not video_id:
            raise McpToolError("video_id is required for SINGLE_VIDEO")
        creative["video_id"] = video_id
    elif fmt == "SINGLE_IMAGE":
        if not image_ids:
            raise McpToolError("image_ids is required for SINGLE_IMAGE")
        creative["image_ids"] = [str(x) for x in image_ids]
    elif fmt == "CAROUSEL":
        if not image_ids or len(image_ids) < 2:
            raise McpToolError("CAROUSEL requires 2-10 image_ids")
        creative["image_ids"] = [str(x) for x in image_ids]
        creative["ad_format"] = "CAROUSEL"
    if identity_id:
        creative["identity_id"] = identity_id
        creative["identity_type"] = identity_type or "CUSTOMIZED_USER"
    else:
        identity = await _default_identity(str(advertiser_id), access_token)
        if identity.get("identity_id"):
            creative.update(identity)
    body = {
        "advertiser_id": str(advertiser_id),
        "adgroup_id": str(adgroup_id),
        "creatives": [creative],
    }
    result = await make_api_request("POST", "ad/create/", access_token, json_body=body)
    if isinstance(result, dict) and "error" not in result:
        result["message"] = "Ad created. It starts DISABLE (paused) unless you passed operation_status=ENABLE."
    return result


@mcp_server.tool()
@tiktok_api_tool
async def update_tiktok_ad(
    advertiser_id: str,
    ad_id: str,
    ad_name: Optional[str] = None,
    ad_text: Optional[str] = None,
    call_to_action: Optional[str] = None,
    landing_page_url: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Update TikTok ad copy, CTA, or landing page.

    Args:
        advertiser_id: TikTok advertiser ID
        ad_id: Ad ID
        ad_name: Optional new name
        ad_text: Optional new copy
        call_to_action: Optional new CTA
        landing_page_url: Optional new URL
    """
    creative = {"ad_id": str(ad_id)}
    if ad_name is not None:
        creative["ad_name"] = ad_name
    if ad_text is not None:
        creative["ad_text"] = ad_text
    if call_to_action is not None:
        creative["call_to_action"] = call_to_action
    if landing_page_url is not None:
        creative["landing_page_url"] = landing_page_url
    if len(creative) == 1:
        raise McpToolError("Provide at least one field to update")
    body = {
        "advertiser_id": str(advertiser_id),
        "creatives": [creative],
    }
    return await make_api_request("POST", "ad/update/", access_token, json_body=body)


@mcp_server.tool()
@tiktok_api_tool
async def update_tiktok_ad_status(
    advertiser_id: str,
    ad_id: str,
    operation_status: str,
    access_token: Optional[str] = None,
) -> dict:
    """Enable, disable, or delete TikTok ads.

    Args:
        advertiser_id: TikTok advertiser ID
        ad_id: Ad ID (or comma-separated IDs)
        operation_status: ENABLE, DISABLE, or DELETE
    """
    status = (operation_status or "").upper()
    if status not in {"ENABLE", "DISABLE", "DELETE"}:
        raise McpToolError("operation_status must be ENABLE, DISABLE, or DELETE")
    ids = [part.strip() for part in str(ad_id).split(",") if part.strip()]
    body = {
        "advertiser_id": str(advertiser_id),
        "ad_ids": ids,
        "operation_status": status,
    }
    return await make_api_request("POST", "ad/status/update/", access_token, json_body=body)
