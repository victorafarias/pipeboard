"""Account-level Google Ads tools."""

from typing import Optional

from .api import google_api_tool, get_client, run_gaql
from .server import mcp_server
from .utils import normalize_customer_id


@mcp_server.tool()
@google_api_tool
async def list_customers(access_token: Optional[str] = None) -> dict:
    """List Google Ads customer IDs accessible with the current OAuth credentials."""
    client = get_client(access_token)
    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()
    customer_ids = []
    for resource_name in response.resource_names:
        cid = resource_name.split("/")[-1]
        customer_ids.append({"customer_id": cid, "resource_name": resource_name})
    return {"customers": customer_ids, "count": len(customer_ids)}


@mcp_server.tool()
@google_api_tool
async def get_account_info(customer_id: str, access_token: Optional[str] = None) -> dict:
    """Get details for a Google Ads customer account.

    Args:
        customer_id: Google Ads customer ID (with or without dashes)
    """
    cid = normalize_customer_id(customer_id)
    query = f"""
        SELECT
          customer.id,
          customer.descriptive_name,
          customer.currency_code,
          customer.time_zone,
          customer.status,
          customer.manager,
          customer.test_account
        FROM customer
        LIMIT 1
    """
    rows = run_gaql(cid, query, access_token)
    if not rows:
        return {"error": {"message": f"No account found for customer_id {cid}"}}
    return {"customer_id": cid, "account": rows[0]}


@mcp_server.tool()
@google_api_tool
async def execute_gaql_query(
    customer_id: str,
    query: str,
    access_token: Optional[str] = None,
) -> dict:
    """Run a raw GAQL query against a Google Ads customer.

    Args:
        customer_id: Google Ads customer ID (with or without dashes)
        query: GAQL query string (SELECT ... FROM ...)
    """
    cid = normalize_customer_id(customer_id)
    rows = run_gaql(cid, query, access_token)
    return {"customer_id": cid, "row_count": len(rows), "results": rows}
