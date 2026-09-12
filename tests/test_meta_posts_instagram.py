"""Instagram publishing tools (Graph API mocked)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from meta_posts_mcp.core.instagram import (
    instagram_create_carousel,
    instagram_create_photo,
    instagram_create_reel,
    instagram_create_story,
    instagram_list_accounts,
    instagram_publish_media,
)


def _parse(result):
    if isinstance(result, dict):
        return result
    return json.loads(result)


@pytest.mark.asyncio
async def test_instagram_list_accounts_maps_linked_ig_users():
    payload = {
        "data": [
            {
                "id": "page1",
                "name": "Shop",
                "access_token": "PAGE_SECRET",
                "instagram_business_account": {
                    "id": "1784",
                    "username": "shop",
                    "name": "Shop IG",
                    "followers_count": 10,
                },
            },
            {"id": "page2", "name": "No IG", "access_token": "OTHER_SECRET"},
        ]
    }
    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = payload
        result = _parse(await instagram_list_accounts(access_token="USER_TOKEN"))
    dumped = json.dumps(result)
    assert "PAGE_SECRET" not in dumped
    assert "OTHER_SECRET" not in dumped
    assert result["count"] == 1
    assert result["data"][0]["ig_user_id"] == "1784"
    assert result["data"][0]["facebook_page_id"] == "page1"


@pytest.mark.asyncio
async def test_instagram_create_photo_publishes_when_finished():
    async def fake_api(endpoint, token, params=None, method="GET"):
        if endpoint == "1784/media" and method == "POST":
            assert params["image_url"] == "https://cdn.example.com/p.jpg"
            assert params["caption"] == "New drop"
            return {"id": "container_1"}
        if endpoint == "container_1":
            return {"id": "container_1", "status_code": "FINISHED"}
        if endpoint == "1784/media_publish":
            assert params["creation_id"] == "container_1"
            return {"id": "media_99"}
        raise AssertionError(f"{method} {endpoint}")

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = fake_api
        result = _parse(
            await instagram_create_photo(
                ig_user_id="1784",
                image_url="https://cdn.example.com/p.jpg",
                caption="New drop",
                access_token="USER_TOKEN",
            )
        )
    assert result["published"] is True
    assert result["publish"]["id"] == "media_99"


@pytest.mark.asyncio
async def test_instagram_create_photo_returns_next_step_when_processing():
    async def fake_api(endpoint, token, params=None, method="GET"):
        if endpoint.endswith("/media"):
            return {"id": "container_busy"}
        if endpoint == "container_busy":
            return {"id": "container_busy", "status_code": "IN_PROGRESS"}
        raise AssertionError(endpoint)

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api, patch(
        "meta_posts_mcp.core.instagram.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        mock_api.side_effect = fake_api
        result = _parse(
            await instagram_create_photo(
                ig_user_id="1784",
                image_url="https://cdn.example.com/p.jpg",
                access_token="USER_TOKEN",
            )
        )
    assert result["published"] is False
    assert "instagram_publish_media" in result["next_step"]
    assert mock_sleep.await_count >= 1


@pytest.mark.asyncio
async def test_instagram_create_carousel_builds_children_then_parent():
    calls = []

    async def fake_api(endpoint, token, params=None, method="GET"):
        calls.append((endpoint, method, dict(params or {})))
        if endpoint == "1784/media" and params and params.get("is_carousel_item") == "true":
            url = params["image_url"]
            return {"id": f"child_{url[-5]}"}
        if endpoint == "1784/media" and params and params.get("media_type") == "CAROUSEL":
            assert params["children"] == "child_1,child_2"
            return {"id": "carousel_container"}
        if endpoint == "carousel_container":
            return {"id": "carousel_container", "status_code": "FINISHED"}
        if endpoint == "1784/media_publish":
            return {"id": "carousel_media"}
        raise AssertionError(f"{endpoint} {params}")

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = fake_api
        result = _parse(
            await instagram_create_carousel(
                ig_user_id="1784",
                image_urls=["https://cdn.example.com/a1.jpg", "https://cdn.example.com/a2.jpg"],
                caption="Two shots",
                access_token="USER_TOKEN",
            )
        )
    assert result["published"] is True
    assert result["child_container_ids"] == ["child_1", "child_2"]


@pytest.mark.asyncio
async def test_instagram_create_carousel_rejects_too_few_images():
    result = _parse(
        await instagram_create_carousel(
            ig_user_id="1784",
            image_urls=["https://cdn.example.com/only.jpg"],
            access_token="USER_TOKEN",
        )
    )
    assert "2–10" in result["error"]["message"]


@pytest.mark.asyncio
async def test_instagram_create_reel_and_story_validation():
    reel_bad = _parse(
        await instagram_create_reel(ig_user_id="1784", video_url="not-a-url", access_token="t")
    )
    assert "video_url must be a public" in reel_bad["error"]["message"]

    story_both = _parse(
        await instagram_create_story(
            ig_user_id="1784",
            image_url="https://cdn.example.com/a.jpg",
            video_url="https://cdn.example.com/a.mp4",
            access_token="t",
        )
    )
    assert "exactly one" in story_both["error"]["message"]


@pytest.mark.asyncio
async def test_instagram_publish_media_posts_creation_id():
    async def fake_api(endpoint, token, params=None, method="GET"):
        assert endpoint == "1784/media_publish"
        assert method == "POST"
        assert params["creation_id"] == "container_1"
        return {"id": "media_1"}

    with patch("meta_posts_mcp.core.graph.make_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = fake_api
        result = _parse(
            await instagram_publish_media(
                ig_user_id="1784", creation_id="container_1", access_token="USER_TOKEN"
            )
        )
    assert result["id"] == "media_1"
