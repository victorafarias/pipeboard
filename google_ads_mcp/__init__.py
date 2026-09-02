"""Google Ads MCP - Python package."""

from google_ads_mcp.core.server import main

__version__ = "1.0.0"

__all__ = ["main", "entrypoint"]


def entrypoint():
    """Main entry point for the package when invoked with uvx or console_scripts."""
    return main()
