"""Unit tests for Google Ads MCP helpers (no live API)."""

import json

from google_ads_mcp.core.http_auth_integration import FastMCPAuthIntegration
from google_ads_mcp.core.utils import currency_to_micros, micros_to_currency, normalize_customer_id


def test_normalize_customer_id_strips_dashes():
    assert normalize_customer_id("123-456-7890") == "1234567890"
    assert normalize_customer_id(" 1234567890 ") == "1234567890"
    assert normalize_customer_id("") == ""


def test_currency_to_micros_converts_units():
    assert currency_to_micros(10) == 10_000_000
    assert currency_to_micros(10.5) == 10_500_000
    assert currency_to_micros(5_000_000) == 5_000_000


def test_micros_to_currency():
    assert micros_to_currency(10_000_000) == 10.0


def test_extract_bearer_token():
    token = FastMCPAuthIntegration.extract_token_from_headers(
        {"Authorization": "Bearer refresh-token-value"}
    )
    assert token == "refresh-token-value"


def test_extract_custom_header_token():
    token = FastMCPAuthIntegration.extract_token_from_headers(
        {"X-GOOGLE-ADS-REFRESH-TOKEN": "from-header"}
    )
    assert token == "from-header"


def test_auth_required_payload_is_json():
    from google_ads_mcp.core.api import auth_required_payload

    payload = json.loads(auth_required_payload())
    assert "error" in payload
    assert "GOOGLE_ADS_REFRESH_TOKEN" in str(payload)
