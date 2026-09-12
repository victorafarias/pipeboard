"""Instagram professional-account organic publishing and engagement tools."""

import asyncio
from typing import List, Optional

from meta_ads_mcp.core.api import meta_api_tool

from .graph import graph_request, require_http_url, tool_error
from .server import mcp_server
from .utils import logger

_CONTAINER_READY = "FINISHED"
_CONTAINER_FAILED = {"ERROR", "EXPIRED"}
_MEDIA_FIELDS = (
    "id,caption,media_type,media_url,permalink,timestamp,username,"
    "like_count,comments_count,thumbnail_url"
)


async def _wait_for_container(
    container_id: str,
    access_token: str,
    max_attempts: int = 8,
    delay_seconds: float = 2.0,
) -> dict:
    last = {"id": container_id, "status_code": "IN_PROGRESS"}
    for attempt in range(max_attempts):
        status = await graph_request(
            container_id,
            access_token,
            {"fields": "id,status_code,status"},
        )
        if "error" in status:
            return status
        last = status
        code = str(status.get("status_code") or "").upper()
        if code == _CONTAINER_READY:
            return status
        if code in _CONTAINER_FAILED:
            return status
        if attempt < max_attempts - 1:
            logger.debug(
                "Instagram container %s status=%s attempt=%s",
                container_id,
                code or "unknown",
                attempt + 1,
            )
            await asyncio.sleep(delay_seconds)
    last["hint"] = (
        "Container is still processing. Call instagram_get_container_status "
        "until status_code is FINISHED, then instagram_publish_media."
    )
    return last


async def _publish_if_ready(
    ig_user_id: str,
    container: dict,
    access_token: str,
    publish: bool,
) -> dict:
    container_id = container.get("id")
    result = {"container": container, "ig_user_id": ig_user_id}
    if not publish:
        result["published"] = False
        result["next_step"] = (
            "Call instagram_publish_media(ig_user_id=..., creation_id='{id}') "
            "when you want it live."
        ).format(id=container_id)
        return result
    if not container_id:
        return container
    if "error" in container:
        return container

    ready = await _wait_for_container(container_id, access_token)
    result["container_status"] = ready
    if "error" in ready:
        return result
    code = str(ready.get("status_code") or "").upper()
    if code != _CONTAINER_READY:
        result["published"] = False
        result["next_step"] = (
            "Media is not FINISHED yet. Poll instagram_get_container_status "
            f"with container_id='{container_id}', then instagram_publish_media."
        )
        return result

    published = await graph_request(
        f"{ig_user_id}/media_publish",
        access_token,
        {"creation_id": container_id},
        method="POST",
    )
    result["publish"] = published
    result["published"] = "error" not in published
    return result


@mcp_server.tool()
@meta_api_tool
async def instagram_list_accounts(access_token: Optional[str] = None, limit: int = 50) -> dict:
    """List Instagram professional accounts linked to Pages the user manages.

    Args:
        access_token: Meta API access token (optional — uses cached token if omitted)
        limit: Maximum Pages to inspect (default: 50)

    Example:
        instagram_list_accounts()
    """
    pages = await graph_request(
        "me/accounts",
        access_token,
        {
            "fields": "id,name,instagram_business_account{id,username,name,followers_count,profile_picture_url}",
            "limit": limit,
        },
    )
    if "error" in pages:
        return pages
    accounts = []
    for page in pages.get("data") or []:
        ig = page.get("instagram_business_account")
        if not ig:
            continue
        accounts.append(
            {
                "ig_user_id": ig.get("id"),
                "username": ig.get("username"),
                "name": ig.get("name"),
                "followers_count": ig.get("followers_count"),
                "facebook_page_id": page.get("id"),
                "facebook_page_name": page.get("name"),
            }
        )
    return {"data": accounts, "count": len(accounts)}


@mcp_server.tool()
@meta_api_tool
async def instagram_create_photo(
    ig_user_id: str,
    image_url: str,
    caption: str = "",
    publish: bool = True,
    access_token: Optional[str] = None,
) -> dict:
    """Create an Instagram feed photo. Image URL must be publicly fetchable by Meta.

    Instagram publishing is two Graph calls: create a container, then publish.
    When publish=true (default), this tool does both if the container is ready.
    Reels/carousels that are still transcoding return the container id to poll.

    Args:
        ig_user_id: Instagram professional account ID (from instagram_list_accounts)
        image_url: Public JPEG/PNG URL
        caption: Optional caption
        publish: If true, publish as soon as the container is FINISHED (default: true)
        access_token: Meta API access token (optional)

    Example:
        instagram_create_photo(ig_user_id="1784...", image_url="https://cdn.example.com/p.jpg", caption="New drop")
    """
    if not ig_user_id:
        return tool_error("ig_user_id is required", example="Use instagram_list_accounts() first")
    url_error = require_http_url(image_url, "image_url")
    if url_error:
        return url_error

    params = {"image_url": image_url.strip()}
    if caption:
        params["caption"] = caption
    container = await graph_request(f"{ig_user_id}/media", access_token, params, method="POST")
    if "error" in container:
        return container
    return await _publish_if_ready(ig_user_id, container, access_token, publish)


@mcp_server.tool()
@meta_api_tool
async def instagram_create_carousel(
    ig_user_id: str,
    image_urls: List[str],
    caption: str = "",
    publish: bool = True,
    access_token: Optional[str] = None,
) -> dict:
    """Create an Instagram carousel (2–10 public image URLs).

    Args:
        ig_user_id: Instagram professional account ID
        image_urls: 2–10 publicly fetchable image URLs
        caption: Optional caption on the carousel
        publish: If true, publish when ready (default: true)
        access_token: Meta API access token (optional)

    Example:
        instagram_create_carousel(ig_user_id="1784...", image_urls=["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg"])
    """
    if not ig_user_id:
        return tool_error("ig_user_id is required")
    urls = [str(u).strip() for u in (image_urls or []) if str(u).strip()]
    if len(urls) < 2 or len(urls) > 10:
        return tool_error(
            "image_urls must contain 2–10 public image URLs",
            received_count=len(urls),
        )

    child_ids = []
    for url in urls:
        url_error = require_http_url(url, "image_urls[]")
        if url_error:
            return url_error
        child = await graph_request(
            f"{ig_user_id}/media",
            access_token,
            {"image_url": url, "is_carousel_item": "true"},
            method="POST",
        )
        if "error" in child:
            return {"error": child["error"], "failed_image_url": url}
        child_id = child.get("id")
        if not child_id:
            return tool_error("Carousel item container did not return an id", details=child)
        child_ids.append(child_id)

    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
    }
    if caption:
        params["caption"] = caption
    container = await graph_request(f"{ig_user_id}/media", access_token, params, method="POST")
    if "error" in container:
        return container
    result = await _publish_if_ready(ig_user_id, container, access_token, publish)
    result["child_container_ids"] = child_ids
    return result


@mcp_server.tool()
@meta_api_tool
async def instagram_create_reel(
    ig_user_id: str,
    video_url: str,
    caption: str = "",
    cover_url: str = "",
    share_to_feed: bool = True,
    publish: bool = True,
    access_token: Optional[str] = None,
) -> dict:
    """Create an Instagram Reel from a public video URL.

    Reels usually need transcoding. If the container is not FINISHED before
    publish, the response includes next_step to poll and publish.

    Args:
        ig_user_id: Instagram professional account ID
        video_url: Public video URL
        caption: Optional caption
        cover_url: Optional public image URL for the cover
        share_to_feed: Also share the Reel to the feed (default: true)
        publish: If true, publish when the container is FINISHED (default: true)
        access_token: Meta API access token (optional)

    Example:
        instagram_create_reel(ig_user_id="1784...", video_url="https://cdn.example.com/reel.mp4", caption="Behind the scenes")
    """
    if not ig_user_id:
        return tool_error("ig_user_id is required")
    url_error = require_http_url(video_url, "video_url")
    if url_error:
        return url_error

    params = {
        "media_type": "REELS",
        "video_url": video_url.strip(),
        "share_to_feed": "true" if share_to_feed else "false",
    }
    if caption:
        params["caption"] = caption
    if cover_url:
        cover_error = require_http_url(cover_url, "cover_url")
        if cover_error:
            return cover_error
        params["cover_url"] = cover_url.strip()

    container = await graph_request(f"{ig_user_id}/media", access_token, params, method="POST")
    if "error" in container:
        return container
    return await _publish_if_ready(ig_user_id, container, access_token, publish)


@mcp_server.tool()
@meta_api_tool
async def instagram_create_story(
    ig_user_id: str,
    image_url: str = "",
    video_url: str = "",
    publish: bool = True,
    access_token: Optional[str] = None,
) -> dict:
    """Create an Instagram Story from a public image or video URL (not both).

    Args:
        ig_user_id: Instagram professional account ID
        image_url: Public image URL (mutually exclusive with video_url)
        video_url: Public video URL (mutually exclusive with image_url)
        publish: If true, publish when ready (default: true)
        access_token: Meta API access token (optional)

    Example:
        instagram_create_story(ig_user_id="1784...", image_url="https://cdn.example.com/story.jpg")
    """
    if not ig_user_id:
        return tool_error("ig_user_id is required")
    if bool(image_url) == bool(video_url):
        return tool_error(
            "Provide exactly one of image_url or video_url",
            example="instagram_create_story(ig_user_id='1784...', image_url='https://cdn.example.com/story.jpg')",
        )

    params = {"media_type": "STORIES"}
    if image_url:
        url_error = require_http_url(image_url, "image_url")
        if url_error:
            return url_error
        params["image_url"] = image_url.strip()
    else:
        url_error = require_http_url(video_url, "video_url")
        if url_error:
            return url_error
        params["video_url"] = video_url.strip()

    container = await graph_request(f"{ig_user_id}/media", access_token, params, method="POST")
    if "error" in container:
        return container
    return await _publish_if_ready(ig_user_id, container, access_token, publish)


@mcp_server.tool()
@meta_api_tool
async def instagram_get_container_status(
    container_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Check an Instagram media container (IN_PROGRESS, FINISHED, ERROR, EXPIRED).

    Args:
        container_id: Container ID returned by instagram_create_*
        access_token: Meta API access token (optional)

    Example:
        instagram_get_container_status(container_id="1788...")
    """
    if not container_id:
        return tool_error("container_id is required")
    return await graph_request(container_id, access_token, {"fields": "id,status_code,status"})


@mcp_server.tool()
@meta_api_tool
async def instagram_publish_media(
    ig_user_id: str,
    creation_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """Publish a finished Instagram media container to the account.

    Args:
        ig_user_id: Instagram professional account ID
        creation_id: Container ID whose status_code is FINISHED
        access_token: Meta API access token (optional)

    Example:
        instagram_publish_media(ig_user_id="1784...", creation_id="1788...")
    """
    if not ig_user_id:
        return tool_error("ig_user_id is required")
    if not creation_id:
        return tool_error("creation_id is required (the container id from instagram_create_*)")
    return await graph_request(
        f"{ig_user_id}/media_publish",
        access_token,
        {"creation_id": creation_id},
        method="POST",
    )


@mcp_server.tool()
@meta_api_tool
async def instagram_list_media(
    ig_user_id: str,
    limit: int = 25,
    access_token: Optional[str] = None,
) -> dict:
    """List recent Instagram media on a professional account.

    Args:
        ig_user_id: Instagram professional account ID
        limit: Maximum items to return (default: 25)
        access_token: Meta API access token (optional)

    Example:
        instagram_list_media(ig_user_id="1784...")
    """
    if not ig_user_id:
        return tool_error("ig_user_id is required")
    return await graph_request(
        f"{ig_user_id}/media",
        access_token,
        {"fields": _MEDIA_FIELDS, "limit": limit},
    )


@mcp_server.tool()
@meta_api_tool
async def instagram_get_media(media_id: str, access_token: Optional[str] = None) -> dict:
    """Get a single Instagram media object.

    Args:
        media_id: Instagram media ID
        access_token: Meta API access token (optional)

    Example:
        instagram_get_media(media_id="1790...")
    """
    if not media_id:
        return tool_error("media_id is required")
    return await graph_request(media_id, access_token, {"fields": _MEDIA_FIELDS})


@mcp_server.tool()
@meta_api_tool
async def instagram_list_comments(
    media_id: str,
    limit: int = 25,
    access_token: Optional[str] = None,
) -> dict:
    """List comments on an Instagram media object.

    Args:
        media_id: Instagram media ID
        limit: Maximum comments to return (default: 25)
        access_token: Meta API access token (optional)

    Example:
        instagram_list_comments(media_id="1790...")
    """
    if not media_id:
        return tool_error("media_id is required")
    return await graph_request(
        f"{media_id}/comments",
        access_token,
        {"fields": "id,text,timestamp,username,like_count", "limit": limit},
    )


@mcp_server.tool()
@meta_api_tool
async def instagram_reply_to_comment(
    comment_id: str,
    message: str,
    access_token: Optional[str] = None,
) -> dict:
    """Reply to an Instagram comment.

    Args:
        comment_id: Comment ID
        message: Reply text
        access_token: Meta API access token (optional)

    Example:
        instagram_reply_to_comment(comment_id="1792...", message="Obrigado!")
    """
    if not comment_id:
        return tool_error("comment_id is required")
    if not message:
        return tool_error("message is required")
    return await graph_request(
        f"{comment_id}/replies",
        access_token,
        {"message": message},
        method="POST",
    )


@mcp_server.tool()
@meta_api_tool
async def instagram_get_insights(
    object_id: str,
    metrics: str = "impressions,reach,engagement",
    period: str = "day",
    access_token: Optional[str] = None,
) -> dict:
    """Get insights for an Instagram professional account or media object.

    Args:
        object_id: ig_user_id or media ID
        metrics: Comma-separated metric names (default: impressions,reach,engagement)
        period: day, week, days_28, or lifetime (media-level metrics often use lifetime)
        access_token: Meta API access token (optional)

    Example:
        instagram_get_insights(object_id="1784...")
        instagram_get_insights(object_id="1790...", metrics="impressions,reach,saved", period="lifetime")
    """
    if not object_id:
        return tool_error("object_id is required (ig_user_id or media ID)")
    return await graph_request(
        f"{object_id}/insights",
        access_token,
        {"metric": metrics, "period": period},
    )
