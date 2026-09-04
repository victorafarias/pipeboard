"""Google Analytics MCP tools must put parsed JSON in structuredContent.result."""

import json

import pytest
from mcp.types import CallToolResult, TextContent


SAMPLE_ACCOUNTS = [
    {
        "account": "accounts/76191805",
        "display_name": "Victor Farias",
        "property_summaries": [
            {
                "property": "properties/501646837",
                "display_name": "jeronimo.app.br",
            }
        ],
    }
]


def _get_tool(name: str):
    from google_analytics_mcp.core.server import mcp_server

    manager = getattr(mcp_server, "_tool_manager", None)
    if manager is None:
        pytest.skip("FastMCP tool manager not available")
    return manager.get_tool(name)


def test_json_call_tool_result_list_is_not_stringified():
    from google_analytics_mcp.core.api import json_call_tool_result

    result = json_call_tool_result(SAMPLE_ACCOUNTS, list_result=True)

    assert isinstance(result.structuredContent["result"], list)
    assert result.structuredContent["result"][0]["account"] == "accounts/76191805"
    assert json.loads(result.content[0].text) == SAMPLE_ACCOUNTS


def test_json_call_tool_result_parses_json_text():
    from google_analytics_mcp.core.api import json_call_tool_result

    dumped = json.dumps(SAMPLE_ACCOUNTS, indent=2)
    result = json_call_tool_result(dumped, list_result=True)

    assert result.content[0].text == dumped
    assert isinstance(result.structuredContent["result"], list)
    assert result.structuredContent["result"] == SAMPLE_ACCOUNTS


def test_get_account_summaries_schema_result_is_array():
    from google_analytics_mcp.core import accounts  # noqa: F401

    tool = _get_tool("get_account_summaries")
    schema = tool.output_schema
    assert schema is not None
    assert schema["properties"]["result"]["type"] == "array"

    payload = CallToolResult(
        content=[TextContent(type="text", text=json.dumps(SAMPLE_ACCOUNTS, indent=2))],
        structuredContent={"result": SAMPLE_ACCOUNTS},
    )
    converted = tool.fn_metadata.convert_result(payload)
    assert isinstance(converted, CallToolResult)
    assert isinstance(converted.structuredContent["result"], list)
    assert json.loads(converted.content[0].text) == SAMPLE_ACCOUNTS


def test_get_account_summaries_rejects_stringified_result():
    from google_analytics_mcp.core import accounts  # noqa: F401
    from pydantic import ValidationError

    tool = _get_tool("get_account_summaries")
    dumped = json.dumps(SAMPLE_ACCOUNTS, indent=2)
    payload = CallToolResult(
        content=[TextContent(type="text", text=dumped)],
        structuredContent={"result": dumped},
    )
    with pytest.raises(ValidationError):
        tool.fn_metadata.convert_result(payload)


@pytest.mark.asyncio
async def test_ga_api_tool_list_survives_fastmcp_convert_result(monkeypatch):
    from google_analytics_mcp.core import accounts  # noqa: F401
    from google_analytics_mcp.core import api as ga_api

    monkeypatch.setattr(ga_api, "is_configured", lambda token=None: True)

    @ga_api.ga_api_tool
    async def fake_summaries(access_token=None) -> list[dict]:
        return SAMPLE_ACCOUNTS

    raw = await fake_summaries()
    assert isinstance(raw.structuredContent["result"], list)

    converted = _get_tool("get_account_summaries").fn_metadata.convert_result(raw)
    assert isinstance(converted.structuredContent["result"], list)
    assert converted.structuredContent["result"][0]["display_name"] == "Victor Farias"
    assert json.loads(converted.content[0].text)[0]["account"] == "accounts/76191805"
