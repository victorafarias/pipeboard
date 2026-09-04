"""Google Analytics API client wrapper and tool decorator.

Client factories wrap the official GAPIC libraries. Request construction for
reports is adapted from the official Google Analytics MCP (Apache-2.0):
https://github.com/googleanalytics/google-analytics-mcp
"""

from typing import Any, Callable, Optional, get_origin
import asyncio
import functools
import json

from mcp.types import CallToolResult, TextContent

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


def auth_required_payload() -> dict[str, Any]:
    return {
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
    }


def _parse_json_payload(value: Any) -> Any:
    """Keep native lists/dicts; parse JSON text so structuredContent is not a string."""
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def json_call_tool_result(value: Any, *, list_result: bool = False) -> CallToolResult:
    """Text in content stays JSON; structuredContent.result is the parsed value.

    FastMCP wraps list/dict annotations as ``{"result": ...}``. Clients that
    require ``result`` to be an array reject a second ``json.dumps`` pass.
    """
    parsed = _parse_json_payload(value)
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(parsed, indent=2)

    if list_result:
        structured = {"result": parsed if isinstance(parsed, list) else []}
        is_error = not isinstance(parsed, list)
    elif isinstance(parsed, dict):
        structured = parsed
        is_error = False
    else:
        structured = {"result": parsed}
        is_error = False

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured,
        isError=is_error,
    )


def _return_annotation_is_list(func: Callable) -> bool:
    return get_origin(getattr(func, "__annotations__", {}).get("return")) is list


def ga_api_tool(func: Callable):
    """Inject the Google Analytics refresh token and normalize errors to JSON."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        list_result = _return_annotation_is_list(func)
        try:
            if not kwargs.get("access_token"):
                token = await auth.get_current_access_token()
                if token:
                    kwargs["access_token"] = token
            if not is_configured(kwargs.get("access_token")):
                logger.warning("Google Analytics is not fully configured")
                return json_call_tool_result(auth_required_payload(), list_result=list_result)
            result = await func(*args, **kwargs)
            return json_call_tool_result(result, list_result=list_result)
        except McpToolError as e:
            message = str(e)
            try:
                parsed = json.loads(message)
            except Exception:
                parsed = {"error": {"message": message}}
            return json_call_tool_result(parsed, list_result=list_result)
        except Exception as e:
            logger.error(f"Google Analytics tool error in {func.__name__}: {e}", exc_info=True)
            return json_call_tool_result(
                {"error": {"message": str(e)}},
                list_result=list_result,
            )

    return wrapper
