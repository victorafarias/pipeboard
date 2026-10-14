"""YouTube asset reuse and App ad video updates."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from google_ads_mcp.core.ads import create_youtube_video_asset
from google_ads_mcp.core.image_assets import update_app_ad_videos


def _error_message(result: str) -> str:
    payload = json.loads(result)
    assert "error" in payload, payload
    return str(payload["error"]["message"])


def _client():
    pytest.importorskip("google.ads.googleads")
    from google.ads.googleads.v25.common.types.ad_asset import AdVideoAsset
    from google.ads.googleads.v25.enums.types.asset_type import AssetTypeEnum
    from google.ads.googleads.v25.services.types.ad_service import AdOperation
    from google.ads.googleads.v25.services.types.asset_service import (
        AssetOperation,
        MutateAssetsRequest,
    )

    client = MagicMock()

    def get_type(name):
        types = {
            "AssetOperation": AssetOperation,
            "MutateAssetsRequest": MutateAssetsRequest,
            "AdOperation": AdOperation,
            "AdVideoAsset": AdVideoAsset,
        }
        return types[name]()

    client.get_type.side_effect = get_type
    client.enums.AssetTypeEnum = AssetTypeEnum.AssetType
    asset_service = MagicMock()
    asset_service.mutate_assets.return_value = SimpleNamespace(
        results=[SimpleNamespace(resource_name="customers/1234567890/assets/777")]
    )
    ad_service = MagicMock()
    ad_service.ad_path.side_effect = (
        lambda customer_id, ad_id: f"customers/{customer_id}/ads/{ad_id}"
    )
    ad_service.mutate_ads.return_value = SimpleNamespace(
        results=[SimpleNamespace(resource_name="customers/1234567890/ads/77")]
    )

    def get_service(name):
        if name == "AssetService":
            return asset_service
        if name == "AdService":
            return ad_service
        raise AssertionError(name)

    client.get_service.side_effect = get_service
    return client, asset_service, ad_service


@pytest.mark.asyncio
async def test_create_youtube_video_asset_reuses_or_creates():
    from google.ads.googleads.v25.enums.types.asset_type import AssetTypeEnum

    client, asset_service, _ = _client()
    existing = [{"asset": {"resource_name": "customers/1234567890/assets/42"}}]
    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ads.get_client", return_value=client
    ), patch("google_ads_mcp.core.ads.run_gaql", return_value=existing) as run_gaql:
        reused = json.loads(
            await create_youtube_video_asset(
                customer_id="123-456-7890",
                video="https://www.youtube.com/shorts/dQw4w9WgXcQ",
                name="Ignored when reused",
                access_token="token",
            )
        )
    asset_service.mutate_assets.assert_not_called()
    assert "dQw4w9WgXcQ" in run_gaql.call_args.args[1]
    assert reused["asset_resource_name"] == "customers/1234567890/assets/42"
    assert reused["asset_id"] == "42"
    assert reused["youtube_video_id"] == "dQw4w9WgXcQ"
    assert reused["created"] is False
    assert reused["customer_id"] == "1234567890"

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ads.get_client", return_value=client
    ), patch("google_ads_mcp.core.ads.run_gaql", return_value=[]):
        created = json.loads(
            await create_youtube_video_asset(
                customer_id="1234567890",
                video="https://youtu.be/abcdefghijk",
                name="Launch film",
                access_token="token",
            )
        )
    request = asset_service.mutate_assets.call_args.kwargs["request"]
    asset = request.operations[0].create
    assert asset.youtube_video_asset.youtube_video_id == "abcdefghijk"
    assert asset.type_ == AssetTypeEnum.AssetType.YOUTUBE_VIDEO
    assert asset.name == "Launch film"
    assert created["created"] is True
    assert created["asset_resource_name"] == "customers/1234567890/assets/777"
    assert created["name"] == "Launch film"

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ads.run_gaql"
    ) as run_gaql:
        invalid = await create_youtube_video_asset(
            customer_id="1234567890",
            video="not-a-video-id",
            access_token="token",
        )
    assert "11-character" in _error_message(invalid)
    run_gaql.assert_not_called()

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.ads.run_gaql"
    ) as run_gaql:
        asset_name = await create_youtube_video_asset(
            customer_id="1234567890",
            video="customers/1234567890/assets/1",
            access_token="token",
        )
    assert "update_app_ad_videos" in _error_message(asset_name)
    run_gaql.assert_not_called()


@pytest.mark.asyncio
async def test_update_app_ad_videos_replace_masks_only_videos():
    client, _, ad_service = _client()

    def run_gaql(_customer_id, query, _token):
        if "FROM ad" in query:
            return [{
                "ad": {
                    "id": "77",
                    "type": "APP_AD",
                    "app_ad": {
                        "youtube_videos": [{"asset": "customers/1234567890/assets/1"}],
                        "images": [{"asset": "customers/1234567890/assets/9"}],
                        "headlines": [{"text": "Keep me"}],
                    },
                }
            }]
        return []

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.image_assets.get_client", return_value=client
    ), patch("google_ads_mcp.core.ads.get_client", return_value=client), patch(
        "google_ads_mcp.core.image_assets.run_gaql", side_effect=run_gaql
    ), patch("google_ads_mcp.core.ads.run_gaql", side_effect=run_gaql):
        raw = await update_app_ad_videos(
            customer_id="123-456-7890",
            ad_id="77",
            youtube_videos=[
                "customers/1234567890/assets/3",
                "https://www.youtube.com/watch?v=abcdefghijk",
                "abcdefghijk",
            ],
            access_token="token",
        )

    operation = ad_service.mutate_ads.call_args.kwargs["operations"][0]
    assert list(operation.update_mask.paths) == ["app_ad.youtube_videos"]
    assert [item.asset for item in operation.update.app_ad.youtube_videos] == [
        "customers/1234567890/assets/3",
        "customers/1234567890/assets/777",
    ]
    assert len(operation.update.app_ad.images) == 0
    assert len(operation.update.app_ad.headlines) == 0
    assert len(operation.update.app_ad.descriptions) == 0
    payload = json.loads(raw)
    assert payload["mode"] == "replace"
    assert payload["video_count"] == 2
    assert payload["ad_id"] == "77"
    assert "Images, headlines, descriptions, and status" in payload["message"]


@pytest.mark.asyncio
async def test_update_app_ad_videos_append_dedupes_and_enforces_limit():
    client, asset_service, ad_service = _client()
    existing_videos = [
        {"asset": f"customers/1234567890/assets/{index}"} for index in range(1, 21)
    ]

    def run_gaql(_customer_id, query, _token):
        if "FROM ad" in query:
            return [{"ad": {"type": "APP_AD", "app_ad": {"youtube_videos": existing_videos}}}]
        if "dQw4w9WgXcQ" in query:
            return [{"asset": {"resource_name": "customers/1234567890/assets/1"}}]
        return []

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.image_assets.get_client", return_value=client
    ), patch("google_ads_mcp.core.ads.get_client", return_value=client), patch(
        "google_ads_mcp.core.image_assets.run_gaql", side_effect=run_gaql
    ), patch("google_ads_mcp.core.ads.run_gaql", side_effect=run_gaql):
        reused = json.loads(
            await update_app_ad_videos(
                customer_id="1234567890",
                ad_id="77",
                youtube_videos=["dQw4w9WgXcQ", "customers/1234567890/assets/1"],
                mode="append",
                access_token="token",
            )
        )
        too_many = await update_app_ad_videos(
            customer_id="1234567890",
            ad_id="77",
            youtube_videos=["https://youtu.be/zzzzzzzzzzz"],
            mode="APPEND",
            access_token="token",
        )
    assert reused["video_count"] == 20
    assert reused["youtube_video_assets"][0] == "customers/1234567890/assets/1"
    asset_service.mutate_assets.assert_not_called()
    assert ad_service.mutate_ads.call_count == 1
    assert "at most 20 videos" in _error_message(too_many)

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.image_assets.run_gaql",
        return_value=[{"ad": {"type": "RESPONSIVE_SEARCH_AD"}}],
    ), patch("google_ads_mcp.core.ads.run_gaql", return_value=[]), patch(
        "google_ads_mcp.core.image_assets.get_client"
    ) as get_client:
        not_app = await update_app_ad_videos(
            customer_id="1234567890",
            ad_id="77",
            youtube_videos=["customers/1234567890/assets/1"],
            access_token="token",
        )
    assert "not an App ad" in _error_message(not_app)
    get_client.assert_not_called()
