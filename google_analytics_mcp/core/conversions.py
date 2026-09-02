"""Conversions reporting tools for the Google Analytics Data API (alpha)."""

from typing import Any, Dict, List, Optional, Union

from .api import create_data_alpha_client, ga_api_tool, proto_to_dict, run_sync
from .report_hints import (
    get_date_ranges_hints,
    get_dimension_filter_hints,
    get_metric_filter_hints,
    get_order_bys_hints,
)
from .server import mcp_server
from .utils import construct_property_rn


def _run_conversions_report_description() -> str:
    return f"""Runs a Google Analytics Data API conversions report.

USE THIS TOOL INSTEAD OF `run_report` WHEN:
- You need to report specifically on conversions, ad performance, return on ad spend (ROAS), or attribution.
- You need to query specific conversion metrics (e.g., advertiserAdCost, returnOnAdSpendByInteractionDate, allConversionsByConversionDate, etc.).
- You need to apply a specific attribution model (e.g., DATA_DRIVEN or LAST_CLICK) to your data.
- The user's query explicitly asks about conversions, ad clicks, ad costs, or campaigns related to conversions.

See the conversions report guide at
https://developers.google.com/analytics/devguides/reporting/data/v1/conversions-api-basics
for details and examples.

Args:
    property_id: The Google Analytics property ID. Accepted formats are:
      - A number
      - A string consisting of 'properties/' followed by a number
    date_ranges: A list of date ranges to include in the report.
    dimensions: A list of dimensions to include in the report.
    metrics: A list of metrics to include in the report.
    conversion_spec: The specification for conversions reporting.
      Should include 'conversion_actions' (list of resource names) and
      'attribution_model'.
    dimension_filter: A Data API FilterExpression to apply to the dimensions.
    metric_filter: A Data API FilterExpression to apply to the metrics.
    order_bys: A list of Data API OrderBy objects.
    limit: The maximum number of rows to return in each response. Value must
      be a positive integer <= 250,000.
    offset: The row count of the start row. The first row is counted as row 0.
    currency_code: The currency code to use for currency values.
    return_property_quota: Whether to return property quota in the response.

## Hints for arguments

### Hints for `dimensions`

The `dimensions` list must consist solely of the following allowed standard dimensions:
- campaignName
- continent
- country
- defaultChannelGroup
- deviceCategory
- medium
- platform
- primaryChannelGroup
- source
- sourceMedium
- sourcePlatform
- subcontinent

### Hints for `metrics`

The `metrics` list must consist solely of the following allowed standard metrics:
- advertiserAdClicks
- advertiserAdCost
- advertiserAdCostPerAllConversionsByConversionDate
- advertiserAdCostPerAllConversionsByInteractionDate
- advertiserAdCostPerClick
- advertiserAdImpressions
- allConversionsByConversionDate
- allConversionsByInteractionDate
- returnOnAdSpendByConversionDate
- returnOnAdSpendByInteractionDate
- totalRevenueByConversionDate
- totalRevenueByInteractionDate

### Hints for `conversion_spec`

The `conversion_spec` argument is required for conversions reporting.
You can pass an empty list for `conversion_actions` if you want all conversion events.
Example:
{{
  "conversion_actions": ["conversionActions/12345"],
  "attribution_model": "DATA_DRIVEN"
}}
`attribution_model` is "DATA_DRIVEN" or "LAST_CLICK".

### Hints for `date_ranges`:
{get_date_ranges_hints()}

### Hints for `dimension_filter`:
{get_dimension_filter_hints()}

### Hints for `metric_filter`:
{get_metric_filter_hints()}

### Hints for `order_bys`:
{get_order_bys_hints()}
"""


@mcp_server.tool(description=_run_conversions_report_description())
@ga_api_tool
async def run_conversions_report(
    property_id: Union[int, str],
    date_ranges: List[Dict[str, Any]],
    dimensions: List[str],
    metrics: List[str],
    conversion_spec: Dict[str, Any],
    dimension_filter: Optional[Dict[str, Any]] = None,
    metric_filter: Optional[Dict[str, Any]] = None,
    order_bys: Optional[List[Dict[str, Any]]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    currency_code: Optional[str] = None,
    return_property_quota: bool = False,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Runs a Google Analytics Data API conversions report."""
    from google.analytics import data_v1alpha

    request = data_v1alpha.RunReportRequest(
        property=construct_property_rn(property_id),
        dimensions=[data_v1alpha.Dimension(name=dimension) for dimension in dimensions],
        metrics=[data_v1alpha.Metric(name=metric) for metric in metrics],
        date_ranges=[data_v1alpha.DateRange(dr) for dr in date_ranges],
        conversion_spec=data_v1alpha.ConversionSpec(conversion_spec),
        return_property_quota=return_property_quota,
    )

    if dimension_filter:
        request.dimension_filter = data_v1alpha.FilterExpression(dimension_filter)
    if metric_filter:
        request.metric_filter = data_v1alpha.FilterExpression(metric_filter)
    if order_bys:
        request.order_bys = [data_v1alpha.OrderBy(order_by) for order_by in order_bys]
    if limit:
        request.limit = limit
    if offset:
        request.offset = offset
    if currency_code:
        request.currency_code = currency_code

    def _sync_call():
        return create_data_alpha_client(access_token).run_report(request)

    response = await run_sync(_sync_call)
    return proto_to_dict(response)
