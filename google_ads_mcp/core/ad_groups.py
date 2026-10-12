"""Ad group tools for Google Ads."""

from typing import Optional, Tuple

from google.protobuf.field_mask_pb2 import FieldMask

from .api import google_api_tool, get_client, run_gaql, McpToolError
from .server import mcp_server
from .utils import currency_to_micros, normalize_customer_id

# Numeric fallbacks match AdvertisingChannelType / AdvertisingChannelSubType.
_CHANNEL_TYPE_NUMBERS = {7: "MULTI_CHANNEL"}
_CHANNEL_SUBTYPE_NUMBERS = {
    12: "APP_CAMPAIGN",
    13: "APP_CAMPAIGN_FOR_ENGAGEMENT",
    18: "APP_CAMPAIGN_FOR_PRE_REGISTRATION",
}
_DISALLOWED_AD_GROUP_TYPES = {"UNSPECIFIED", "UNKNOWN"}


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


def _enum_token(value, number_map) -> str:
    """Normalize a GAQL enum value (name or number) to its name."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return number_map.get(value, "")
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return number_map.get(int(text), "")
    return text.split(".")[-1].upper()


def _is_app_campaign(channel_type, channel_subtype) -> bool:
    """App campaigns are MULTI_CHANNEL, usually with an APP_CAMPAIGN subtype."""
    channel = _enum_token(channel_type, _CHANNEL_TYPE_NUMBERS)
    subtype = _enum_token(channel_subtype, _CHANNEL_SUBTYPE_NUMBERS)
    if channel == "MULTI_CHANNEL":
        return True
    return subtype.startswith("APP_CAMPAIGN")


def _campaign_id_value(campaign_id) -> str:
    text = str(campaign_id).strip() if campaign_id is not None else ""
    if not text.isdigit():
        raise McpToolError("campaign_id must be a numeric campaign ID")
    return str(int(text))


def _campaign_channel(customer_id: str, campaign_id: str, access_token: Optional[str]) -> Tuple[str, str]:
    query = f"""
        SELECT
          campaign.id,
          campaign.advertising_channel_type,
          campaign.advertising_channel_sub_type
        FROM campaign
        WHERE campaign.id = {campaign_id}
        LIMIT 1
    """
    rows = run_gaql(customer_id, query, access_token)
    if not rows:
        raise McpToolError(f"Campaign {campaign_id} not found")
    row = rows[0] if isinstance(rows[0], dict) else {}
    campaign = row.get("campaign") if isinstance(row.get("campaign"), dict) else row
    if not isinstance(campaign, dict):
        raise McpToolError(f"Campaign {campaign_id} not found")
    return (
        _enum_token(campaign.get("advertising_channel_type"), _CHANNEL_TYPE_NUMBERS),
        _enum_token(campaign.get("advertising_channel_sub_type"), _CHANNEL_SUBTYPE_NUMBERS),
    )


def _resolve_ad_group_type(client, ad_group_type: Optional[str], is_app: bool):
    """Return (enum_or_none, name_or_none). App campaigns omit type unless asked."""
    requested = (ad_group_type or "").strip()
    if requested:
        name = requested.upper()
        enum_cls = client.enums.AdGroupTypeEnum
        if name in _DISALLOWED_AD_GROUP_TYPES or not hasattr(enum_cls, name):
            raise McpToolError(
                f"Unsupported ad_group_type '{ad_group_type}'. "
                "Omit it for App campaigns so the type field is left unset, "
                "or pass a supported type such as SEARCH_STANDARD."
            )
        return getattr(enum_cls, name), name
    if is_app:
        return None, None
    return client.enums.AdGroupTypeEnum.SEARCH_STANDARD, "SEARCH_STANDARD"


@mcp_server.tool()
@google_api_tool
async def create_ad_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid: Optional[float] = None,
    status: str = "PAUSED",
    ad_group_type: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Create an ad group. New ad groups start PAUSED unless status is overridden.

    Search campaigns keep SEARCH_STANDARD when ad_group_type is omitted, and
    cpc_bid is applied when provided.

    App campaigns (MULTI_CHANNEL / APP_CAMPAIGN) reject an explicit ad group
    type such as SEARCH_STANDARD with OPERATION_NOT_PERMITTED_FOR_CONTEXT.
    The type field is omitted unless ad_group_type is passed. cpc_bid does
    not apply on those ad groups and is ignored when provided.

    Args:
        customer_id: Google Ads customer ID
        campaign_id: Parent campaign ID
        name: Ad group name
        cpc_bid: Optional CPC bid in account currency. Ignored for App campaigns.
        status: PAUSED (default) or ENABLED
        ad_group_type: Optional type such as SEARCH_STANDARD. Leave empty for
            App campaigns so Google can choose the type.
    """
    cid = normalize_customer_id(customer_id)
    campaign_id_value = _campaign_id_value(campaign_id)
    channel_type, channel_subtype = _campaign_channel(cid, campaign_id_value, access_token)
    is_app = _is_app_campaign(channel_type, channel_subtype)

    client = get_client(access_token)
    type_enum, type_name = _resolve_ad_group_type(client, ad_group_type, is_app)
    status_value = (status or "PAUSED").upper()
    ad_group_service = client.get_service("AdGroupService")
    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("AdGroupOperation")
    ad_group = operation.create
    ad_group.name = name
    ad_group.campaign = campaign_service.campaign_path(cid, campaign_id_value)
    ad_group.status = getattr(client.enums.AdGroupStatusEnum, status_value)
    if type_enum is not None:
        ad_group.type_ = type_enum
    cpc_bid_skipped = False
    if cpc_bid is not None and not is_app:
        ad_group.cpc_bid_micros = currency_to_micros(cpc_bid)
    elif cpc_bid is not None and is_app:
        cpc_bid_skipped = True
    response = ad_group_service.mutate_ad_groups(customer_id=cid, operations=[operation])
    resource_name = response.results[0].resource_name
    message = "Ad group created. It starts PAUSED unless you passed status=ENABLED."
    if cpc_bid_skipped:
        message += " cpc_bid was ignored because App campaign ad groups do not use a CPC bid."
    result = {
        "customer_id": cid,
        "ad_group_resource_name": resource_name,
        "ad_group_id": resource_name.split("/")[-1],
        "status": status_value,
        "ad_group_type": type_name,
        "message": message,
    }
    if cpc_bid_skipped:
        result["cpc_bid_skipped"] = True
    return result


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
