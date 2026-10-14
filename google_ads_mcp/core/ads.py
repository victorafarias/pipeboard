"""Ad tools for Google Ads (Responsive Search Ads and App ads)."""

import re
from typing import List, Optional, Sequence, Tuple

from .api import google_api_tool, get_client, run_gaql, McpToolError
from .server import mcp_server
from .utils import normalize_customer_id

_ASSET_RESOURCE_RE = re.compile(r"^customers/\d+/assets/\d+$")
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_URL_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^#&]*&)?v=|embed/|shorts/|v/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)
_APP_AD_STATUSES = {"ENABLED", "PAUSED"}
_HEADLINE_LIMIT = 30
_DESCRIPTION_LIMIT = 90


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

    Responsive search ads include responsive_search_ad headlines and
    descriptions. App ads include app_ad headlines, descriptions, images,
    and youtube_videos.

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
          ad_group_ad.ad.app_ad.headlines,
          ad_group_ad.ad.app_ad.descriptions,
          ad_group_ad.ad.app_ad.images,
          ad_group_ad.ad.app_ad.youtube_videos,
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


def _validate_app_ad_texts(
    values,
    *,
    singular: str,
    plural: str,
    max_chars: int,
) -> List[str]:
    if not isinstance(values, (list, tuple)):
        raise McpToolError(f"{plural} must be a list of 1 to 5 strings")
    count = len(values)
    if count < 1 or count > 5:
        raise McpToolError(f"App ads require 1-5 {plural} (got {count})")
    cleaned: List[str] = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str):
            raise McpToolError(f"{singular} {index} must be a string")
        text = value.strip()
        if not text:
            raise McpToolError(f"{singular} {index} is empty")
        if len(text) > max_chars:
            raise McpToolError(
                f"{singular} {index} is {len(text)} characters; "
                f"each {singular.lower()} must be {max_chars} characters or fewer"
            )
        cleaned.append(text)
    return cleaned


def _validate_asset_resource_names(values, *, label: str) -> List[str]:
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise McpToolError(f"{label} must be a list of asset resource names")
    cleaned: List[str] = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str) or not value.strip():
            raise McpToolError(f"{label} {index} must be a non-empty string")
        resource_name = value.strip()
        if not _ASSET_RESOURCE_RE.match(resource_name):
            raise McpToolError(
                f"{label} {index} must be an asset resource name like "
                f"customers/1234567890/assets/9876543210. Got: {value!r}"
            )
        cleaned.append(resource_name)
    return cleaned


def _classify_youtube_video(value, index: int) -> Tuple[str, str]:
    """Return ('asset', resource_name) or ('id', youtube_video_id)."""
    if not isinstance(value, str) or not value.strip():
        raise McpToolError(f"YouTube video {index} must be a non-empty string")
    text = value.strip()
    if _ASSET_RESOURCE_RE.match(text):
        return ("asset", text)
    if _YOUTUBE_ID_RE.match(text):
        return ("id", text)
    match = _YOUTUBE_URL_ID_RE.search(text)
    if match:
        return ("id", match.group(1))
    raise McpToolError(
        f"YouTube video {index} must be an 11-character video id, a YouTube URL, "
        "or an asset resource name (customers/CUSTOMER_ID/assets/ASSET_ID). "
        f"Got: {value!r}"
    )


def _asset_resource_name_from_row(row) -> str:
    if not isinstance(row, dict):
        return ""
    asset = row.get("asset")
    if isinstance(asset, dict) and asset.get("resource_name"):
        return str(asset["resource_name"])
    if row.get("resource_name"):
        return str(row["resource_name"])
    return ""


def _existing_youtube_asset_resource_name(
    customer_id: str, video_id: str, access_token: Optional[str]
) -> str:
    query = (
        "SELECT asset.resource_name "
        "FROM asset "
        "WHERE asset.type = YOUTUBE_VIDEO "
        f"AND asset.youtube_video_asset.youtube_video_id = '{video_id}' "
        "LIMIT 1"
    )
    rows = run_gaql(customer_id, query, access_token)
    for row in rows:
        resource_name = _asset_resource_name_from_row(row)
        if resource_name:
            return resource_name
    return ""


def _create_youtube_video_asset(
    client, customer_id: str, video_id: str, name: Optional[str] = None
) -> str:
    asset_service = client.get_service("AssetService")
    operation = client.get_type("AssetOperation")
    asset = operation.create
    asset.type_ = client.enums.AssetTypeEnum.YOUTUBE_VIDEO
    asset.youtube_video_asset.youtube_video_id = video_id
    asset.name = (name or "").strip() or f"YouTube video {video_id}"
    request = client.get_type("MutateAssetsRequest")
    request.customer_id = customer_id
    request.operations.append(operation)
    response = asset_service.mutate_assets(request=request)
    results = getattr(response, "results", None) or []
    if not results or not getattr(results[0], "resource_name", ""):
        raise McpToolError(f"Failed to create a YOUTUBE_VIDEO asset for video id {video_id}")
    return results[0].resource_name


def _resolve_youtube_videos(
    client,
    customer_id: str,
    classified: Sequence[Tuple[str, str]],
    access_token: Optional[str],
) -> List[dict]:
    """Turn video ids into asset resource names. Existing assets are reused."""
    resolved: List[dict] = []
    created_in_call = {}
    for kind, value in classified:
        if kind == "asset":
            resolved.append(
                {"resource_name": value, "created": False, "youtube_video_id": None}
            )
            continue
        video_id = value
        if video_id in created_in_call:
            resolved.append(
                {
                    "resource_name": created_in_call[video_id],
                    "created": False,
                    "youtube_video_id": video_id,
                }
            )
            continue
        existing = _existing_youtube_asset_resource_name(customer_id, video_id, access_token)
        if existing:
            created_in_call[video_id] = existing
            resolved.append(
                {
                    "resource_name": existing,
                    "created": False,
                    "youtube_video_id": video_id,
                }
            )
            continue
        resource_name = _create_youtube_video_asset(client, customer_id, video_id)
        created_in_call[video_id] = resource_name
        resolved.append(
            {
                "resource_name": resource_name,
                "created": True,
                "youtube_video_id": video_id,
            }
        )
    return resolved


def _require_customer_id(customer_id: str) -> str:
    if not customer_id or not str(customer_id).strip():
        raise McpToolError("customer_id is required")
    cid = normalize_customer_id(customer_id)
    if not cid:
        raise McpToolError("customer_id is required")
    return cid


@mcp_server.tool()
@google_api_tool
async def create_youtube_video_asset(
    customer_id: str,
    video: str,
    name: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Create or reuse a YOUTUBE_VIDEO asset and return its resource name.

    video is an 11-character YouTube id or a youtube.com / youtu.be / shorts
    URL. If this customer already has a YOUTUBE_VIDEO asset for that id, that
    asset is returned and name is ignored. Otherwise a new asset is created.
    name is optional and defaults to "YouTube video {id}".

    Args:
        customer_id: Google Ads customer ID
        video: YouTube video id or URL
        name: Optional asset name when a new asset is created
    """
    kind, video_id = _classify_youtube_video(video, 1)
    if kind != "id":
        raise McpToolError(
            "video must be an 11-character YouTube id or a youtube.com, "
            "youtu.be, or shorts URL. Pass an asset resource name to "
            "update_app_ad_videos instead."
        )
    asset_name = (name or "").strip() if isinstance(name, str) else ""
    if asset_name and len(asset_name) > 255:
        raise McpToolError("name must be 255 characters or fewer")
    cid = _require_customer_id(customer_id)
    existing = _existing_youtube_asset_resource_name(cid, video_id, access_token)
    created = False
    if existing:
        resource_name = existing
    else:
        client = get_client(access_token)
        resource_name = _create_youtube_video_asset(
            client, cid, video_id, asset_name or None
        )
        created = True
    return {
        "customer_id": cid,
        "asset_resource_name": resource_name,
        "asset_id": resource_name.rsplit("/", 1)[-1],
        "youtube_video_id": video_id,
        "created": created,
        "name": asset_name or f"YouTube video {video_id}" if created else None,
    }


def _ad_id_from_resource_name(resource_name: str) -> Optional[str]:
    if not resource_name or "~" not in resource_name:
        return None
    ad_id = resource_name.rsplit("~", 1)[-1]
    return ad_id or None


def _append_text_assets(client, repeated_field, texts: Sequence[str]) -> None:
    for text in texts:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        repeated_field.append(asset)


def _append_asset_links(client, repeated_field, type_name: str, resource_names: Sequence[str]) -> None:
    for resource_name in resource_names:
        asset = client.get_type(type_name)
        asset.asset = resource_name
        repeated_field.append(asset)


@mcp_server.tool()
@google_api_tool
async def create_app_ad(
    customer_id: str,
    ad_group_id: str,
    headlines: List[str],
    descriptions: List[str],
    image_asset_resource_names: Optional[List[str]] = None,
    youtube_videos: Optional[List[str]] = None,
    html5_media_bundles: Optional[List[str]] = None,
    status: str = "PAUSED",
    validate_only: bool = False,
    access_token: Optional[str] = None,
) -> dict:
    """Create an App ad in an existing ad group of an App campaign.

    The ad is an AdGroupAd whose ad.app_ad (AppAdInfo) holds the assets.
    Use it on a MULTI_CHANNEL campaign with subtype APP_CAMPAIGN. App ads
    do not take a final URL; the store listing comes from the campaign.
    New ads start PAUSED unless status is ENABLED.

    Args:
        customer_id: Google Ads customer ID
        ad_group_id: Parent ad group ID
        headlines: 1-5 headlines, each 30 characters or fewer
        descriptions: 1-5 descriptions, each 90 characters or fewer
        image_asset_resource_names: Optional image asset resource names
            (customers/{id}/assets/{id})
        youtube_videos: Optional YouTube video ids, YouTube URLs, or existing
            YOUTUBE_VIDEO asset resource names. An 11-character id (or a
            youtube.com / youtu.be URL) is resolved to an asset: a
            YOUTUBE_VIDEO asset with that id is reused when one already
            exists, otherwise AssetService creates one. Asset resource names
            are attached as-is and are not created.
        html5_media_bundles: Optional HTML5 media-bundle asset resource names
        status: PAUSED (default) or ENABLED
        validate_only: When true, AdGroupAdService.MutateAdGroupAds is called
            with validate_only and no ad is created. YouTube video assets are
            still created when a video id is given, because the ad has to
            reference a real asset resource name. Created asset names are
            returned.
    """
    headline_texts = _validate_app_ad_texts(
        headlines,
        singular="Headline",
        plural="headlines",
        max_chars=_HEADLINE_LIMIT,
    )
    description_texts = _validate_app_ad_texts(
        descriptions,
        singular="Description",
        plural="descriptions",
        max_chars=_DESCRIPTION_LIMIT,
    )
    status_value = (status or "PAUSED").upper()
    if status_value not in _APP_AD_STATUSES:
        raise McpToolError("status must be ENABLED or PAUSED")
    images = _validate_asset_resource_names(
        image_asset_resource_names, label="Image asset"
    )
    html5_assets = _validate_asset_resource_names(
        html5_media_bundles, label="HTML5 media bundle"
    )
    if youtube_videos is None:
        classified_videos: List[Tuple[str, str]] = []
    elif not isinstance(youtube_videos, (list, tuple)):
        raise McpToolError(
            "youtube_videos must be a list of video ids, YouTube URLs, or asset resource names"
        )
    else:
        classified_videos = [
            _classify_youtube_video(value, index)
            for index, value in enumerate(youtube_videos, start=1)
        ]
    if not customer_id or not str(customer_id).strip():
        raise McpToolError("customer_id is required")
    cid = normalize_customer_id(customer_id)
    if not cid:
        raise McpToolError("customer_id is required")
    ad_group_id = str(ad_group_id).strip() if ad_group_id is not None else ""
    if not ad_group_id:
        raise McpToolError("ad_group_id is required")

    client = get_client(access_token)
    youtube_video_assets = _resolve_youtube_videos(
        client, cid, classified_videos, access_token
    )

    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_service = client.get_service("AdGroupService")
    operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = operation.create
    ad_group_ad.ad_group = ad_group_service.ad_group_path(cid, ad_group_id)
    ad_group_ad.status = getattr(client.enums.AdGroupAdStatusEnum, status_value)
    app_ad = ad_group_ad.ad.app_ad
    _append_text_assets(client, app_ad.headlines, headline_texts)
    _append_text_assets(client, app_ad.descriptions, description_texts)
    _append_asset_links(client, app_ad.images, "AdImageAsset", images)
    _append_asset_links(
        client,
        app_ad.youtube_videos,
        "AdVideoAsset",
        [item["resource_name"] for item in youtube_video_assets],
    )
    _append_asset_links(
        client, app_ad.html5_media_bundles, "AdMediaBundleAsset", html5_assets
    )

    request = client.get_type("MutateAdGroupAdsRequest")
    request.customer_id = cid
    request.operations.append(operation)
    request.validate_only = bool(validate_only)
    response = ad_group_ad_service.mutate_ad_group_ads(request=request)

    results = getattr(response, "results", None) or []
    resource_name = ""
    if results:
        resource_name = getattr(results[0], "resource_name", "") or ""
    if not validate_only and not resource_name:
        raise McpToolError("App ad mutate returned no ad resource name")

    if validate_only:
        message = "Validation succeeded. No App ad was created."
        if any(item["created"] for item in youtube_video_assets):
            message += (
                " YouTube video assets were still created so the ad could reference them."
            )
    else:
        message = "App ad created. It starts PAUSED unless you passed status=ENABLED."

    return {
        "customer_id": cid,
        "ad_group_id": ad_group_id,
        "ad_resource_name": resource_name or None,
        "ad_id": _ad_id_from_resource_name(resource_name),
        "status": status_value,
        "validate_only": bool(validate_only),
        "youtube_video_assets": youtube_video_assets,
        "message": message,
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
