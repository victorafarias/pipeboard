"""Smoke-test a streamable-HTTP MCP server: initialize + tools/list.

Usage:
  python scripts/smoke_mcp.py --url http://localhost:8080 --token YOUR_TOKEN
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

import requests


def rpc(url: str, token: str, method: str, params: dict | None = None, session_id: str | None = None):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }
    endpoint = url.rstrip("/")
    if not endpoint.endswith("/mcp"):
        endpoint = endpoint + "/mcp"
    response = requests.post(endpoint, headers=headers, json=body, timeout=30)
    return response


def parse_payload(response: requests.Response):
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        data_lines = [
            line[6:]
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        if not data_lines:
            return None
        return json.loads(data_lines[-1])
    if response.text:
        return response.json()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an MCP streamable-HTTP server")
    parser.add_argument("--url", required=True, help="Base URL, with or without /mcp")
    parser.add_argument("--token", required=True, help="Bearer token for HTTP auth")
    args = parser.parse_args()

    init = rpc(
        args.url,
        args.token,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke-mcp", "version": "1.0"},
        },
    )
    print(f"initialize HTTP {init.status_code}")
    if init.status_code == 401:
        print(init.text)
        return 1
    session_id = init.headers.get("mcp-session-id")
    payload = parse_payload(init)
    if payload:
        print(json.dumps(payload, indent=2)[:2000])

    listed = rpc(args.url, args.token, "tools/list", {}, session_id=session_id)
    print(f"tools/list HTTP {listed.status_code}")
    listed_payload = parse_payload(listed)
    if not listed_payload:
        print(listed.text[:2000])
        return 1
    tools = ((listed_payload.get("result") or {}).get("tools")) or []
    names = [t.get("name") for t in tools]
    print(f"{len(names)} tools:")
    for name in names:
        print(f"  - {name}")
    if not names:
        print("No tools returned")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
