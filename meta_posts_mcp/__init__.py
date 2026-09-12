"""Meta Posts MCP — organic Facebook Page and Instagram publishing via Graph API."""

from meta_posts_mcp.core.server import main

__version__ = "1.0.0"

__all__ = ["main", "entrypoint"]


def entrypoint():
    """Console-script / uvx entry point."""
    return main()
