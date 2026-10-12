"""create_ad_group keeps Search groups as SEARCH_STANDARD and omits type for App campaigns."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from google_ads_mcp.core.ad_groups import create_ad_group
from google_ads_mcp.core.utils import currency_to_micros


def _error_message(result: str) -> str:
    payload = json.loads(result)
    assert "error" in payload, payload
    message = payload["error"]["message"]
    if isinstance(message, dict):
        return json.dumps(message)
    return str(message)


def _proto_client():
    pytest.importorskip("google.ads.googleads")
    from google.ads.googleads.v25.enums.types.ad_group_status import AdGroupStatusEnum
    from google.ads.googleads.v25.enums.types.ad_group_type import AdGroupTypeEnum
    from google.ads.googleads.v25.services.types.ad_group_service import AdGroupOperation

    client = MagicMock()
    client.get_type.side_effect = lambda name: AdGroupOperation()
    client.enums.AdGroupStatusEnum = AdGroupStatusEnum.AdGroupStatus
    client.enums.AdGroupTypeEnum = AdGroupTypeEnum.AdGroupType

    ad_group_service = MagicMock()
    ad_group_service.mutate_ad_groups.return_value = SimpleNamespace(
        results=[SimpleNamespace(resource_name="customers/1234567890/adGroups/777")]
    )
    campaign_service = MagicMock()
    campaign_service.campaign_path.side_effect = (
        lambda customer_id, campaign_id: f"customers/{customer_id}/campaigns/{campaign_id}"
    )

    def get_service(name):
        if name == "AdGroupService":
            return ad_group_service
        if name == "CampaignService":
            return campaign_service
        raise AssertionError(name)

    client.get_service.side_effect = get_service
    return client, ad_group_service


def _created(ad_group_service):
    operation = ad_group_service.mutate_ad_groups.call_args.kwargs["operations"][0]
    return operation.create


async def _call(campaign_row, **overrides):
    client, ad_group_service = _proto_client()
    params = {
        "customer_id": "123-456-7890",
        "campaign_id": "42",
        "name": "Group",
        "access_token": "refresh-token",
    }
    params.update(overrides)
    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ad_groups.get_client", return_value=client
    ), patch("google_ads_mcp.core.ad_groups.run_gaql", return_value=[campaign_row]) as run_gaql:
        raw = await create_ad_group(**params)
    return raw, ad_group_service, run_gaql


_SEARCH = {
    "campaign": {
        "advertising_channel_type": "SEARCH",
        "advertising_channel_sub_type": "UNSPECIFIED",
    }
}
_APP = {
    "campaign": {
        "advertising_channel_type": "MULTI_CHANNEL",
        "advertising_channel_sub_type": "APP_CAMPAIGN",
    }
}


@pytest.mark.asyncio
async def test_search_ad_group_stays_search_standard_and_paused():
    from google.ads.googleads.v25.enums.types.ad_group_status import AdGroupStatusEnum
    from google.ads.googleads.v25.enums.types.ad_group_type import AdGroupTypeEnum

    raw, service, run_gaql = await _call(_SEARCH, cpc_bid=2.5)
    created = _created(service)
    assert created.type_ == AdGroupTypeEnum.AdGroupType.SEARCH_STANDARD
    assert created.status == AdGroupStatusEnum.AdGroupStatus.PAUSED
    assert created.cpc_bid_micros == currency_to_micros(2.5)
    assert created._pb.HasField("cpc_bid_micros")
    assert created.campaign == "customers/1234567890/campaigns/42"
    assert "campaign.id = 42" in run_gaql.call_args.args[1]
    assert run_gaql.call_args.args[0] == "1234567890"

    payload = json.loads(raw)
    assert payload["ad_group_id"] == "777"
    assert payload["status"] == "PAUSED"
    assert payload["ad_group_type"] == "SEARCH_STANDARD"
    assert "cpc_bid_skipped" not in payload


@pytest.mark.asyncio
async def test_search_ad_group_omits_cpc_when_not_provided_and_accepts_enabled():
    from google.ads.googleads.v25.enums.types.ad_group_status import AdGroupStatusEnum

    raw, service, _ = await _call(_SEARCH, status="ENABLED")
    created = _created(service)
    assert created.status == AdGroupStatusEnum.AdGroupStatus.ENABLED
    assert created._pb.HasField("cpc_bid_micros") is False
    assert "type_" in {field.name for field, _ in created._pb.ListFields()}
    payload = json.loads(raw)
    assert payload["status"] == "ENABLED"
    assert payload["ad_group_type"] == "SEARCH_STANDARD"


@pytest.mark.asyncio
async def test_app_campaign_omits_type_and_skips_cpc_bid():
    from google.ads.googleads.v25.enums.types.ad_group_status import AdGroupStatusEnum

    raw, service, _ = await _call(_APP, cpc_bid=3)
    created = _created(service)
    field_names = {field.name for field, _ in created._pb.ListFields()}
    assert "type_" not in field_names
    assert created._pb.HasField("cpc_bid_micros") is False
    assert created.status == AdGroupStatusEnum.AdGroupStatus.PAUSED
    assert created.name == "Group"
    assert created.campaign == "customers/1234567890/campaigns/42"

    payload = json.loads(raw)
    assert payload["ad_group_type"] is None
    assert payload["status"] == "PAUSED"
    assert payload["cpc_bid_skipped"] is True
    assert "cpc_bid was ignored" in payload["message"]
    assert payload["ad_group_resource_name"] == "customers/1234567890/adGroups/777"


@pytest.mark.asyncio
async def test_app_campaign_without_bid_does_not_set_type():
    raw, service, _ = await _call(
        {
            "campaign": {
                "advertising_channel_type": "MULTI_CHANNEL",
                "advertising_channel_sub_type": "APP_CAMPAIGN_FOR_ENGAGEMENT",
            }
        }
    )
    created = _created(service)
    assert "type_" not in {field.name for field, _ in created._pb.ListFields()}
    payload = json.loads(raw)
    assert payload["ad_group_type"] is None
    assert "cpc_bid_skipped" not in payload


@pytest.mark.asyncio
async def test_app_campaign_detected_from_enum_numbers():
    _, service, _ = await _call(
        {"campaign": {"advertising_channel_type": 7, "advertising_channel_sub_type": 12}}
    )
    created = _created(service)
    assert "type_" not in {field.name for field, _ in created._pb.ListFields()}


@pytest.mark.asyncio
async def test_explicit_ad_group_type_overrides_search_default():
    from google.ads.googleads.v25.enums.types.ad_group_type import AdGroupTypeEnum

    raw, service, _ = await _call(_SEARCH, ad_group_type="display_standard")
    created = _created(service)
    assert created.type_ == AdGroupTypeEnum.AdGroupType.DISPLAY_STANDARD
    payload = json.loads(raw)
    assert payload["ad_group_type"] == "DISPLAY_STANDARD"


@pytest.mark.asyncio
async def test_explicit_ad_group_type_can_be_set_on_app_campaign():
    from google.ads.googleads.v25.enums.types.ad_group_type import AdGroupTypeEnum

    _, service, _ = await _call(_APP, ad_group_type="SEARCH_STANDARD", cpc_bid=1)
    created = _created(service)
    assert created.type_ == AdGroupTypeEnum.AdGroupType.SEARCH_STANDARD
    assert created._pb.HasField("cpc_bid_micros") is False


@pytest.mark.asyncio
async def test_invalid_ad_group_type_and_missing_campaign():
    client, service = _proto_client()
    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ad_groups.run_gaql", return_value=[_SEARCH]
    ), patch("google_ads_mcp.core.ad_groups.get_client", return_value=client):
        invalid = await create_ad_group(
            customer_id="1234567890",
            campaign_id="42",
            name="Group",
            ad_group_type="NOT_A_TYPE",
            access_token="token",
        )
    assert "Unsupported ad_group_type" in _error_message(invalid)
    service.mutate_ad_groups.assert_not_called()

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ad_groups.run_gaql", return_value=[]
    ), patch("google_ads_mcp.core.ad_groups.get_client") as get_client:
        missing = await create_ad_group(
            customer_id="1234567890",
            campaign_id="42",
            name="Group",
            access_token="token",
        )
    assert "Campaign 42 not found" in _error_message(missing)
    get_client.assert_not_called()

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ad_groups.run_gaql"
    ) as run_gaql:
        bad_id = await create_ad_group(
            customer_id="1234567890",
            campaign_id="abc",
            name="Group",
            access_token="token",
        )
    assert "campaign_id must be a numeric campaign ID" in _error_message(bad_id)
    run_gaql.assert_not_called()
