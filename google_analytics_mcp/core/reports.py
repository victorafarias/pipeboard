"""Core, realtime, and metadata reporting tools for the Google Analytics Data API."""

from typing import Any, Dict, List, Optional, Union

from .api import create_data_client, ga_api_tool, proto_to_dict, run_sync
from .report_hints import (
    get_date_ranges_hints,
    get_dimension_filter_hints,
    get_metric_filter_hints,
    get_order_bys_hints,
)
from .server import mcp_server
from .utils import construct_property_rn


def _run_report_description() -> str:
    return f"""Runs a Google Analytics Data API report.

Note that the reference docs at
https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta
all use camelCase field names, but field names passed to this method should
be in snake_case since the tool is using the protocol buffers (protobuf)
format. The protocol buffers for the Data API are available at
https://github.com/googleapis/googleapis/tree/master/google/analytics/data/v1beta.

Args:
    property_id: The Google Analytics property ID. Accepted formats are:
      - A number
      - A string consisting of 'properties/' followed by a number
    date_ranges: A list of date ranges
      (https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/DateRange)
      to include in the report.
    dimensions: A list of dimensions to include in the report.
    metrics: A list of metrics to include in the report.
    dimension_filter: A Data API FilterExpression
      (https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/FilterExpression)
      to apply to the dimensions. Don't use this for filtering metrics. Use
      metric_filter instead.
    metric_filter: A Data API FilterExpression to apply to the metrics. Don't
      use this for filtering dimensions. Use dimension_filter instead.
    order_bys: A list of Data API OrderBy objects to apply to the dimensions
      and metrics.
    limit: The maximum number of rows to return in each response. Value must
      be a positive integer <= 250,000.
    offset: The row count of the start row. The first row is counted as row 0.
    currency_code: The currency code to use for currency values. Must be in
      ISO4217 format, such as "AED", "USD", "JPY". If empty, the report uses
      the property's default currency.
    return_property_quota: Whether to return property quota in the response.

## Hints for arguments

### Hints for `dimensions`

The `dimensions` list must consist solely of either of the following:

1. Standard dimensions defined in the HTML table at
   https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema#dimensions.
   These dimensions are available to *every* property.
2. Custom dimensions for the `property_id`. Use the
   `get_custom_dimensions_and_metrics` tool to retrieve the list of
   custom dimensions for a property.

### Hints for `metrics`

The `metrics` list must consist solely of either of the following:

1. Standard metrics defined in the HTML table at
   https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema#metrics.
   These metrics are available to *every* property.
2. Custom metrics for the `property_id`. Use the
   `get_custom_dimensions_and_metrics` tool to retrieve the list of
   custom metrics for a property.

### Hints for `date_ranges`:
{get_date_ranges_hints()}

### Hints for `dimension_filter`:
{get_dimension_filter_hints()}

### Hints for `metric_filter`:
{get_metric_filter_hints()}

### Hints for `order_bys`:
{get_order_bys_hints()}
"""


def _run_realtime_report_description() -> str:
    return f"""Runs a Google Analytics Data API realtime report.

See
https://developers.google.com/analytics/devguides/reporting/data/v1/realtime-basics
for more information.

Args:
    property_id: The Google Analytics property ID. Accepted formats are:
      - A number
      - A string consisting of 'properties/' followed by a number
    dimensions: A list of dimensions to include in the report. Dimensions must
      be realtime dimensions.
    metrics: A list of metrics to include in the report. Metrics must be
      realtime metrics.
    dimension_filter: A Data API FilterExpression to apply to the dimensions.
    metric_filter: A Data API FilterExpression to apply to the metrics.
    order_bys: A list of Data API OrderBy objects.
    limit: The maximum number of rows to return in each response.
    offset: The row count of the start row. The first row is counted as row 0.
    return_property_quota: Whether to return realtime property quota in the response.

## Hints for arguments

### Hints for `dimensions`

The `dimensions` list must consist solely of either of the following:

1. Realtime standard dimensions defined in the HTML table at
   https://developers.google.com/analytics/devguides/reporting/data/v1/realtime-api-schema#dimensions.
   These dimensions are available to *every* property.
2. User-scoped custom dimensions for the `property_id`. Use the
   `get_custom_dimensions_and_metrics` tool to retrieve the list of
   custom dimensions for a property, and look for the custom
   dimensions with an `apiName` that begins with "customUser:".

### Hints for `metrics`

The `metrics` list must consist solely of the Realtime standard
metrics defined in the HTML table at
https://developers.google.com/analytics/devguides/reporting/data/v1/realtime-api-schema#metrics.
These metrics are available to *every* property.

Realtime reports can't use custom metrics.

### Hints for `dimension_filter`:
{get_dimension_filter_hints()}

### Hints for `metric_filter`:
{get_metric_filter_hints()}

### Hints for `order_bys`:
{get_order_bys_hints()}
"""


@mcp_server.tool(description=_run_report_description())
@ga_api_tool
async def run_report(
    property_id: Union[int, str],
    date_ranges: List[Dict[str, Any]],
    dimensions: List[str],
    metrics: List[str],
    dimension_filter: Optional[Dict[str, Any]] = None,
    metric_filter: Optional[Dict[str, Any]] = None,
    order_bys: Optional[List[Dict[str, Any]]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    currency_code: Optional[str] = None,
    return_property_quota: bool = False,
    access_token: Optional[str] = None,
) -> str:
    """Runs a Google Analytics Data API report."""
    from google.analytics import data_v1beta

    request = data_v1beta.RunReportRequest(
        property=construct_property_rn(property_id),
        dimensions=[data_v1beta.Dimension(name=dimension) for dimension in dimensions],
        metrics=[data_v1beta.Metric(name=metric) for metric in metrics],
        date_ranges=[data_v1beta.DateRange(dr) for dr in date_ranges],
        return_property_quota=return_property_quota,
    )

    if dimension_filter:
        request.dimension_filter = data_v1beta.FilterExpression(dimension_filter)
    if metric_filter:
        request.metric_filter = data_v1beta.FilterExpression(metric_filter)
    if order_bys:
        request.order_bys = [data_v1beta.OrderBy(order_by) for order_by in order_bys]
    if limit:
        request.limit = limit
    if offset:
        request.offset = offset
    if currency_code:
        request.currency_code = currency_code

    def _sync_call():
        return create_data_client(access_token).run_report(request)

    response = await run_sync(_sync_call)
    return proto_to_dict(response)


@mcp_server.tool(description=_run_realtime_report_description())
@ga_api_tool
async def run_realtime_report(
    property_id: Union[int, str],
    dimensions: List[str],
    metrics: List[str],
    dimension_filter: Optional[Dict[str, Any]] = None,
    metric_filter: Optional[Dict[str, Any]] = None,
    order_bys: Optional[List[Dict[str, Any]]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    return_property_quota: bool = False,
    access_token: Optional[str] = None,
) -> str:
    """Runs a Google Analytics Data API realtime report."""
    from google.analytics import data_v1beta

    request = data_v1beta.RunRealtimeReportRequest(
        property=construct_property_rn(property_id),
        dimensions=[data_v1beta.Dimension(name=dimension) for dimension in dimensions],
        metrics=[data_v1beta.Metric(name=metric) for metric in metrics],
        return_property_quota=return_property_quota,
    )

    if dimension_filter:
        request.dimension_filter = data_v1beta.FilterExpression(dimension_filter)
    if metric_filter:
        request.metric_filter = data_v1beta.FilterExpression(metric_filter)
    if order_bys:
        request.order_bys = [data_v1beta.OrderBy(order_by) for order_by in order_bys]
    if limit:
        request.limit = limit
    if offset:
        request.offset = offset

    def _sync_call():
        return create_data_client(access_token).run_realtime_report(request)

    response = await run_sync(_sync_call)
    return proto_to_dict(response)


@mcp_server.tool()
@ga_api_tool
async def get_custom_dimensions_and_metrics(
    property_id: Union[int, str],
    access_token: Optional[str] = None,
) -> str:
    """Returns the property's custom dimensions and metrics.

    Args:
        property_id: The Google Analytics property ID. Accepted formats are:
          - A number
          - A string consisting of 'properties/' followed by a number
    """

    def _sync_call():
        return create_data_client(access_token).get_metadata(
            name=f"{construct_property_rn(property_id)}/metadata"
        )

    metadata = await run_sync(_sync_call)
    custom_metrics = [
        proto_to_dict(metric) for metric in metadata.metrics if metric.custom_definition
    ]
    custom_dimensions = [
        proto_to_dict(dimension)
        for dimension in metadata.dimensions
        if dimension.custom_definition
    ]
    return {
        "custom_dimensions": custom_dimensions,
        "custom_metrics": custom_metrics,
    }
