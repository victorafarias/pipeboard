"""Image and video upload tools for TikTok Ads."""

from typing import Optional
import os

from .api import tiktok_api_tool, make_api_request, McpToolError
from .server import mcp_server


@mcp_server.tool()
@tiktok_api_tool
async def upload_tiktok_image(
    advertiser_id: str,
    image_path: str,
    file_name: str = "",
    access_token: Optional[str] = None,
) -> dict:
    """Upload an image for TikTok ad creatives (jpg, png, webp).

    Args:
        advertiser_id: TikTok advertiser ID
        image_path: Local path to the image file
        file_name: Optional file name sent to TikTok
    """
    if not os.path.isfile(image_path):
        raise McpToolError(f"Image file not found: {image_path}")
    name = file_name or os.path.basename(image_path)
    with open(image_path, "rb") as fh:
        content = fh.read()
    files = {"file": (name, content)}
    data = {
        "advertiser_id": str(advertiser_id),
        "upload_type": "UPLOAD_BY_FILE",
        "file_name": name,
    }
    return await make_api_request(
        "POST",
        "file/image/ad/upload/",
        access_token,
        json_body=data,
        files=files,
    )


@mcp_server.tool()
@tiktok_api_tool
async def upload_tiktok_video(
    advertiser_id: str,
    video_path: str,
    file_name: str = "",
    access_token: Optional[str] = None,
) -> dict:
    """Upload a video for TikTok ad creatives (mp4/mov, ideally 9:16 and 5-60s).

    Args:
        advertiser_id: TikTok advertiser ID
        video_path: Local path to the video file
        file_name: Optional file name sent to TikTok
    """
    if not os.path.isfile(video_path):
        raise McpToolError(f"Video file not found: {video_path}")
    name = file_name or os.path.basename(video_path)
    with open(video_path, "rb") as fh:
        content = fh.read()
    files = {"video_file": (name, content)}
    data = {
        "advertiser_id": str(advertiser_id),
        "upload_type": "UPLOAD_BY_FILE",
        "file_name": name,
        "flaw_detect": True,
        "auto_fix_enabled": True,
    }
    return await make_api_request(
        "POST",
        "file/video/ad/upload/",
        access_token,
        json_body=data,
        files=files,
    )
