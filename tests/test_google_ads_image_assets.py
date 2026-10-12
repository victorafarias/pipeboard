"""Image upload validation and App ad image updates."""

import base64
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from google_ads_mcp.core.http_auth_integration import HTTP_MAX_BODY_BYTES
from google_ads_mcp.core.image_assets import (
    MAX_IMAGE_BYTES,
    update_app_ad_images,
    upload_image_asset,
)


def _error_message(result: str) -> str:
    payload = json.loads(result)
    assert "error" in payload, payload
    message = payload["error"]["message"]
    return str(message)


def _image_bytes(width: int, height: int, image_format: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (20, 40, 60)).save(buffer, format=image_format)
    return buffer.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _asset_client():
    pytest.importorskip("google.ads.googleads")
    from google.ads.googleads.v25.enums.types.asset_type import AssetTypeEnum
    from google.ads.googleads.v25.services.types.ad_service import AdOperation
    from google.ads.googleads.v25.services.types.asset_service import (
        AssetOperation,
        MutateAssetsRequest,
    )
    from google.ads.googleads.v25.common.types.ad_asset import AdImageAsset

    client = MagicMock()

    def get_type(name):
        types = {
            "AssetOperation": AssetOperation,
            "MutateAssetsRequest": MutateAssetsRequest,
            "AdOperation": AdOperation,
            "AdImageAsset": AdImageAsset,
        }
        return types[name]()

    client.get_type.side_effect = get_type
    client.enums.AssetTypeEnum = AssetTypeEnum.AssetType
    asset_service = MagicMock()
    asset_service.mutate_assets.return_value = SimpleNamespace(
        results=[SimpleNamespace(resource_name="customers/1234567890/assets/555")]
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


async def _upload(**overrides):
    params = {
        "customer_id": "123-456-7890",
        "name": "Hero",
        "access_token": "refresh-token",
    }
    params.update(overrides)
    with patch("google_ads_mcp.core.api.is_configured", return_value=True):
        return await upload_image_asset(**params)


@pytest.mark.asyncio
async def test_upload_image_asset_rejects_format_size_ratio_and_input():
    missing = await _upload()
    assert "either image_base64 or url" in _error_message(missing)

    both = await _upload(image_base64="aaaa", url="https://example.com/a.png")
    assert "not both" in _error_message(both)

    gif = await _upload(image_base64=_b64(_image_bytes(100, 100, "GIF")))
    assert "PNG or JPG" in _error_message(gif)

    wide = await _upload(image_base64=_b64(_image_bytes(160, 90, "PNG")))
    assert "1.91:1, 1:1, or 4:5" in _error_message(wide)

    oversized = await _upload(image_base64=_b64(b"x" * (MAX_IMAGE_BYTES + 1)))
    assert "maximum is 5 MB" in _error_message(oversized)

    nameless = await _upload(name="  ", image_base64=_b64(_image_bytes(100, 100)))
    assert "name is required" in _error_message(nameless)

    blocked = await _upload(url="http://127.0.0.1/secret.png")
    assert "non-public address" in _error_message(blocked)


@pytest.mark.asyncio
async def test_upload_image_asset_accepts_png_jpg_and_data_url():
    from google.ads.googleads.v25.enums.types.asset_type import AssetTypeEnum

    client, asset_service, _ = _asset_client()
    png = _image_bytes(191, 100, "PNG")
    jpeg = _image_bytes(80, 100, "JPEG")
    with patch("google_ads_mcp.core.image_assets.get_client", return_value=client):
        raw = await _upload(image_base64=f"data:image/png;base64,{_b64(png)}")
        jpeg_raw = await _upload(image_base64=_b64(jpeg), name="Square-ish")

    payload = json.loads(raw)
    assert payload["customer_id"] == "1234567890"
    assert payload["asset_resource_name"] == "customers/1234567890/assets/555"
    assert payload["asset_id"] == "555"
    assert payload["aspect_ratio"] == "1.91:1"
    assert payload["mime_type"] == "IMAGE_PNG"
    assert payload["width"] == 191
    assert payload["height"] == 100

    created = asset_service.mutate_assets.call_args_list[0].kwargs["request"].operations[0].create
    assert created.name == "Hero"
    assert created.type_ == AssetTypeEnum.AssetType.IMAGE
    assert created.image_asset.data == png
    assert asset_service.mutate_assets.call_args_list[0].kwargs["request"].customer_id == "1234567890"

    jpeg_payload = json.loads(jpeg_raw)
    assert jpeg_payload["aspect_ratio"] == "4:5"
    assert jpeg_payload["mime_type"] == "IMAGE_JPEG"


@pytest.mark.asyncio
async def test_update_app_ad_images_replace_masks_only_images():
    client, _, ad_service = _asset_client()
    existing = {
        "ad": {
            "id": "77",
            "type": "APP_AD",
            "app_ad": {
                "images": [{"asset": "customers/1234567890/assets/1"}],
                "headlines": [{"text": "Keep me"}],
            },
        }
    }
    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.image_assets.get_client", return_value=client
    ), patch("google_ads_mcp.core.image_assets.run_gaql", return_value=[existing]) as run_gaql:
        raw = await update_app_ad_images(
            customer_id="123-456-7890",
            ad_id="77",
            image_asset_resource_names=[
                "customers/1234567890/assets/9",
                "customers/1234567890/assets/9",
                "customers/1234567890/assets/8",
            ],
            access_token="token",
        )
    query = run_gaql.call_args.args[1]
    assert "FROM ad" in query
    assert "ad.app_ad.images" in query
    assert "ad.id = 77" in query
    operation = ad_service.mutate_ads.call_args.kwargs["operations"][0]
    assert list(operation.update_mask.paths) == ["app_ad.images"]
    assert [item.asset for item in operation.update.app_ad.images] == [
        "customers/1234567890/assets/9",
        "customers/1234567890/assets/8",
    ]
    assert len(operation.update.app_ad.headlines) == 0
    assert operation.update.resource_name == "customers/1234567890/ads/77"
    payload = json.loads(raw)
    assert payload["mode"] == "replace"
    assert payload["image_count"] == 2
    assert payload["ad_id"] == "77"
    assert "headlines" in payload["message"]


@pytest.mark.asyncio
async def test_update_app_ad_images_append_and_limits():
    client, _, ad_service = _asset_client()
    existing_assets = [
        {"asset": f"customers/1234567890/assets/{index}"} for index in range(1, 19)
    ]
    row = {"ad": {"type": "APP_AD", "app_ad": {"images": existing_assets}}}
    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.image_assets.get_client", return_value=client
    ), patch("google_ads_mcp.core.image_assets.run_gaql", return_value=[row]):
        raw = await update_app_ad_images(
            customer_id="1234567890",
            ad_id="77",
            image_asset_resource_names=[
                "customers/1234567890/assets/1",
                "customers/1234567890/assets/19",
                "customers/1234567890/assets/20",
            ],
            mode="append",
            access_token="token",
        )
        too_many = await update_app_ad_images(
            customer_id="1234567890",
            ad_id="77",
            image_asset_resource_names=[
                "customers/1234567890/assets/90",
                "customers/1234567890/assets/91",
                "customers/1234567890/assets/92",
            ],
            mode="APPEND",
            access_token="token",
        )
    payload = json.loads(raw)
    assert payload["image_count"] == 20
    assert payload["image_asset_resource_names"][-1] == "customers/1234567890/assets/20"
    assert "at most 20 images" in _error_message(too_many)
    assert ad_service.mutate_ads.call_count == 1

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.image_assets.run_gaql",
        return_value=[{"ad": {"type": "RESPONSIVE_SEARCH_AD"}}],
    ), patch("google_ads_mcp.core.image_assets.get_client") as get_client:
        not_app = await update_app_ad_images(
            customer_id="1234567890",
            ad_id="77",
            image_asset_resource_names=["customers/1234567890/assets/1"],
            access_token="token",
        )
    assert "not an App ad" in _error_message(not_app)
    get_client.assert_not_called()

    with patch("google_ads_mcp.core.api.is_configured", return_value=True), patch(
        "google_ads_mcp.core.image_assets.run_gaql"
    ) as run_gaql:
        bad_mode = await update_app_ad_images(
            customer_id="1234567890",
            ad_id="77",
            image_asset_resource_names=["customers/1234567890/assets/1"],
            mode="merge",
            access_token="token",
        )
    assert "mode must be replace or append" in _error_message(bad_mode)
    run_gaql.assert_not_called()


def test_http_body_limit_fits_base64_png_payloads():
    def base64_length(size: int) -> int:
        return 4 * ((size + 2) // 3)

    three_point_five_mb = int(3.5 * 1024 * 1024)
    assert HTTP_MAX_BODY_BYTES >= base64_length(three_point_five_mb) + 64 * 1024
    assert HTTP_MAX_BODY_BYTES >= base64_length(MAX_IMAGE_BYTES) + 64 * 1024
    assert HTTP_MAX_BODY_BYTES == 12 * 1024 * 1024


@pytest.mark.asyncio
async def test_streamable_http_accepts_multimegabyte_json_body():
    import httpx

    from google_ads_mcp.core.http_auth_integration import setup_fastmcp_http_auth
    from google_ads_mcp.core.server import mcp_server

    setup_fastmcp_http_auth(mcp_server)
    app = mcp_server.streamable_http_app()
    assert app.max_body_size == HTTP_MAX_BODY_BYTES
    # About a 3.5 MB PNG after base64, which is the remote-upload case.
    body = b'{"image_base64":"' + (b"A" * (5 * 1024 * 1024)) + b'"}'
    assert len(body) < HTTP_MAX_BODY_BYTES
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://google-ads") as client:
        accepted = await client.post(
            "/mcp",
            content=body,
            headers={"content-type": "application/json"},
        )
        rejected = await client.post(
            "/mcp",
            content=b"x" * (HTTP_MAX_BODY_BYTES + 1),
            headers={"content-type": "application/json"},
        )
    assert accepted.status_code == 401
    assert rejected.status_code == 413
