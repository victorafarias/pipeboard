"""Ensure Google Analytics MCP tools expose string output schemas."""

import json

import pytest


def _get_tool(name: str):
    from google_analytics_mcp.core.server import mcp_server

    manager = getattr(mcp_server, "_tool_manager", None)
    if manager is None:
        pytest.skip("FastMCP tool manager not available")
    return manager.get_tool(name)


def test_get_account_summaries_output_schema_is_string():
    from google_analytics_mcp.core import accounts  # noqa: F401

    tool = _get_tool("get_account_summaries")
    schema = tool.output_schema
    assert schema is not None
    assert schema["properties"]["result"]["type"] == "string"

    sample = json.dumps([{"account": "accounts/1", "display_name": "Test"}], indent=2)
    converted = tool.fn_metadata.convert_result(sample)
    assert converted is not None


@pytest.mark.parametrize(
    "tool_name",
    [
        "get_property_details",
        "list_google_ads_links",
        "list_property_annotations",
        "run_report",
        "run_realtime_report",
        "get_custom_dimensions_and_metrics",
        "run_funnel_report",
        "run_conversions_report",
    ],
)
def test_ga_api_tools_use_string_output_schema(tool_name: str):
    from google_analytics_mcp.core import (  # noqa: F401
        accounts,
        conversions,
        funnel,
        reports,
    )

    tool = _get_tool(tool_name)
    schema = tool.output_schema
    assert schema is not None
    assert schema["properties"]["result"]["type"] == "string"
