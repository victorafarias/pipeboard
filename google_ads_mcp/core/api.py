"""Google Ads API client wrapper and tool decorator."""

from typing import Any, Callable, Dict, List, Optional
import functools
import json
import os

from . import auth
from .auth import get_google_ads_config, is_configured
from .utils import logger, normalize_customer_id

GOOGLE_ADS_API_VERSION = os.environ.get("GOOGLE_ADS_API_VERSION", "v25")


class McpToolError(Exception):
    pass


def _load_google_ads():
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException

    return GoogleAdsClient, GoogleAdsException


def proto_to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "_pb"):
        from google.protobuf.json_format import MessageToDict

        return MessageToDict(obj._pb, preserving_proto_field_name=True)
    if hasattr(obj, "__dict__") and not isinstance(obj, (str, bytes, int, float, bool)):
        try:
            from google.protobuf.json_format import MessageToDict

            return MessageToDict(obj, preserving_proto_field_name=True)
        except Exception:
            return str(obj)
    return obj


def serialize_search_rows(response) -> List[Dict[str, Any]]:
    rows = []
    for row in response:
        rows.append(proto_to_dict(row))
    return rows


def get_client(refresh_token: Optional[str] = None):
    GoogleAdsClient, _ = _load_google_ads()
    config = get_google_ads_config(refresh_token)
    if not config.get("refresh_token"):
        raise McpToolError("Google Ads refresh token is missing")
    if not config.get("developer_token"):
        raise McpToolError("GOOGLE_ADS_DEVELOPER_TOKEN is not set")
    if not config.get("client_id") or not config.get("client_secret"):
        raise McpToolError("GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET are not set")
    return GoogleAdsClient.load_from_dict(config, version=GOOGLE_ADS_API_VERSION)


def format_google_ads_exception(ex) -> Dict[str, Any]:
    details = []
    failure = getattr(ex, "failure", None)
    if failure is not None:
        for error in getattr(failure, "errors", []):
            details.append(
                {
                    "message": getattr(error, "message", str(error)),
                    "error_code": str(getattr(error, "error_code", "")),
                }
            )
    return {
        "error": {
            "message": str(ex),
            "details": details or [str(ex)],
        }
    }


def run_gaql(customer_id: str, query: str, refresh_token: Optional[str] = None) -> List[Dict[str, Any]]:
    _, GoogleAdsException = _load_google_ads()
    client = get_client(refresh_token)
    ga_service = client.get_service("GoogleAdsService")
    cid = normalize_customer_id(customer_id)
    try:
        response = ga_service.search(customer_id=cid, query=query)
        return serialize_search_rows(response)
    except GoogleAdsException as ex:
        raise McpToolError(json.dumps(format_google_ads_exception(ex))) from ex


def auth_required_payload() -> str:
    return json.dumps(
        {
            "error": {
                "message": "Authentication Required",
                "details": {
                    "description": "Google Ads credentials are missing.",
                    "required_env": [
                        "GOOGLE_ADS_DEVELOPER_TOKEN",
                        "GOOGLE_ADS_CLIENT_ID",
                        "GOOGLE_ADS_CLIENT_SECRET",
                        "GOOGLE_ADS_REFRESH_TOKEN",
                        "GOOGLE_ADS_LOGIN_CUSTOMER_ID (optional, MCC)",
                    ],
                    "http": "Pass the refresh token as Authorization: Bearer <token> or ?token=",
                    "action_required": "Call get_login_link or set GOOGLE_ADS_REFRESH_TOKEN",
                },
            }
        },
        indent=2,
    )


def google_api_tool(func: Callable):
    """Inject the Google Ads refresh token and normalize errors to JSON."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            if not kwargs.get("access_token"):
                token = await auth.get_current_access_token()
                if token:
                    kwargs["access_token"] = token
            if not is_configured(kwargs.get("access_token")):
                logger.warning("Google Ads is not fully configured")
                return auth_required_payload()
            result = await func(*args, **kwargs)
            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            if isinstance(result, str):
                return result
            return json.dumps({"data": result}, indent=2)
        except McpToolError as e:
            message = str(e)
            try:
                parsed = json.loads(message)
                return json.dumps(parsed, indent=2)
            except Exception:
                return json.dumps({"error": {"message": message}}, indent=2)
        except Exception as e:
            _, GoogleAdsException = _load_google_ads()
            if isinstance(e, GoogleAdsException):
                return json.dumps(format_google_ads_exception(e), indent=2)
            logger.error(f"Google Ads tool error in {func.__name__}: {e}", exc_info=True)
            return json.dumps({"error": {"message": str(e)}}, indent=2)

    return wrapper
