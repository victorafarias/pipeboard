"""Utility functions for Google Analytics MCP."""

import logging
import os
import pathlib
import platform
import sys

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "google-analytics-mcp"


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
    log_file = _app_data_dir() / "google_analytics_debug.log"
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

using_refresh_token = bool(os.environ.get("GOOGLE_ANALYTICS_REFRESH_TOKEN", ""))
if not using_refresh_token:
    if not os.environ.get("GOOGLE_ANALYTICS_CLIENT_ID"):
        print("WARNING: GOOGLE_ANALYTICS_CLIENT_ID is not set.", file=sys.stderr)
    if not os.environ.get("GOOGLE_ANALYTICS_CLIENT_SECRET"):
        print("WARNING: GOOGLE_ANALYTICS_CLIENT_SECRET is not set.", file=sys.stderr)


def get_app_data_dir() -> pathlib.Path:
    return _app_data_dir()


def construct_property_rn(property_value: int | str) -> str:
    """Return a property resource name: properties/{id}.

    Accepts a number, a numeric string, or a string already starting with
    ``properties/``.
    """
    property_num = None
    if isinstance(property_value, int):
        property_num = property_value
    elif isinstance(property_value, str):
        property_value = property_value.strip()
        if property_value.isdigit():
            property_num = int(property_value)
        elif property_value.startswith("properties/"):
            numeric_part = property_value.split("/")[-1]
            if numeric_part.isdigit():
                property_num = int(numeric_part)
    if property_num is None:
        raise ValueError(
            f"Invalid property ID: {property_value}. "
            "A valid property value is either a number or a string starting "
            "with 'properties/' and followed by a number."
        )
    return f"properties/{property_num}"
