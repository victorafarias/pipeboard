"""FastMCP HTTP authentication for Google Ads MCP."""

import contextvars
import json
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .utils import logger

_auth_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "google_ads_auth_token", default=None
)


class FastMCPAuthIntegration:
    @staticmethod
    def set_auth_token(token: str) -> None:
        _auth_token.set(token)

    @staticmethod
    def get_auth_token() -> Optional[str]:
        return _auth_token.get(None)

    @staticmethod
    def clear_auth_token() -> None:
        _auth_token.set(None)

    @staticmethod
    def extract_token_from_headers(headers: dict) -> Optional[str]:
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        token = headers.get("X-GOOGLE-ADS-REFRESH-TOKEN") or headers.get(
            "x-google-ads-refresh-token"
        )
        if token:
            return token
        return None


def patch_fastmcp_server(mcp_server):
    original_run = mcp_server.run

    def patched_run(transport="stdio", **kwargs):
        if transport == "streamable-http":
            setup_http_auth_patching()
        return original_run(transport=transport, **kwargs)

    mcp_server.run = patched_run


def setup_http_auth_patching():
    from . import auth

    original_get_current_access_token = auth.get_current_access_token

    async def get_current_access_token_with_http_support() -> Optional[str]:
        context_token = FastMCPAuthIntegration.get_auth_token()
        if context_token:
            return context_token
        return await original_get_current_access_token()

    auth.get_current_access_token = get_current_access_token_with_http_support


class AuthInjectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_token = FastMCPAuthIntegration.extract_token_from_headers(dict(request.headers))
        if not auth_token:
            query_token = request.query_params.get("token")
            if query_token:
                auth_token = query_token.strip()
        if not auth_token:
            logger.warning(
                "HTTP Auth Middleware: rejecting request to %s — no Bearer token",
                request.url.path,
            )
            return Response(
                content=json.dumps(
                    {
                        "error": "Unauthorized",
                        "message": (
                            "Authentication required. Provide Authorization: Bearer "
                            "<google-ads-refresh-token> or ?token=."
                        ),
                    }
                ),
                status_code=401,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )
        FastMCPAuthIntegration.set_auth_token(auth_token)
        try:
            return await call_next(request)
        finally:
            FastMCPAuthIntegration.clear_auth_token()


def setup_starlette_middleware(app):
    if not app:
        return
    already_added = any(
        getattr(item, "cls", None) == AuthInjectionMiddleware for item in app.user_middleware
    )
    if not already_added:
        app.add_middleware(AuthInjectionMiddleware)


def setup_fastmcp_http_auth(mcp_server):
    patch_fastmcp_server(mcp_server)
    app_provider_methods = []
    if hasattr(mcp_server, "streamable_http_app") and callable(mcp_server.streamable_http_app):
        app_provider_methods.append("streamable_http_app")
    if hasattr(mcp_server, "sse_app") and callable(mcp_server.sse_app):
        app_provider_methods.append("sse_app")
    for method_name in app_provider_methods:
        original = getattr(mcp_server, method_name)

        def patched(*args, _original=original, **kwargs):
            app = _original(*args, **kwargs)
            if app:
                setup_starlette_middleware(app)
            return app

        setattr(mcp_server, method_name, patched)
