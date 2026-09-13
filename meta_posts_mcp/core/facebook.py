"""Facebook Page organic publishing and engagement tools."""

from typing import Optional

from meta_ads_mcp.core.api import meta_api_tool

from .graph import (
    graph_request,
    parse_unix_time,
    require_http_url,
    resolve_page_token,
    tool_error,
    validate_facebook_schedule,
)
from .server import mcp_server

_PAGE_LIST_FIELDS = (
    "id,name,category,fan_count,followers_count,tasks,"
    "instagram_business_account{id,username,name,followers_count}"
)
_POST_FIELDS = (
    "id,message,created_time,permalink_url,status_type,is_published,"
    "scheduled_publish_time,attachments{media_type,url,unshimmed_url}"
)


@mcp_server.tool()
@meta_api_tool
async def facebook_list_pages(access_token: Optional[str] = None, limit: int = 50) -> dict:
    """List Facebook Pages the current user can manage.

    Page access tokens are never returned. Use the page `id` with the other
    facebook_* tools.

    Args:
        access_token: Meta API access token (optional — uses cached token if omitted)
        limit: Maximum number of pages to return (default: 50)

    Example:
        facebook_list_pages()
        facebook_list_pages(limit=10)
    """
    data = await graph_request(
        "me/accounts",
        access_token,
        {"fields": _PAGE_LIST_FIELDS, "limit": limit},
    )
    return data


@mcp_server.tool()
@meta_api_tool
async def facebook_create_post(
    page_id: str,
    message: str = "",
    link: str = "",
    photo_url: str = "",
    video_url: str = "",
    scheduled_publish_time: str = "",
    published: bool = True,
    access_token: Optional[str] = None,
) -> dict:
    """Create an organic post on a Facebook Page (text, link, photo, or video).

    Provide exactly one media kind when attaching media: photo_url, video_url,
    or link. A text-only post needs `message`. Media URLs must be publicly
    fetchable by Meta.

    To schedule, pass scheduled_publish_time (ISO-8601 or unix). The post is
    then created unpublished and goes live at that time (10 minutes to 75 days
    ahead).

    Args:
        page_id: Facebook Page ID (from facebook_list_pages)
        message: Post text / caption
        link: Optional URL for a link post (feed). Do not combine with photo_url or video_url
        photo_url: Public image URL for a photo post
        video_url: Public video URL for a video post
        scheduled_publish_time: Unix timestamp or ISO-8601 datetime to schedule
        published: If false, create an unpublished/draft post (ignored when scheduling)
        access_token: Meta API access token (optional)

    Example:
        facebook_create_post(page_id="123", message="Hello from the shop")
        facebook_create_post(page_id="123", message="New drop", photo_url="https://cdn.example.com/p.jpg")
        facebook_create_post(page_id="123", message="Goes live later", scheduled_publish_time="2026-09-13T09:00:00-03:00")
    """
    if not page_id:
        return tool_error("page_id is required", example="page_id='123456789'")

    media_kinds = [name for name, value in (("photo_url", photo_url), ("video_url", video_url), ("link", link)) if value]
    if len(media_kinds) > 1:
        return tool_error(
            "Provide only one of photo_url, video_url, or link",
            received=media_kinds,
        )
    if not message and not media_kinds:
        return tool_error(
            "A post needs message, photo_url, video_url, or link",
            example="facebook_create_post(page_id='123', message='Hello')",
        )

    unix_ts, time_error = parse_unix_time(scheduled_publish_time)
    if time_error:
        return time_error
    if unix_ts is not None:
        schedule_error = validate_facebook_schedule(unix_ts)
        if schedule_error:
            return schedule_error
        published = False

    if photo_url:
        url_error = require_http_url(photo_url, "photo_url")
        if url_error:
            return url_error
    if video_url:
        url_error = require_http_url(video_url, "video_url")
        if url_error:
            return url_error
    if link:
        url_error = require_http_url(link, "link")
        if url_error:
            return url_error

    page_token, token_warning = await resolve_page_token(page_id, access_token)
    params = {}
    if message:
        params["message" if not photo_url else "caption"] = message
    if unix_ts is not None:
        params["scheduled_publish_time"] = unix_ts
        params["published"] = "false"
    else:
        params["published"] = "true" if published else "false"

    if photo_url:
        params["url"] = photo_url.strip()
        endpoint = f"{page_id}/photos"
    elif video_url:
        params["file_url"] = video_url.strip()
        if message:
            params["description"] = message
            params.pop("caption", None)
            params.pop("message", None)
        endpoint = f"{page_id}/videos"
    else:
        if message:
            params["message"] = message
        if link:
            params["link"] = link.strip()
        endpoint = f"{page_id}/feed"

    result = await graph_request(endpoint, page_token, params, method="POST")
    if token_warning and "error" in result:
        result["page_token_lookup"] = token_warning
    if "error" not in result:
        result["page_id"] = page_id
        if unix_ts is not None:
            result["scheduled_publish_time"] = unix_ts
            result["published"] = False
    return result


@mcp_server.tool()
@meta_api_tool
async def facebook_list_posts(
    page_id: str,
    limit: int = 25,
    include_unpublished: bool = False,
    access_token: Optional[str] = None,
) -> dict:
    """List recent posts on a Facebook Page.

    Args:
        page_id: Facebook Page ID
        limit: Maximum published posts to return (default: 25)
        include_unpublished: If true, also fetch scheduled/unpublished posts
        access_token: Meta API access token (optional)

    Example:
        facebook_list_posts(page_id="123")
        facebook_list_posts(page_id="123", include_unpublished=True)
    """
    if not page_id:
        return tool_error("page_id is required", example="page_id='123456789'")

    page_token, _ = await resolve_page_token(page_id, access_token)
    published = await graph_request(
        f"{page_id}/posts",
        page_token,
        {"fields": _POST_FIELDS, "limit": limit},
    )
    if not include_unpublished:
        return published

    scheduled = await graph_request(
        f"{page_id}/scheduled_posts",
        page_token,
        {"fields": _POST_FIELDS, "limit": limit},
    )
    return {
        "published": published,
        "unpublished_or_scheduled": scheduled,
    }


@mcp_server.tool()
@meta_api_tool
async def facebook_get_post(post_id: str, access_token: Optional[str] = None) -> dict:
    """Get a Facebook Page post by ID.

    Args:
        post_id: Post ID (`{page_id}_{post_id}` or the id returned by facebook_create_post)
        access_token: Meta API access token (optional)

    Example:
        facebook_get_post(post_id="123_456")
    """
    if not post_id:
        return tool_error("post_id is required", example="post_id='123456789_987654321'")
    return await graph_request(post_id, access_token, {"fields": _POST_FIELDS})


@mcp_server.tool()
@meta_api_tool
async def facebook_delete_post(post_id: str, access_token: Optional[str] = None) -> dict:
    """Delete a Facebook Page post. This cannot be undone.

    Args:
        post_id: Post ID to delete
        access_token: Meta API access token (optional)

    Example:
        facebook_delete_post(post_id="123_456")
    """
    if not post_id:
        return tool_error("post_id is required", example="post_id='123456789_987654321'")
    return await graph_request(post_id, access_token, method="DELETE")


@mcp_server.tool()
@meta_api_tool
async def facebook_list_comments(
    post_id: str,
    limit: int = 25,
    access_token: Optional[str] = None,
) -> dict:
    """List comments on a Facebook Page post.

    Args:
        post_id: Post ID
        limit: Maximum comments to return (default: 25)
        access_token: Meta API access token (optional)

    Example:
        facebook_list_comments(post_id="123_456")
    """
    if not post_id:
        return tool_error("post_id is required")
    return await graph_request(
        f"{post_id}/comments",
        access_token,
        {"fields": "id,from,message,created_time,comment_count,like_count", "limit": limit},
    )


@mcp_server.tool()
@meta_api_tool
async def facebook_reply_to_comment(
    comment_id: str,
    message: str,
    access_token: Optional[str] = None,
) -> dict:
    """Reply to a comment on a Facebook Page post.

    Args:
        comment_id: Comment ID to reply to
        message: Reply text
        access_token: Meta API access token (optional)

    Example:
        facebook_reply_to_comment(comment_id="789", message="Thanks for writing in!")
    """
    if not comment_id:
        return tool_error("comment_id is required")
    if not message:
        return tool_error("message is required")
    return await graph_request(
        f"{comment_id}/comments",
        access_token,
        {"message": message},
        method="POST",
    )


@mcp_server.tool()
@meta_api_tool
async def facebook_get_insights(
    object_id: str,
    metrics: str = "page_impressions,page_engaged_users",
    period: str = "day",
    access_token: Optional[str] = None,
) -> dict:
    """Get insights for a Facebook Page or post.

    Args:
        object_id: Page ID or post ID
        metrics: Comma-separated metric names (default: page_impressions,page_engaged_users)
        period: Aggregation period: day, week, days_28, or lifetime (default: day)
        access_token: Meta API access token (optional)

    Example:
        facebook_get_insights(object_id="123")
        facebook_get_insights(object_id="123_456", metrics="post_impressions,post_engaged_users", period="lifetime")
    """
    if not object_id:
        return tool_error("object_id is required (a Page ID or post ID)")
    return await graph_request(
        f"{object_id}/insights",
        access_token,
        {"metric": metrics, "period": period},
    )
