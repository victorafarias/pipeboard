"""MCP server configuration for TikTok Ads API."""

import argparse
import os
import sys

from mcp.server.fastmcp import FastMCP

from .auth import login as login_auth
from .utils import logger

mcp_server = FastMCP("tiktok-ads")


def login_cli():
    logger.info("Starting TikTok Ads CLI authentication flow")
    print("Starting TikTok Ads CLI authentication flow...")
    login_auth()


def main():
    logger.info("TikTok Ads MCP server starting")
    parser = argparse.ArgumentParser(
        description="TikTok Ads MCP Server - Model Context Protocol server for TikTok Marketing API"
    )
    parser.add_argument("--login", action="store_true", help="Authenticate with TikTok and store the token")
    parser.add_argument("--version", action="store_true", help="Show the version of the package")
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport method",
    )
    parser.add_argument("--port", type=int, default=8080, help="Port for Streamable HTTP transport")
    parser.add_argument("--host", type=str, default="localhost", help="Host for Streamable HTTP transport")
    parser.add_argument(
        "--sse-response",
        action="store_true",
        help="Use SSE response format instead of JSON",
    )
    args = parser.parse_args()

    if args.version:
        from tiktok_ads_mcp import __version__

        print(f"TikTok Ads MCP v{__version__}")
        return 0

    if args.login:
        login_cli()
        return 0

    if os.environ.get("PIPEBOARD_API_TOKEN"):
        logger.warning("PIPEBOARD_API_TOKEN is set but is ignored by tiktok-ads-mcp.")
        print(
            "⚠️  PIPEBOARD_API_TOKEN is ignored. Set TIKTOK_ACCESS_TOKEN / TIKTOK_REFRESH_TOKEN.",
            file=sys.stderr,
        )

    from . import accounts, campaigns, adgroups, ads, media, insights, targeting, authentication  # noqa: F401

    if args.transport == "streamable-http":
        logger.info(f"Starting TikTok Ads MCP with Streamable HTTP on {args.host}:{args.port}")
        mcp_server.settings.host = args.host
        mcp_server.settings.port = args.port
        mcp_server.settings.stateless_http = True
        mcp_server.settings.json_response = not args.sse_response
        mcp_server.settings.transport_security.enable_dns_rebinding_protection = False
        try:
            from .http_auth_integration import setup_fastmcp_http_auth

            setup_fastmcp_http_auth(mcp_server)
            logger.info("FastMCP HTTP authentication integration setup successful")
        except Exception as e:
            logger.error(f"Failed to setup HTTP authentication: {e}")
            print(f"⚠️  HTTP authentication setup failed: {e}")
        print(f"Starting TikTok Ads MCP server on {args.host}:{args.port}")
        print("Auth: Authorization: Bearer <tiktok-access-token>")
        try:
            mcp_server.run(transport="streamable-http")
        except Exception as e:
            logger.error(f"Error starting Streamable HTTP server: {e}")
            print(f"Error: Failed to start Streamable HTTP server: {e}")
            return 1
    else:
        logger.info("Starting TikTok Ads MCP server with stdio transport")
        mcp_server.run(transport="stdio")
