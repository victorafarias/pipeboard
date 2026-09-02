"""Verify Google and TikTok MCP tools are registered on their FastMCP servers."""

import pytest


def _tool_names(server):
    manager = getattr(server, "_tool_manager", None)
    if manager is None:
        pytest.skip("FastMCP tool manager not available")
    tools = manager.list_tools()
    return sorted(t.name for t in tools)


def test_google_ads_tools_registered():
    pytest.importorskip("google.protobuf")
    from google_ads_mcp.core.server import mcp_server
    from google_ads_mcp.core import (  # noqa: F401
        accounts,
        ad_groups,
        ads,
        authentication,
        campaigns,
        insights,
        keywords,
    )

    names = _tool_names(mcp_server)
    expected = {
        "list_customers",
        "get_account_info",
        "execute_gaql_query",
        "get_campaigns",
        "create_campaign",
        "update_campaign",
        "enable_campaign",
        "pause_campaign",
        "get_ad_groups",
        "create_ad_group",
        "update_ad_group",
        "get_ads",
        "create_responsive_search_ad",
        "enable_ad",
        "pause_ad",
        "get_keywords",
        "add_keywords",
        "add_negative_keywords",
        "get_search_terms_report",
        "get_campaign_metrics",
        "get_login_link",
    }
    missing = expected - set(names)
    assert not missing, f"Missing Google Ads tools: {missing}"


def test_tiktok_ads_tools_registered():
    from tiktok_ads_mcp.core.server import mcp_server
    from tiktok_ads_mcp.core import (  # noqa: F401
        accounts,
        adgroups,
        ads,
        authentication,
        campaigns,
        insights,
        media,
        targeting,
    )

    names = _tool_names(mcp_server)
    expected = {
        "list_tiktok_advertisers",
        "get_tiktok_advertiser_info",
        "get_tiktok_campaigns",
        "create_tiktok_campaign",
        "update_tiktok_campaign",
        "update_tiktok_campaign_status",
        "get_tiktok_adgroups",
        "create_tiktok_adgroup",
        "update_tiktok_adgroup",
        "update_tiktok_adgroup_status",
        "get_tiktok_ads",
        "create_tiktok_ad",
        "update_tiktok_ad",
        "update_tiktok_ad_status",
        "upload_tiktok_image",
        "upload_tiktok_video",
        "get_tiktok_insights",
        "get_tiktok_targeting_regions",
        "get_tiktok_interest_categories",
        "get_login_link",
    }
    missing = expected - set(names)
    assert not missing, f"Missing TikTok Ads tools: {missing}"
