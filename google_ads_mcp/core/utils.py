"""Utility functions for Google Ads MCP."""

import logging
import os
import pathlib
import platform
import sys

from dotenv import load_dotenv

# Load the repo-root .env even when the process cwd is not the project.
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

APP_NAME = "google-ads-mcp"


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
    log_file = _app_data_dir() / "google_ads_debug.log"
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

using_refresh_token = bool(os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", ""))
if not using_refresh_token:
    if not os.environ.get("GOOGLE_ADS_CLIENT_ID"):
        print("WARNING: GOOGLE_ADS_CLIENT_ID is not set.", file=sys.stderr)
    if not os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"):
        print("WARNING: GOOGLE_ADS_DEVELOPER_TOKEN is not set.", file=sys.stderr)


def get_app_data_dir() -> pathlib.Path:
    return _app_data_dir()


def normalize_customer_id(customer_id: str) -> str:
    """Strip dashes/spaces so '123-456-7890' becomes '1234567890'."""
    if not customer_id:
        return ""
    return str(customer_id).replace("-", "").replace(" ", "").strip()


def currency_to_micros(amount) -> int:
    """Convert a currency amount (10.50) or already-micros int to micros.

    Values >= 1_000_000 are treated as micros already.
    """
    if amount is None or amount == "":
        return 0
    value = float(amount)
    if value >= 1_000_000:
        return int(value)
    return int(round(value * 1_000_000))


def micros_to_currency(micros) -> float:
    if micros is None:
        return 0.0
    return round(int(micros) / 1_000_000, 6)
