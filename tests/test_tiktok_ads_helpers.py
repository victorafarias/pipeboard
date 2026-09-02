"""Unit tests for TikTok Ads MCP helpers (no live API)."""

import json

from tiktok_ads_mcp.core.api import auth_required_payload
from tiktok_ads_mcp.core.http_auth_integration import FastMCPAuthIntegration


def test_extract_bearer_token():
    token = FastMCPAuthIntegration.extract_token_from_headers(
        {"Authorization": "Bearer tiktok-access-token"}
    )
    assert token == "tiktok-access-token"


def test_extract_custom_header_token():
    token = FastMCPAuthIntegration.extract_token_from_headers(
        {"X-TIKTOK-ACCESS-TOKEN": "from-header"}
    )
    assert token == "from-header"


def test_auth_required_payload_is_json():
    payload = json.loads(auth_required_payload())
    assert "error" in payload
    assert "TIKTOK_ACCESS_TOKEN" in str(payload)


def test_campaign_objectives_cover_plan():
    from tiktok_ads_mcp.core.campaigns import CAMPAIGN_OBJECTIVES

    expected = {
        "TRAFFIC",
        "CONVERSIONS",
        "APP_INSTALL",
        "REACH",
        "VIDEO_VIEWS",
        "LEAD_GENERATION",
        "CATALOG_SALES",
        "COMMUNITY_INTERACTION",
    }
    assert expected <= CAMPAIGN_OBJECTIVES
