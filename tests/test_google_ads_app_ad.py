"""Tool registration and argument validation for Google Ads App ads."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from google_ads_mcp.core.ads import create_app_ad, get_ads


def _error_message(result: str) -> str:
    payload = json.loads(result)
    assert "error" in payload, payload
    message = payload["error"]["message"]
    if isinstance(message, dict):
        return json.dumps(message)
    return str(message)


async def _call_create(**overrides):
    params = {
        "customer_id": "123-456-7890",
        "ad_group_id": "99",
        "headlines": ["Install now"],
        "descriptions": ["Get the app"],
        "access_token": "refresh-token",
    }
    params.update(overrides)
    with patch("google_ads_mcp.core.api.is_configured", return_value=True):
        return await create_app_ad(**params)


def _proto_client():
    pytest.importorskip("google.ads.googleads")
    from google.ads.googleads.v25.common.types.ad_asset import (
        AdImageAsset,
        AdMediaBundleAsset,
        AdTextAsset,
        AdVideoAsset,
    )
    from google.ads.googleads.v25.enums.types.ad_group_ad_status import AdGroupAdStatusEnum
    from google.ads.googleads.v25.enums.types.asset_type import AssetTypeEnum
    from google.ads.googleads.v25.services.types.ad_group_ad_service import (
        AdGroupAdOperation,
        MutateAdGroupAdsRequest,
    )
    from google.ads.googleads.v25.services.types.asset_service import (
        AssetOperation,
        MutateAssetsRequest,
    )

    types = {
        "AdGroupAdOperation": AdGroupAdOperation,
        "AdTextAsset": AdTextAsset,
        "AdImageAsset": AdImageAsset,
        "AdVideoAsset": AdVideoAsset,
        "AdMediaBundleAsset": AdMediaBundleAsset,
        "MutateAdGroupAdsRequest": MutateAdGroupAdsRequest,
        "AssetOperation": AssetOperation,
        "MutateAssetsRequest": MutateAssetsRequest,
    }
    client = MagicMock()
    client.get_type.side_effect = lambda name: types[name]()
    client.enums.AdGroupAdStatusEnum = AdGroupAdStatusEnum.AdGroupAdStatus
    client.enums.AssetTypeEnum = AssetTypeEnum.AssetType

    ad_group_service = MagicMock()
    ad_group_service.ad_group_path.side_effect = (
        lambda customer_id, ad_group_id: f"customers/{customer_id}/adGroups/{ad_group_id}"
    )
    ad_group_ad_service = MagicMock()
    ad_group_ad_service.mutate_ad_group_ads.return_value = SimpleNamespace(
        results=[SimpleNamespace(resource_name="customers/1234567890/adGroupAds/99~4242")]
    )
    asset_service = MagicMock()
    asset_service.mutate_assets.return_value = SimpleNamespace(
        results=[SimpleNamespace(resource_name="customers/1234567890/assets/777")]
    )

    def get_service(name):
        if name == "AdGroupService":
            return ad_group_service
        if name == "AdGroupAdService":
            return ad_group_ad_service
        if name == "AssetService":
            return asset_service
        raise AssertionError(name)

    client.get_service.side_effect = get_service
    return client, ad_group_ad_service, asset_service


@pytest.mark.asyncio
async def test_create_app_ad_rejects_headline_count_and_length():
    missing = await _call_create(headlines=[])
    assert "1-5 headlines" in _error_message(missing)

    too_many = await _call_create(headlines=["a", "b", "c", "d", "e", "f"])
    assert "1-5 headlines (got 6)" in _error_message(too_many)

    too_long = await _call_create(headlines=["h" * 31])
    assert "31 characters" in _error_message(too_long)
    assert "30 characters or fewer" in _error_message(too_long)

    empty = await _call_create(headlines=["   "])
    assert "Headline 1 is empty" in _error_message(empty)

    not_a_list = await _call_create(headlines="Install now")
    assert "headlines must be a list" in _error_message(not_a_list)


@pytest.mark.asyncio
async def test_create_app_ad_rejects_description_count_and_length():
    missing = await _call_create(descriptions=[])
    assert "1-5 descriptions" in _error_message(missing)

    too_many = await _call_create(descriptions=["a", "b", "c", "d", "e", "f"])
    assert "1-5 descriptions (got 6)" in _error_message(too_many)

    too_long = await _call_create(descriptions=["d" * 91])
    assert "91 characters" in _error_message(too_long)
    assert "90 characters or fewer" in _error_message(too_long)


@pytest.mark.asyncio
async def test_create_app_ad_rejects_status_assets_and_youtube_values():
    status = await _call_create(status="REMOVED")
    assert "status must be ENABLED or PAUSED" in _error_message(status)

    image = await _call_create(image_asset_resource_names=["not-an-asset"])
    assert "Image asset 1 must be an asset resource name" in _error_message(image)

    html5 = await _call_create(html5_media_bundles=["customers/1/assets/nope"])
    assert "HTML5 media bundle 1 must be an asset resource name" in _error_message(html5)

    video = await _call_create(youtube_videos=["not-a-video-id"])
    assert "11-character video id" in _error_message(video)

    missing_group = await _call_create(ad_group_id="  ")
    assert "ad_group_id is required" in _error_message(missing_group)


@pytest.mark.asyncio
async def test_create_app_ad_returns_resource_name_and_id():
    client, ad_group_ad_service, asset_service = _proto_client()
    from google.ads.googleads.v25.enums.types.ad_group_ad_status import AdGroupAdStatusEnum

    headlines = ["h" * 30, "Second"]
    descriptions = ["d" * 90]
    with patch("google_ads_mcp.core.ads.get_client", return_value=client), patch(
        "google_ads_mcp.core.ads.run_gaql"
    ) as run_gaql:
        raw = await _call_create(
            headlines=headlines,
            descriptions=descriptions,
            image_asset_resource_names=["customers/1234567890/assets/10"],
            html5_media_bundles=["customers/1234567890/assets/11"],
            youtube_videos=["customers/1234567890/assets/12"],
            status="enabled",
        )
    run_gaql.assert_not_called()
    asset_service.mutate_assets.assert_not_called()

    payload = json.loads(raw)
    assert payload["customer_id"] == "1234567890"
    assert payload["ad_group_id"] == "99"
    assert payload["ad_resource_name"] == "customers/1234567890/adGroupAds/99~4242"
    assert payload["ad_id"] == "4242"
    assert payload["status"] == "ENABLED"
    assert payload["validate_only"] is False
    assert payload["youtube_video_assets"] == [
        {
            "resource_name": "customers/1234567890/assets/12",
            "created": False,
            "youtube_video_id": None,
        }
    ]

    request = ad_group_ad_service.mutate_ad_group_ads.call_args.kwargs["request"]
    assert request.customer_id == "1234567890"
    assert request.validate_only is False
    created = request.operations[0].create
    assert created.ad_group == "customers/1234567890/adGroups/99"
    assert created.status == AdGroupAdStatusEnum.AdGroupAdStatus.ENABLED
    assert [item.text for item in created.ad.app_ad.headlines] == headlines
    assert [item.text for item in created.ad.app_ad.descriptions] == descriptions
    assert [item.asset for item in created.ad.app_ad.images] == ["customers/1234567890/assets/10"]
    assert [item.asset for item in created.ad.app_ad.youtube_videos] == [
        "customers/1234567890/assets/12"
    ]
    assert [item.asset for item in created.ad.app_ad.html5_media_bundles] == [
        "customers/1234567890/assets/11"
    ]


@pytest.mark.asyncio
async def test_create_app_ad_creates_youtube_asset_for_video_id_and_url():
    client, ad_group_ad_service, asset_service = _proto_client()
    from google.ads.googleads.v25.enums.types.asset_type import AssetTypeEnum

    with patch("google_ads_mcp.core.ads.get_client", return_value=client), patch(
        "google_ads_mcp.core.ads.run_gaql", return_value=[]
    ) as run_gaql:
        raw = await _call_create(
            youtube_videos=[
                "dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=abcdefghijk&feature=share",
            ],
            validate_only=True,
        )

    assert run_gaql.call_count == 2
    assert "dQw4w9WgXcQ" in run_gaql.call_args_list[0].args[1]
    assert "abcdefghijk" in run_gaql.call_args_list[1].args[1]
    assert asset_service.mutate_assets.call_count == 2
    first_asset_request = asset_service.mutate_assets.call_args_list[0].kwargs["request"]
    created_asset = first_asset_request.operations[0].create
    assert created_asset.youtube_video_asset.youtube_video_id == "dQw4w9WgXcQ"
    assert created_asset.type_ == AssetTypeEnum.AssetType.YOUTUBE_VIDEO
    assert first_asset_request.validate_only is False

    request = ad_group_ad_service.mutate_ad_group_ads.call_args.kwargs["request"]
    assert request.validate_only is True
    videos = [item.asset for item in request.operations[0].create.ad.app_ad.youtube_videos]
    assert videos == ["customers/1234567890/assets/777", "customers/1234567890/assets/777"]

    payload = json.loads(raw)
    assert payload["validate_only"] is True
    assert payload["ad_resource_name"] == "customers/1234567890/adGroupAds/99~4242"
    assert payload["ad_id"] == "4242"
    assert payload["status"] == "PAUSED"
    assert all(item["created"] for item in payload["youtube_video_assets"])
    assert "YouTube video assets were still created" in payload["message"]


@pytest.mark.asyncio
async def test_create_app_ad_reuses_existing_youtube_asset():
    client, _, asset_service = _proto_client()
    existing = [{"asset": {"resource_name": "customers/1234567890/assets/55"}}]
    with patch("google_ads_mcp.core.ads.get_client", return_value=client), patch(
        "google_ads_mcp.core.ads.run_gaql", return_value=existing
    ):
        raw = await _call_create(youtube_videos=["dQw4w9WgXcQ"])

    asset_service.mutate_assets.assert_not_called()
    payload = json.loads(raw)
    assert payload["youtube_video_assets"][0]["resource_name"] == "customers/1234567890/assets/55"
    assert payload["youtube_video_assets"][0]["created"] is False
    assert payload["youtube_video_assets"][0]["youtube_video_id"] == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_create_app_ad_validate_only_without_results():
    client, ad_group_ad_service, _ = _proto_client()
    ad_group_ad_service.mutate_ad_group_ads.return_value = SimpleNamespace(results=[])
    with patch("google_ads_mcp.core.ads.get_client", return_value=client):
        raw = await _call_create(validate_only=True)

    payload = json.loads(raw)
    assert payload["validate_only"] is True
    assert payload["ad_resource_name"] is None
    assert payload["ad_id"] is None
    assert "No App ad was created" in payload["message"]
    request = ad_group_ad_service.mutate_ad_group_ads.call_args.kwargs["request"]
    assert request.validate_only is True


@pytest.mark.asyncio
async def test_get_ads_selects_app_ad_headlines_and_descriptions():
    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ads.run_gaql", return_value=[]
    ) as run_gaql:
        raw = await get_ads(customer_id="123-456-7890", ad_group_id="99", access_token="token")

    query = run_gaql.call_args.args[1]
    assert "ad_group_ad.ad.responsive_search_ad.headlines" in query
    assert "ad_group_ad.ad.responsive_search_ad.descriptions" in query
    assert "ad_group_ad.ad.app_ad.headlines" in query
    assert "ad_group_ad.ad.app_ad.descriptions" in query
    assert "ad_group_ad.ad.app_ad.images" in query
    assert "ad_group.id = 99" in query
    payload = json.loads(raw)
    assert payload["customer_id"] == "1234567890"
    assert payload["ads"] == []
