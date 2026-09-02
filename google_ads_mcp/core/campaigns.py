"""Campaign tools for Google Ads."""

from typing import Optional

from google.protobuf.field_mask_pb2 import FieldMask

from .api import google_api_tool, get_client, run_gaql, McpToolError
from .server import mcp_server
from .utils import currency_to_micros, normalize_customer_id

CHANNEL_TYPES = {
    "SEARCH": "SEARCH",
    "DISPLAY": "DISPLAY",
    "SHOPPING": "SHOPPING",
    "VIDEO": "VIDEO",
    "MULTI_CHANNEL": "MULTI_CHANNEL",
    "PERFORMANCE_MAX": "PERFORMANCE_MAX",
    "DEMAND_GEN": "DEMAND_GEN",
}

BIDDING_STRATEGIES = {
    "MANUAL_CPC",
    "MAXIMIZE_CONVERSIONS",
    "MAXIMIZE_CONVERSION_VALUE",
    "TARGET_CPA",
    "TARGET_ROAS",
    "TARGET_SPEND",
    "TARGET_IMPRESSION_SHARE",
}


def _set_eu_political(client, campaign) -> None:
    try:
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )
    except Exception:
        pass


def _apply_bidding(client, campaign, bidding_strategy: str, target_cpa=None, target_roas=None) -> None:
    strategy = (bidding_strategy or "MANUAL_CPC").upper()
    if strategy not in BIDDING_STRATEGIES:
        raise McpToolError(
            f"Unsupported bidding_strategy '{bidding_strategy}'. "
            f"Use one of: {sorted(BIDDING_STRATEGIES)}"
        )
    if strategy == "MANUAL_CPC":
        campaign.manual_cpc.enhanced_cpc_enabled = False
    elif strategy == "MAXIMIZE_CONVERSIONS":
        campaign.maximize_conversions.target_cpa_micros = 0
    elif strategy == "MAXIMIZE_CONVERSION_VALUE":
        campaign.maximize_conversion_value.target_roas = 0
    elif strategy == "TARGET_CPA":
        if target_cpa is None:
            raise McpToolError("target_cpa is required for TARGET_CPA bidding")
        campaign.target_cpa.target_cpa_micros = currency_to_micros(target_cpa)
    elif strategy == "TARGET_ROAS":
        if target_roas is None:
            raise McpToolError("target_roas is required for TARGET_ROAS bidding (e.g. 3.5 for 350%)")
        campaign.target_roas.target_roas = float(target_roas)
    elif strategy == "TARGET_SPEND":
        campaign.target_spend.cpc_bid_ceiling_micros = 0
    elif strategy == "TARGET_IMPRESSION_SHARE":
        campaign.target_impression_share.location = (
            client.enums.TargetImpressionShareLocationEnum.ANYWHERE_ON_PAGE
        )
        campaign.target_impression_share.location_fraction_micros = 1_000_000


@mcp_server.tool()
@google_api_tool
async def get_campaigns(
    customer_id: str,
    status_filter: str = "",
    limit: int = 50,
    access_token: Optional[str] = None,
) -> dict:
    """List campaigns for a Google Ads customer.

    Args:
        customer_id: Google Ads customer ID
        status_filter: Optional ENABLED, PAUSED, or REMOVED
        limit: Max campaigns to return (default 50)
    """
    cid = normalize_customer_id(customer_id)
    where = ""
    if status_filter:
        where = f"WHERE campaign.status = '{status_filter.upper()}'"
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign.advertising_channel_type,
          campaign_budget.amount_micros,
          campaign.bidding_strategy_type,
          campaign.start_date,
          campaign.end_date
        FROM campaign
        {where}
        ORDER BY campaign.id
        LIMIT {int(limit)}
    """
    rows = run_gaql(cid, query, access_token)
    return {"customer_id": cid, "count": len(rows), "campaigns": rows}


@mcp_server.tool()
@google_api_tool
async def create_campaign(
    customer_id: str,
    name: str,
    daily_budget: float,
    advertising_channel_type: str = "SEARCH",
    bidding_strategy: str = "MANUAL_CPC",
    status: str = "PAUSED",
    target_cpa: Optional[float] = None,
    target_roas: Optional[float] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Create a Google Ads campaign. New campaigns start PAUSED unless status is overridden.

    Args:
        customer_id: Google Ads customer ID
        name: Campaign name
        daily_budget: Daily budget in account currency (e.g. 50.0) or micros (>= 1_000_000)
        advertising_channel_type: SEARCH, DISPLAY, VIDEO, etc. (default SEARCH)
        bidding_strategy: MANUAL_CPC, MAXIMIZE_CONVERSIONS, TARGET_CPA, TARGET_ROAS, ...
        status: PAUSED (default) or ENABLED
        target_cpa: Required for TARGET_CPA (currency units)
        target_roas: Required for TARGET_ROAS (e.g. 3.5)
    """
    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    channel = (advertising_channel_type or "SEARCH").upper()
    if channel not in CHANNEL_TYPES:
        raise McpToolError(f"Unsupported advertising_channel_type '{advertising_channel_type}'")

    budget_service = client.get_service("CampaignBudgetService")
    budget_op = client.get_type("CampaignBudgetOperation")
    budget = budget_op.create
    budget.name = f"{name} Budget"
    budget.amount_micros = currency_to_micros(daily_budget)
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared = False
    budget_response = budget_service.mutate_campaign_budgets(
        customer_id=cid, operations=[budget_op]
    )
    budget_resource = budget_response.results[0].resource_name

    campaign_service = client.get_service("CampaignService")
    campaign_op = client.get_type("CampaignOperation")
    campaign = campaign_op.create
    campaign.name = name
    campaign.campaign_budget = budget_resource
    campaign.advertising_channel_type = getattr(
        client.enums.AdvertisingChannelTypeEnum, channel
    )
    campaign.status = getattr(client.enums.CampaignStatusEnum, (status or "PAUSED").upper())
    campaign.network_settings.target_google_search = True
    campaign.network_settings.target_search_network = channel == "SEARCH"
    campaign.network_settings.target_content_network = False
    _apply_bidding(client, campaign, bidding_strategy, target_cpa, target_roas)
    _set_eu_political(client, campaign)

    response = campaign_service.mutate_campaigns(customer_id=cid, operations=[campaign_op])
    resource_name = response.results[0].resource_name
    return {
        "customer_id": cid,
        "campaign_resource_name": resource_name,
        "campaign_id": resource_name.split("/")[-1],
        "budget_resource_name": budget_resource,
        "status": (status or "PAUSED").upper(),
        "message": "Campaign created. It starts PAUSED unless you passed status=ENABLED.",
    }


@mcp_server.tool()
@google_api_tool
async def update_campaign(
    customer_id: str,
    campaign_id: str,
    name: Optional[str] = None,
    daily_budget: Optional[float] = None,
    status: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Update a campaign name, status, or daily budget.

    Args:
        customer_id: Google Ads customer ID
        campaign_id: Campaign ID
        name: Optional new name
        daily_budget: Optional new daily budget (currency units or micros)
        status: Optional ENABLED, PAUSED, or REMOVED
    """
    cid = normalize_customer_id(customer_id)
    client = get_client(access_token)
    campaign_service = client.get_service("CampaignService")
    resource_name = campaign_service.campaign_path(cid, campaign_id)

    updated = {}
    if daily_budget is not None:
        rows = run_gaql(
            cid,
            f"SELECT campaign.campaign_budget FROM campaign WHERE campaign.id = {int(campaign_id)}",
            access_token,
        )
        if not rows:
            raise McpToolError(f"Campaign {campaign_id} not found")
        budget_resource = rows[0]["campaign"]["campaign_budget"]
        budget_service = client.get_service("CampaignBudgetService")
        budget_op = client.get_type("CampaignBudgetOperation")
        budget = budget_op.update
        budget.resource_name = budget_resource
        budget.amount_micros = currency_to_micros(daily_budget)
        budget_op.update_mask.CopyFrom(FieldMask(paths=["amount_micros"]))
        budget_service.mutate_campaign_budgets(customer_id=cid, operations=[budget_op])
        updated["daily_budget"] = daily_budget

    if name is not None or status is not None:
        campaign_op = client.get_type("CampaignOperation")
        campaign = campaign_op.update
        campaign.resource_name = resource_name
        paths = []
        if name is not None:
            campaign.name = name
            paths.append("name")
            updated["name"] = name
        if status is not None:
            campaign.status = getattr(client.enums.CampaignStatusEnum, status.upper())
            paths.append("status")
            updated["status"] = status.upper()
        campaign_op.update_mask.CopyFrom(FieldMask(paths=paths))
        campaign_service.mutate_campaigns(customer_id=cid, operations=[campaign_op])

    return {"customer_id": cid, "campaign_id": str(campaign_id), "updated": updated}


async def _set_campaign_status(customer_id: str, campaign_id: str, status: str, access_token: Optional[str]):
    return await update_campaign(
        customer_id=customer_id,
        campaign_id=campaign_id,
        status=status,
        access_token=access_token,
    )


@mcp_server.tool()
@google_api_tool
async def enable_campaign(
    customer_id: str, campaign_id: str, access_token: Optional[str] = None
) -> dict:
    """Enable a paused Google Ads campaign."""
    return await _set_campaign_status(customer_id, campaign_id, "ENABLED", access_token)


@mcp_server.tool()
@google_api_tool
async def pause_campaign(
    customer_id: str, campaign_id: str, access_token: Optional[str] = None
) -> dict:
    """Pause a Google Ads campaign."""
    return await _set_campaign_status(customer_id, campaign_id, "PAUSED", access_token)
