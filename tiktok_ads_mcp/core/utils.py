"""Utility functions for TikTok Ads MCP."""

import logging
import os
import pathlib
import platform
import sys

from dotenv import load_dotenv

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

APP_NAME = "tiktok-ads-mcp"


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
    log_file = _app_data_dir() / "tiktok_ads_debug.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=str(log_file),
        filemode="a",
    )
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    logger.info(f"Logging initialized. Log file: {log_file}")
    logger.info(f"Platform: {platform.system()} {platform.release()}")
    return logger


logger = setup_logging()

if not os.environ.get("TIKTOK_ACCESS_TOKEN") and not os.environ.get("TIKTOK_REFRESH_TOKEN"):
    if not os.environ.get("TIKTOK_APP_ID"):
        print("WARNING: TIKTOK_APP_ID is not set.", file=sys.stderr)


def get_app_data_dir() -> pathlib.Path:
    return _app_data_dir()
