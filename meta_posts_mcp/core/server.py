"""MCP server configuration for organic Facebook and Instagram posts."""

import argparse
import os
import sys

from mcp.server.fastmcp import FastMCP

from meta_ads_mcp.core.auth import login as login_auth
from meta_ads_mcp.core import auth as ads_auth

from .utils import POSTS_AUTH_SCOPE, logger

mcp_server = FastMCP("meta-posts")


def login_cli():
    """Run the local Meta OAuth flow with organic-publishing scopes."""
    logger.info("Starting Meta Posts CLI authentication flow")
    print("Starting Meta Posts CLI authentication flow...")
    original_scope = ads_auth.AUTH_SCOPE
    ads_auth.AUTH_SCOPE = POSTS_AUTH_SCOPE
    try:
        login_auth()
    finally:
        ads_auth.AUTH_SCOPE = original_scope


def main():
    logger.info("Meta Posts MCP server starting")
    parser = argparse.ArgumentParser(
        description=(
            "Meta Posts MCP Server — publish and manage organic Facebook Page "
            "and Instagram content via the Graph API"
        ),
        epilog=(
            "Examples:\n"
            "  python -m meta_posts_mcp\n"
            "  python -m meta_posts_mcp --login\n"
            "  python -m meta_posts_mcp --transport streamable-http --host 127.0.0.1 --port 8084\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--login", action="store_true", help="Authenticate with Meta and store the token")
    parser.add_argument("--app-id", type=str, help="Meta App ID (Client ID) for authentication")
    parser.add_argument("--version", action="store_true", help="Show the version of the package")
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport method: 'stdio' for MCP clients (default), 'streamable-http' for HTTP API access",
    )
    parser.add_argument("--port", type=int, default=8084, help="Port for Streamable HTTP transport")
    parser.add_argument("--host", type=str, default="localhost", help="Host for Streamable HTTP transport")
    parser.add_argument(
        "--sse-response",
        action="store_true",
        help="Use SSE response format instead of JSON",
    )
    args = parser.parse_args()

    from meta_ads_mcp.core.auth import auth_manager, meta_config

    env_app_id = os.environ.get("META_APP_ID")
    if args.app_id:
        auth_manager.app_id = args.app_id
        meta_config.set_app_id(args.app_id)
    elif env_app_id:
        auth_manager.app_id = env_app_id
        meta_config.set_app_id(env_app_id)

    if args.version:
        from meta_posts_mcp import __version__

        print(f"Meta Posts MCP v{__version__}")
        return 0

    if args.login:
        login_cli()
        return 0

    if os.environ.get("PIPEBOARD_API_TOKEN"):
        logger.warning("PIPEBOARD_API_TOKEN is set but is ignored by meta-posts-mcp.")
        print(
            "⚠️  PIPEBOARD_API_TOKEN is ignored by meta-posts-mcp.\n"
            "   Set META_ACCESS_TOKEN from a Meta app that has pages_manage_posts\n"
            "   and instagram_content_publish, or run: python -m meta_posts_mcp --login",
            file=sys.stderr,
        )

    from . import authentication, facebook, instagram  # noqa: F401

    if args.transport == "streamable-http":
        logger.info("Starting Meta Posts MCP with Streamable HTTP on %s:%s", args.host, args.port)
        mcp_server.settings.host = args.host
        mcp_server.settings.port = args.port
        mcp_server.settings.stateless_http = True
        mcp_server.settings.json_response = not args.sse_response
        mcp_server.settings.transport_security.enable_dns_rebinding_protection = False
        try:
            from meta_ads_mcp.core.http_auth_integration import setup_fastmcp_http_auth

            setup_fastmcp_http_auth(mcp_server)
            logger.info("FastMCP HTTP authentication integration setup successful")
        except Exception as exc:
            logger.error("Failed to setup HTTP authentication: %s", exc)
            print(f"⚠️  HTTP authentication setup failed: {exc}")
        print(f"Starting Meta Posts MCP server on {args.host}:{args.port}")
        print("Auth: Authorization: Bearer <meta-access-token>")
        try:
            mcp_server.run(transport="streamable-http")
        except Exception as exc:
            logger.error("Error starting Streamable HTTP server: %s", exc)
            print(f"Error: Failed to start Streamable HTTP server: {exc}")
            return 1
    else:
        logger.info("Starting Meta Posts MCP server with stdio transport")
        mcp_server.run(transport="stdio")
