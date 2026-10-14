"""upload_ad_video uses file_url or resumable advideos chunks."""

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from meta_ads_mcp.core.ads import VIDEO_CHUNK_MAX_BYTES, upload_ad_video


def _error(result: str) -> str:
    payload = json.loads(result)
    assert "error" in payload
    message = payload["error"]
    return message if isinstance(message, str) else json.dumps(message)


@pytest.mark.asyncio
async def test_upload_ad_video_from_public_url_polls_until_ready():
    calls = []

    async def fake_api(endpoint, access_token, params=None, method="GET", files=None, timeout=30.0):
        calls.append((endpoint, method, params, files))
        if method == "POST":
            return {"id": "vid_9"}
        if len([item for item in calls if item[1] == "GET"]) == 1:
            return {"id": "vid_9", "status": {"video_status": "processing"}}
        return {
            "id": "vid_9",
            "status": {"video_status": "ready"},
            "picture": "https://cdn.example/picture.jpg",
            "thumbnails": {
                "data": [
                    {"uri": "https://cdn.example/other.jpg", "is_preferred": False},
                    {"uri": "https://cdn.example/preferred.jpg", "is_preferred": True},
                ]
            },
        }

    with patch("meta_ads_mcp.core.ads.make_api_request", side_effect=fake_api), patch(
        "meta_ads_mcp.core.ads.asyncio.sleep", new_callable=AsyncMock
    ):
        result = json.loads(
            await upload_ad_video(
                account_id="123",
                video_url="https://example.com/launch.mp4",
                name="Launch",
                access_token="token",
                timeout_seconds=5,
            )
        )

    post = calls[0]
    assert post[0] == "act_123/advideos"
    assert post[1] == "POST"
    assert post[2]["file_url"] == "https://example.com/launch.mp4"
    assert post[2]["name"] == "Launch"
    assert result["success"] is True
    assert result["video_id"] == "vid_9"
    assert result["status"] == "ready"
    assert result["thumbnails"][0] == "https://cdn.example/preferred.jpg"
    assert "https://cdn.example/picture.jpg" in result["thumbnails"]


@pytest.mark.asyncio
async def test_upload_ad_video_base64_uses_resumable_phases():
    posts = []

    async def fake_api(endpoint, access_token, params=None, method="GET", files=None, timeout=30.0):
        if method == "POST":
            posts.append((params, files))
            phase = params.get("upload_phase")
            if phase == "start":
                return {"upload_session_id": "sess", "video_id": "vid_b", "start_offset": "0", "end_offset": "4"}
            if phase == "transfer":
                chunk = files["video_file_chunk"][1]
                assert params["start_offset"] in (0, 4)
                assert len(chunk) == 4
                offset = int(params["start_offset"]) + len(chunk)
                return {"start_offset": str(offset), "end_offset": "8" if offset < 8 else "8"}
            if phase == "finish":
                assert params["upload_session_id"] == "sess"
                assert params["title"] == "Clip"
                return {"success": True}
        return {
            "id": "vid_b",
            "status": {"video_status": "ready"},
            "thumbnails": {"data": [{"uri": "https://cdn.example/thumb.jpg"}]},
        }

    payload = base64.b64encode(b"12345678").decode("ascii")
    with patch("meta_ads_mcp.core.ads.make_api_request", side_effect=fake_api), patch(
        "meta_ads_mcp.core.ads.asyncio.sleep", new_callable=AsyncMock
    ):
        result = json.loads(
            await upload_ad_video(
                account_id="act_5",
                video_base64=payload,
                name="Clip",
                access_token="token",
            )
        )

    phases = [params["upload_phase"] for params, _files in posts]
    assert phases == ["start", "transfer", "transfer", "finish"]
    assert result["video_id"] == "vid_b"
    assert result["thumbnails"] == ["https://cdn.example/thumb.jpg"]
    assert result["success"] is True


@pytest.mark.asyncio
async def test_chunked_upload_across_calls_and_size_limit():
    with patch("meta_ads_mcp.core.ads.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = {
            "upload_session_id": "sess",
            "video_id": "vid_c",
            "start_offset": "0",
            "end_offset": "8388608",
        }
        started = json.loads(
            await upload_ad_video(
                account_id="act_5",
                upload_phase="start",
                file_size=13 * 1024 * 1024,
                access_token="token",
            )
        )
    assert started["upload_session_id"] == "sess"
    assert started["video_id"] == "vid_c"
    assert started["max_chunk_bytes"] == VIDEO_CHUNK_MAX_BYTES
    assert "13 MB" in started["message"]

    with patch("meta_ads_mcp.core.ads.VIDEO_CHUNK_MAX_BYTES", 4), patch(
        "meta_ads_mcp.core.ads.make_api_request", new_callable=AsyncMock
    ) as mock_api:
        too_big = await upload_ad_video(
            account_id="act_5",
            video_base64=base64.b64encode(b"12345").decode("ascii"),
            access_token="token",
        )
    assert "12 MiB" in _error(too_big)
    mock_api.assert_not_called()

    async def transfer_api(endpoint, access_token, params=None, method="GET", files=None, timeout=30.0):
        assert files["video_file_chunk"][1] == b"abcd"
        assert params["upload_phase"] == "transfer"
        assert params["start_offset"] == 0
        return {"start_offset": "4", "end_offset": "4"}

    with patch("meta_ads_mcp.core.ads.make_api_request", side_effect=transfer_api):
        transferred = json.loads(
            await upload_ad_video(
                account_id="act_5",
                upload_phase="transfer",
                upload_session_id="sess",
                start_offset=0,
                video_base64=base64.b64encode(b"abcd").decode("ascii"),
                video_id="vid_c",
                access_token="token",
            )
        )
    assert transferred["upload_complete"] is True

    async def finish_api(endpoint, access_token, params=None, method="GET", files=None, timeout=30.0):
        if method == "POST":
            assert params["upload_phase"] == "finish"
            return {"success": True}
        return {
            "status": {"video_status": "ready"},
            "picture": "https://cdn.example/done.jpg",
        }

    with patch("meta_ads_mcp.core.ads.make_api_request", side_effect=finish_api), patch(
        "meta_ads_mcp.core.ads.asyncio.sleep", new_callable=AsyncMock
    ):
        finished = json.loads(
            await upload_ad_video(
                account_id="act_5",
                upload_phase="finish",
                upload_session_id="sess",
                video_id="vid_c",
                name="Big",
                access_token="token",
            )
        )
    assert finished["video_id"] == "vid_c"
    assert finished["thumbnails"] == ["https://cdn.example/done.jpg"]
    assert finished["status"] == "ready"


@pytest.mark.asyncio
async def test_upload_ad_video_validation_and_timeout():
    with patch("meta_ads_mcp.core.ads.make_api_request", new_callable=AsyncMock) as mock_api:
        missing = await upload_ad_video(account_id="act_1", access_token="token")
        both = await upload_ad_video(
            account_id="act_1",
            video_url="https://cdn.example/a.mp4",
            video_base64="aaaa",
            access_token="token",
        )
        blocked = await upload_ad_video(
            account_id="act_1",
            video_url="http://127.0.0.1/secret.mp4",
            access_token="token",
        )
    assert "Provide video_url or video_base64" in _error(missing)
    assert "not both" in _error(both)
    assert "non-public address" in _error(blocked)
    mock_api.assert_not_called()

    ticks = {"n": 0}

    def monotonic():
        ticks["n"] += 1
        return 0 if ticks["n"] < 5 else 1000

    async def processing(endpoint, access_token, params=None, method="GET", files=None, timeout=30.0):
        if method == "POST":
            return {"id": "vid_wait"}
        return {"id": "vid_wait", "status": {"video_status": "processing"}}

    with patch("meta_ads_mcp.core.ads.make_api_request", side_effect=processing), patch(
        "meta_ads_mcp.core.ads.time.monotonic", side_effect=monotonic
    ), patch("meta_ads_mcp.core.ads.asyncio.sleep", new_callable=AsyncMock):
        waited = json.loads(
            await upload_ad_video(
                account_id="act_1",
                video_url="https://example.com/slow.mp4",
                access_token="token",
                timeout_seconds=30,
            )
        )
    assert waited["video_id"] == "vid_wait"
    assert waited["status"] == "processing"
    assert waited["success"] is False
    assert "not ready" in waited["error"]


def test_video_chunk_fits_under_12_mib_and_13_mb_needs_more_than_one():
    encoded = 4 * ((VIDEO_CHUNK_MAX_BYTES + 2) // 3)
    assert encoded + 256 * 1024 < 12 * 1024 * 1024
    assert 13 * 1024 * 1024 > VIDEO_CHUNK_MAX_BYTES


def test_upload_ad_video_is_registered():
    from meta_ads_mcp.core.server import mcp_server
    from meta_ads_mcp.core import ads  # noqa: F401

    names = [tool.name for tool in mcp_server._tool_manager.list_tools()]
    assert "upload_ad_video" in names
