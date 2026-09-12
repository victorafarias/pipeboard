"""Verify Meta Posts MCP tools are registered and Graph helpers behave safely."""

import json

import pytest

from meta_posts_mcp.core.graph import redact_tokens, require_http_url, tool_error, validate_facebook_schedule
from meta_posts_mcp.core.graph import parse_unix_time


def _tool_names(server):
    manager = getattr(server, "_tool_manager", None)
    if manager is None:
        pytest.skip("FastMCP tool manager not available")
    tools = manager.list_tools()
    return sorted(t.name for t in tools)


def test_meta_posts_tools_registered():
    from meta_posts_mcp.core.server import mcp_server
    from meta_posts_mcp.core import authentication, facebook, instagram  # noqa: F401

    names = _tool_names(mcp_server)
    expected = {
        "facebook_list_pages",
        "facebook_create_post",
        "facebook_list_posts",
        "facebook_get_post",
        "facebook_delete_post",
        "facebook_list_comments",
        "facebook_reply_to_comment",
        "facebook_get_insights",
        "instagram_list_accounts",
        "instagram_create_photo",
        "instagram_create_carousel",
        "instagram_create_reel",
        "instagram_create_story",
        "instagram_get_container_status",
        "instagram_publish_media",
        "instagram_list_media",
        "instagram_get_media",
        "instagram_list_comments",
        "instagram_reply_to_comment",
        "instagram_get_insights",
        "get_login_link",
    }
    missing = expected - set(names)
    assert not missing, f"Missing Meta Posts tools: {missing}"


def test_redact_tokens_strips_access_token_keys():
    payload = {
        "id": "111",
        "name": "Shop",
        "access_token": "EAA_secret",
        "instagram_business_account": {
            "id": "1784",
            "access_token": "nested_secret",
        },
        "data": [{"access_token": "page_secret", "id": "222"}],
    }
    redacted = redact_tokens(payload)
    dumped = json.dumps(redacted)
    assert "EAA_secret" not in dumped
    assert "nested_secret" not in dumped
    assert "page_secret" not in dumped
    assert redacted["id"] == "111"
    assert redacted["instagram_business_account"]["id"] == "1784"
    assert "access_token" not in redacted
    assert "access_token" not in redacted["data"][0]


def test_require_http_url_rejects_blank_and_non_http():
    assert require_http_url("", "image_url")["error"]["message"].startswith("image_url is required")
    assert "must be a public" in require_http_url("ftp://x/a.jpg", "image_url")["error"]["message"]
    assert "must be a public" in require_http_url("not-a-url", "photo_url")["error"]["message"]
    assert require_http_url("https://cdn.example.com/a.jpg", "image_url") is None
    assert require_http_url("http://cdn.example.com/a.jpg", "image_url") is None


def test_parse_unix_time_iso_and_digits():
    unix, err = parse_unix_time("1700000000")
    assert err is None
    assert unix == 1700000000
    unix, err = parse_unix_time("2026-09-13T09:00:00-03:00")
    assert err is None
    assert unix > 1_700_000_000
    unix, err = parse_unix_time("not-a-date")
    assert unix is None
    assert "scheduled_publish_time" in err["error"]["message"]


def test_validate_facebook_schedule_window():
    now = 1_800_000_000
    too_soon = validate_facebook_schedule(now + 60, now=now)
    assert too_soon is not None
    too_late = validate_facebook_schedule(now + 80 * 24 * 60 * 60, now=now)
    assert too_late is not None
    ok = validate_facebook_schedule(now + 3600, now=now)
    assert ok is None


def test_tool_error_shape():
    err = tool_error("page_id is required", example="page_id='123'")
    assert err["error"]["message"] == "page_id is required"
    assert err["error"]["example"] == "page_id='123'"
