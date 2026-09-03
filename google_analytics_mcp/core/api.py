"""Google Analytics API client wrapper and tool decorator.

Client factories wrap the official GAPIC libraries. Request construction for
reports is adapted from the official Google Analytics MCP (Apache-2.0):
https://github.com/googleanalytics/google-analytics-mcp
"""

from typing import Any, Callable, Optional
import asyncio
import functools
import json

from . import auth
from .auth import GOOGLE_AUTH_SCOPE, get_google_analytics_config, is_configured
from .utils import logger


def _package_version() -> str:
    try:
        from google_analytics_mcp import __version__

        return __version__
    except Exception:
        return "unknown"


def _client_info():
    from google.api_core.gapic_v1.client_info import ClientInfo

    return ClientInfo(user_agent=f"google-analytics-mcp/{_package_version()}")


class McpToolError(Exception):
    pass


def _load_admin_beta():
    from google.analytics.admin_v1beta import AnalyticsAdminServiceClient

    return AnalyticsAdminServiceClient


def _load_admin_alpha():
    from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient

    return AnalyticsAdminServiceClient


def _load_data_beta():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    return BetaAnalyticsDataClient


def _load_data_alpha():
    from google.analytics.data_v1alpha import AlphaAnalyticsDataClient

    return AlphaAnalyticsDataClient


def proto_to_dict(obj: Any) -> Any:
    """Convert a proto-plus / protobuf message to a snake_case dict."""
    if obj is None:
        return None
    if hasattr(obj, "to_dict"):
        try:
            return type(obj).to_dict(
                obj, use_integers_for_enums=False, preserving_proto_field_name=True
            )
        except Exception:
            pass
    if hasattr(obj, "_pb"):
        from google.protobuf.json_format import MessageToDict

        return MessageToDict(obj._pb, preserving_proto_field_name=True)
    try:
        from google.protobuf.json_format import MessageToDict

        return MessageToDict(obj, preserving_proto_field_name=True)
    except Exception:
        return str(obj)


def get_credentials(refresh_token: Optional[str] = None):
    from google.oauth2.credentials import Credentials

    config = get_google_analytics_config(refresh_token)
    if not config.get("refresh_token"):
        raise McpToolError("Google Analytics refresh token is missing")
    if not config.get("client_id") or not config.get("client_secret"):
        raise McpToolError(
            "GOOGLE_ANALYTICS_CLIENT_ID / GOOGLE_ANALYTICS_CLIENT_SECRET are not set"
        )
    return Credentials(
        token=None,
        refresh_token=config["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        scopes=[GOOGLE_AUTH_SCOPE],
    )


def create_admin_client(refresh_token: Optional[str] = None):
    AnalyticsAdminServiceClient = _load_admin_beta()
    return AnalyticsAdminServiceClient(
        credentials=get_credentials(refresh_token),
        client_info=_client_info(),
    )


def create_admin_alpha_client(refresh_token: Optional[str] = None):
    AnalyticsAdminServiceClient = _load_admin_alpha()
    return AnalyticsAdminServiceClient(
        credentials=get_credentials(refresh_token),
        client_info=_client_info(),
    )


def create_data_client(refresh_token: Optional[str] = None):
    BetaAnalyticsDataClient = _load_data_beta()
    return BetaAnalyticsDataClient(
        credentials=get_credentials(refresh_token),
        client_info=_client_info(),
    )


def create_data_alpha_client(refresh_token: Optional[str] = None):
    AlphaAnalyticsDataClient = _load_data_alpha()
    return AlphaAnalyticsDataClient(
        credentials=get_credentials(refresh_token),
        client_info=_client_info(),
    )


async def run_sync(func, *args, **kwargs):
    """Run a blocking GAPIC call off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def auth_required_payload() -> str:
    return json.dumps(
        {
            "error": {
                "message": "Authentication Required",
                "details": {
                    "description": "Google Analytics credentials are missing.",
                    "required_env": [
                        "GOOGLE_ANALYTICS_CLIENT_ID",
                        "GOOGLE_ANALYTICS_CLIENT_SECRET",
                        "GOOGLE_ANALYTICS_REFRESH_TOKEN",
                    ],
                    "http": "Pass the refresh token as Authorization: Bearer <token> or ?token=",
                    "action_required": "Call get_login_link or set GOOGLE_ANALYTICS_REFRESH_TOKEN",
                },
            }
        },
        indent=2,
    )


def ga_api_tool(func: Callable):
    """Inject the Google Analytics refresh token and normalize errors to JSON."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            if not kwargs.get("access_token"):
                token = await auth.get_current_access_token()
                if token:
                    kwargs["access_token"] = token
            if not is_configured(kwargs.get("access_token")):
                logger.warning("Google Analytics is not fully configured")
                return auth_required_payload()
            result = await func(*args, **kwargs)
            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            if isinstance(result, str):
                return result
            if isinstance(result, list):
                return json.dumps(result, indent=2)
            return json.dumps({"data": result}, indent=2)
        except McpToolError as e:
            message = str(e)
            try:
                parsed = json.loads(message)
                return json.dumps(parsed, indent=2)
            except Exception:
                return json.dumps({"error": {"message": message}}, indent=2)
        except Exception as e:
            logger.error(f"Google Analytics tool error in {func.__name__}: {e}", exc_info=True)
            return json.dumps({"error": {"message": str(e)}}, indent=2)

    # ga_api_tool always serializes tool output to JSON text; keep FastMCP's output
    # schema aligned so structured validation does not expect list/dict objects.
    wrapper.__annotations__ = {
        **getattr(func, "__annotations__", {}),
        "return": str,
    }
    return wrapper
