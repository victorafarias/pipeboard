"""Tests for real Meta carousel creatives (link_data.child_attachments).

FLEX / image_hashes is NOT a carousel — these tests lock that distinction in.
"""

import json
from unittest.mock import patch

import pytest

from meta_ads_mcp.core.ads import (
    create_ad_creative,
    _normalize_carousel_child_attachments,
    _carousel_call_to_action,
)


THREE_CARDS = [
    {
        "link": "https://example.com/p1",
        "image_hash": "hash1",
        "name": "Product 1",
        "description": "$8.99",
    },
    {
        "link": "https://example.com/p2",
        "image_hash": "hash2",
        "name": "Product 2",
        "description": "$9.99",
    },
    {
        "link": "https://example.com/p3",
        "image_hash": "hash3",
        "name": "Product 3",
    },
]


def _mock_page_discovery():
    return patch(
        "meta_ads_mcp.core.ads._discover_pages_for_account",
        return_value={"success": True, "page_id": "987654321", "page_name": "Test Page"},
    )


def _error_text(result: str) -> str:
    data = json.loads(result)
    if "data" in data:
        data = json.loads(data["data"])
    err = data.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return err or ""


def _posted_creative(mock_api):
    return mock_api.call_args_list[0][0][2]


@pytest.mark.asyncio
async def test_carousel_posts_child_attachments_not_asset_feed_spec():
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [
            {"id": "creative_carousel"},
            {
                "id": "creative_carousel",
                "name": "Carousel",
                "object_story_spec": {
                    "page_id": "987654321",
                    "link_data": {"child_attachments": THREE_CARDS},
                },
            },
        ]

        result = await create_ad_creative(
            account_id="act_123",
            name="Carousel",
            page_id="987654321",
            link_url="https://example.com/",
            message="Shop the collection",
            headline="New arrivals",
            call_to_action_type="SHOP_NOW",
            child_attachments=THREE_CARDS,
            access_token="tok",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["format"] == "CAROUSEL"
        assert data["creative_id"] == "creative_carousel"

        posted = _posted_creative(mock_api)
        assert "asset_feed_spec" not in posted
        link_data = posted["object_story_spec"]["link_data"]
        assert link_data["link"] == "https://example.com/"
        assert link_data["message"] == "Shop the collection"
        assert link_data["name"] == "New arrivals"
        assert len(link_data["child_attachments"]) == 3
        assert link_data["child_attachments"][0]["image_hash"] == "hash1"
        assert link_data["child_attachments"][0]["name"] == "Product 1"
        assert link_data["child_attachments"][2]["link"] == "https://example.com/p3"
        assert link_data["call_to_action"] == {"type": "SHOP_NOW"}
        for card in link_data["child_attachments"]:
            assert card["call_to_action"] == {"type": "SHOP_NOW"}


@pytest.mark.asyncio
async def test_carousel_parent_link_defaults_from_first_card():
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        result = await create_ad_creative(
            account_id="act_123",
            page_id="987654321",
            message="Shop",
            child_attachments=THREE_CARDS,
            access_token="tok",
        )

        data = json.loads(result)
        assert data["success"] is True
        posted = _posted_creative(mock_api)
        assert posted["object_story_spec"]["link_data"]["link"] == "https://example.com/p1"


@pytest.mark.asyncio
async def test_carousel_card_inherits_parent_link_when_omitted():
    cards = [
        {"image_hash": "h1", "name": "A"},
        {"image_hash": "h2", "name": "B", "link": "https://example.com/b"},
    ]
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        result = await create_ad_creative(
            account_id="act_123",
            page_id="p",
            link_url="https://example.com/fallback",
            message="Shop",
            child_attachments=cards,
            access_token="tok",
        )

        data = json.loads(result)
        assert data["success"] is True
        attachments = _posted_creative(mock_api)["object_story_spec"]["link_data"]["child_attachments"]
        assert attachments[0]["link"] == "https://example.com/fallback"
        assert attachments[1]["link"] == "https://example.com/b"


@pytest.mark.asyncio
async def test_carousel_per_card_cta_overrides_parent():
    cards = [
        {"link": "https://example.com/a", "image_hash": "h1", "call_to_action_type": "LEARN_MORE"},
        {"link": "https://example.com/b", "image_hash": "h2"},
    ]
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        await create_ad_creative(
            account_id="act_123",
            page_id="p",
            message="Shop",
            call_to_action_type="SHOP_NOW",
            child_attachments=cards,
            access_token="tok",
        )

        attachments = _posted_creative(mock_api)["object_story_spec"]["link_data"]["child_attachments"]
        assert attachments[0]["call_to_action"] == {"type": "LEARN_MORE"}
        assert attachments[1]["call_to_action"] == {"type": "SHOP_NOW"}


@pytest.mark.asyncio
async def test_carousel_whatsapp_cta_has_no_value():
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        await create_ad_creative(
            account_id="act_123",
            page_id="p",
            message="Chat with us",
            call_to_action_type="WHATSAPP_MESSAGE",
            child_attachments=THREE_CARDS[:2],
            access_token="tok",
        )

        link_data = _posted_creative(mock_api)["object_story_spec"]["link_data"]
        assert link_data["call_to_action"] == {"type": "WHATSAPP_MESSAGE"}
        assert "value" not in link_data["call_to_action"]
        for card in link_data["child_attachments"]:
            assert card["call_to_action"] == {"type": "WHATSAPP_MESSAGE"}


@pytest.mark.asyncio
async def test_carousel_multi_share_flags():
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        await create_ad_creative(
            account_id="act_123",
            page_id="p",
            message="Shop",
            child_attachments=THREE_CARDS,
            multi_share_optimized=False,
            multi_share_end_card=False,
            access_token="tok",
        )

        link_data = _posted_creative(mock_api)["object_story_spec"]["link_data"]
        assert link_data["multi_share_optimized"] is False
        assert link_data["multi_share_end_card"] is False


@pytest.mark.asyncio
async def test_carousel_instagram_user_id_nested_in_object_story_spec():
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        await create_ad_creative(
            account_id="act_123",
            page_id="p",
            message="Shop",
            child_attachments=THREE_CARDS,
            instagram_actor_id="17841400000000000",
            access_token="tok",
        )

        spec = _posted_creative(mock_api)["object_story_spec"]
        assert spec["instagram_user_id"] == "17841400000000000"
        assert "instagram_actor_id" not in spec
        assert "child_attachments" in spec["link_data"]


@pytest.mark.asyncio
async def test_carousel_json_string_coercion():
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        result = await create_ad_creative(
            account_id="act_123",
            page_id="p",
            message="Shop",
            child_attachments=json.dumps(THREE_CARDS),  # type: ignore[arg-type]
            access_token="tok",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["format"] == "CAROUSEL"
        attachments = _posted_creative(mock_api)["object_story_spec"]["link_data"]["child_attachments"]
        assert len(attachments) == 3


@pytest.mark.asyncio
async def test_carousel_video_card_requires_thumbnail():
    cards = [
        {"link": "https://example.com/a", "video_id": "111"},
        {"link": "https://example.com/b", "image_hash": "h2"},
    ]
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Watch",
        child_attachments=cards,
        access_token="tok",
    )
    assert "video_id but no thumbnail" in _error_text(result)


@pytest.mark.asyncio
async def test_carousel_video_card_with_thumbnail_accepted():
    cards = [
        {"link": "https://example.com/a", "video_id": 111, "image_hash": "thumb1"},
        {"link": "https://example.com/b", "image_hash": "h2"},
    ]
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.side_effect = [{"id": "c1"}, {"id": "c1"}]

        result = await create_ad_creative(
            account_id="act_123",
            page_id="p",
            message="Watch",
            child_attachments=cards,
            access_token="tok",
        )

        data = json.loads(result)
        assert data["success"] is True
        first = _posted_creative(mock_api)["object_story_spec"]["link_data"]["child_attachments"][0]
        assert first["video_id"] == "111"
        assert first["image_hash"] == "thumb1"


@pytest.mark.asyncio
async def test_carousel_rejects_single_card():
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Shop",
        child_attachments=[{"link": "https://example.com/a", "image_hash": "h1"}],
        access_token="tok",
    )
    assert "2-10 child_attachments" in _error_text(result)


@pytest.mark.asyncio
async def test_carousel_rejects_eleven_cards():
    cards = [{"link": f"https://example.com/{i}", "image_hash": f"h{i}"} for i in range(11)]
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Shop",
        child_attachments=cards,
        access_token="tok",
    )
    assert "at most 10" in _error_text(result)


@pytest.mark.asyncio
async def test_carousel_rejects_card_without_media():
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Shop",
        child_attachments=[
            {"link": "https://example.com/a", "name": "No media"},
            {"link": "https://example.com/b", "image_hash": "h2"},
        ],
        access_token="tok",
    )
    assert "needs image_hash" in _error_text(result)


@pytest.mark.asyncio
async def test_carousel_requires_message():
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        child_attachments=THREE_CARDS,
        access_token="tok",
    )
    assert "require 'message'" in _error_text(result)


@pytest.mark.asyncio
async def test_carousel_cannot_mix_with_image_hash():
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Shop",
        image_hash="abc",
        child_attachments=THREE_CARDS,
        access_token="tok",
    )
    assert "Only one media source" in _error_text(result)


@pytest.mark.asyncio
async def test_carousel_cannot_mix_with_image_hashes():
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Shop",
        image_hashes=["h1", "h2"],
        child_attachments=THREE_CARDS,
        access_token="tok",
    )
    assert "Only one media source" in _error_text(result)


@pytest.mark.asyncio
async def test_carousel_cannot_mix_with_flex_optimization():
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Shop",
        optimization_type="DEGREES_OF_FREEDOM",
        child_attachments=THREE_CARDS,
        access_token="tok",
    )
    err = _error_text(result)
    assert "cannot be combined" in err
    assert "optimization_type" in err


@pytest.mark.asyncio
async def test_carousel_cannot_mix_with_plural_headlines():
    result = await create_ad_creative(
        account_id="act_123",
        page_id="p",
        message="Shop",
        headlines=["A", "B"],
        child_attachments=THREE_CARDS,
        access_token="tok",
    )
    err = _error_text(result)
    assert "cannot be combined" in err
    assert "headlines" in err


@pytest.mark.asyncio
async def test_flex_image_hashes_still_not_a_carousel():
    """Regression: multiple image_hashes must stay on asset_feed_spec, not child_attachments."""
    with patch("meta_ads_mcp.core.ads.make_api_request") as mock_api, _mock_page_discovery():
        mock_api.return_value = {"id": "flex1", "name": "Flex"}

        result = await create_ad_creative(
            account_id="act_123",
            page_id="p",
            link_url="https://example.com",
            message="Test",
            image_hashes=["h1", "h2", "h3"],
            access_token="tok",
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data.get("format") != "CAROUSEL"
        posted = _posted_creative(mock_api)
        assert "asset_feed_spec" in posted
        link_data = posted.get("object_story_spec", {}).get("link_data", {})
        assert "child_attachments" not in link_data


def test_normalize_helper_rejects_non_list():
    cards, err = _normalize_carousel_child_attachments(
        {"oops": True},  # type: ignore[arg-type]
        default_link=None,
        default_cta_type=None,
        lead_gen_form_id=None,
        phone_number=None,
    )
    assert cards is None
    assert "must be a list" in err


def test_whatsapp_cta_builder_omits_value():
    assert _carousel_call_to_action("WHATSAPP_MESSAGE") == {"type": "WHATSAPP_MESSAGE"}
    assert _carousel_call_to_action("SHOP_NOW") == {"type": "SHOP_NOW"}
    assert _carousel_call_to_action(
        "SIGN_UP", lead_gen_form_id="form1"
    ) == {"type": "SIGN_UP", "value": {"lead_gen_form_id": "form1"}}
    assert _carousel_call_to_action(
        "CALL_NOW", phone_number="+18005551234"
    ) == {"type": "CALL_NOW", "value": {"link": "tel:+18005551234"}}
