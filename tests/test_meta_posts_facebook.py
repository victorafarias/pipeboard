"""Facebook Page publishing tools (Graph API mocked)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from meta_posts_mcp.core.facebook import (
    facebook_create_post,
    facebook_delete_post,
    facebook_list_pages,
    facebook_list_posts,
)


def _parse(result):
    if isinstance(result, dict):
        return result
    return json.loads(result)


@pytest.mark.asyncio
async def test_facebook_list_pages_redacts_page_tokens():
    graph_payload = {
        "data": [
            {
                "id": "111",
                "name": "Shop",
                "access_token": "PAGE_TOKEN_SECRET",
                "instagram_business_account": {"id": "1784", "username": "shop"},
            }
        ]
    }
    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = graph_payload
        result = _parse(await facebook_list_pages(access_token="USER_TOKEN"))
    dumped = json.dumps(result)
    assert "PAGE_TOKEN_SECRET" not in dumped
    assert result["data"][0]["id"] == "111"
    assert result["data"][0]["name"] == "Shop"
    assert "access_token" not in result["data"][0]


@pytest.mark.asyncio
async def test_facebook_create_text_post_uses_feed_and_page_token():
    async def fake_api(endpoint, token, params=None, method="GET"):
        if endpoint == "111" and method == "GET":
            return {"id": "111", "name": "Shop", "access_token": "PAGE_TOKEN"}
        if endpoint == "111/feed" and method == "POST":
            assert token == "PAGE_TOKEN"
            assert params["message"] == "Hello shop"
            assert params["published"] == "true"
            return {"id": "111_999"}
        raise AssertionError(f"unexpected {method} {endpoint}")

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = fake_api
        result = _parse(
            await facebook_create_post(page_id="111", message="Hello shop", access_token="USER_TOKEN")
        )
    assert result["id"] == "111_999"
    assert result["page_id"] == "111"
    assert "PAGE_TOKEN" not in json.dumps(result)


@pytest.mark.asyncio
async def test_facebook_create_photo_post_posts_to_photos():
    async def fake_api(endpoint, token, params=None, method="GET"):
        if endpoint == "111":
            return {"id": "111", "access_token": "PAGE_TOKEN"}
        if endpoint == "111/photos":
            assert params["url"] == "https://cdn.example.com/p.jpg"
            assert params["caption"] == "New drop"
            return {"id": "photo_1", "post_id": "111_1"}
        raise AssertionError(endpoint)

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = fake_api
        result = _parse(
            await facebook_create_post(
                page_id="111",
                message="New drop",
                photo_url="https://cdn.example.com/p.jpg",
                access_token="USER_TOKEN",
            )
        )
    assert result["id"] == "photo_1"


@pytest.mark.asyncio
async def test_facebook_create_post_rejects_mixed_media_and_missing_page():
    missing = _parse(await facebook_create_post(page_id="", message="x", access_token="t"))
    assert "page_id is required" in missing["error"]["message"]

    mixed = _parse(
        await facebook_create_post(
            page_id="111",
            photo_url="https://cdn.example.com/p.jpg",
            video_url="https://cdn.example.com/v.mp4",
            access_token="t",
        )
    )
    assert "only one of" in mixed["error"]["message"]

    empty = _parse(await facebook_create_post(page_id="111", access_token="t"))
    assert "needs message" in empty["error"]["message"]


@pytest.mark.asyncio
async def test_facebook_create_post_schedules_unpublished():
    async def fake_api(endpoint, token, params=None, method="GET"):
        if endpoint == "111":
            return {"id": "111", "access_token": "PAGE_TOKEN"}
        if endpoint == "111/feed":
            assert params["published"] == "false"
            assert isinstance(params["scheduled_publish_time"], int)
            return {"id": "111_sched"}
        raise AssertionError(endpoint)

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = fake_api
        with patch("meta_posts_mcp.core.graph.time.time", return_value=1_800_000_000):
            result = _parse(
                await facebook_create_post(
                    page_id="111",
                    message="Later",
                    scheduled_publish_time=str(1_800_000_000 + 3600),
                    access_token="USER_TOKEN",
                )
            )
    assert result["id"] == "111_sched"
    assert result["published"] is False


@pytest.mark.asyncio
async def test_facebook_list_posts_and_delete():
    async def fake_api(endpoint, token, params=None, method="GET"):
        if endpoint == "111" and method == "GET":
            return {"id": "111", "access_token": "PAGE_TOKEN"}
        if endpoint == "111/posts":
            return {"data": [{"id": "111_1", "message": "Hi"}]}
        if endpoint == "111_1" and method == "DELETE":
            return {"success": True}
        raise AssertionError(f"{method} {endpoint}")

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = fake_api
        listed = _parse(await facebook_list_posts(page_id="111", access_token="USER_TOKEN"))
        deleted = _parse(await facebook_delete_post(post_id="111_1", access_token="USER_TOKEN"))
    assert listed["data"][0]["id"] == "111_1"
    assert deleted["success"] is True
