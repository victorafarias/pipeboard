"""Logging and constants for Meta Posts MCP."""

import logging
import os
import pathlib
import platform
import sys

from dotenv import load_dotenv

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

APP_NAME = "meta-posts-mcp"

# Permissions required to publish organic Facebook/Instagram content.
# Used by --login and get_login_link. Broader than the ads-only AUTH_SCOPE.
POSTS_AUTH_SCOPE = (
    "public_profile,pages_show_list,pages_read_engagement,pages_manage_posts,"
    "pages_manage_engagement,pages_read_user_content,business_management,"
    "instagram_basic,instagram_content_publish,instagram_manage_comments,"
    "instagram_manage_insights,read_insights"
)


def _app_data_dir() -> pathlib.Path:
    if platform.system() == "Windows":
        base_path = pathlib.Path(os.environ.get("APPDATA", ""))
    elif platform.system() == "Darwin":
        base_path = pathlib.Path.home() / "Library" / "Application Support"
    else:
        base_path = pathlib.Path.home() / ".config"
    log_dir = base_path / APP_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging():
    log_file = _app_data_dir() / "meta_posts_debug.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=str(log_file),
        filemode="a",
    )
    named = logging.getLogger(APP_NAME)
    named.setLevel(logging.DEBUG)
    named.info("Logging initialized. Log file: %s", log_file)
    return named


logger = setup_logging()

using_direct_token = bool(os.environ.get("META_ACCESS_TOKEN", ""))
if not using_direct_token:
    if not os.environ.get("META_APP_ID"):
        print("WARNING: META_APP_ID is not set.", file=sys.stderr)
        print("RECOMMENDED: Set META_ACCESS_TOKEN from your Meta app.", file=sys.stderr)
    if not os.environ.get("META_APP_SECRET"):
        print(
            "WARNING: META_APP_SECRET is not set (needed only to exchange a short-lived token).",
            file=sys.stderr,
        )
