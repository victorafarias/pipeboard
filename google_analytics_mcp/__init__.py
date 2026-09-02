"""Google Analytics MCP — FastMCP server for the Google Analytics Admin and Data APIs.

Tool request construction and LLM argument hints are adapted from the official
Google Analytics MCP (Apache-2.0):
https://github.com/googleanalytics/google-analytics-mcp
"""

from google_analytics_mcp.core.server import main

__version__ = "1.0.0"

__all__ = ["main", "entrypoint"]


def entrypoint():
    """Main entry point for the package when invoked with uvx or console_scripts."""
    return main()
