"""LLM argument hints for Google Analytics reporting tools.

Examples follow the protobuf/snake_case field names expected by the Data API
clients (not the REST camelCase docs). Adapted from the official Google
Analytics MCP: https://github.com/googleanalytics/google-analytics-mcp
"""

_FILTER_NOTES = """
Notes:
The API applies the `dimension_filter` and `metric_filter` independently. As a
result, some complex combinations of dimension and metric filters are not
possible in a single report request.

For example, you can't create a `dimension_filter` and `metric_filter`
combination for the following condition:

  (
    (eventName = "page_view" AND eventCount > 100)
    OR
    (eventName = "join_group" AND eventCount < 50)
  )

This isn't possible because there's no way to apply the condition
"eventCount > 100" only to the data with eventName of "page_view", and
the condition "eventCount < 50" only to the data with eventName of
"join_group".

If you have complex conditions like this, either:

a) Run a single report that applies a subset of the conditions that the API
   supports as well as the data needed to perform filtering of the API
   response on the client side.
or
b) Run a separate report for each combination of dimension condition and
   metric condition.

Try to run fewer reports (option a) if possible. However, if running fewer
reports results in excessive quota usage for the API, use option b. More
information on quota usage is at
https://developers.google.com/analytics/blog/2023/data-api-quota-management.
"""


def get_date_ranges_hints() -> str:
    return """Example date_range arguments:
1. A single date range:
   [ {"start_date": "2025-01-01", "end_date": "2025-01-31", "name": "Jan2025"} ]

2. A relative date range using 'yesterday' and 'today':
   [ {"start_date": "yesterday", "end_date": "today", "name": "YesterdayAndToday"} ]

3. A relative date range using 'NdaysAgo' and 'today':
   [ {"start_date": "30daysAgo", "end_date": "yesterday", "name": "Previous30Days"} ]

4. Multiple date ranges:
   [
     {"start_date": "2025-01-01", "end_date": "2025-01-31", "name": "Jan2025"},
     {"start_date": "2025-02-01", "end_date": "2025-02-28", "name": "Feb2025"}
   ]
"""


def get_dimension_filter_hints() -> str:
    return """Example dimension_filter arguments:
1. A simple filter:
   {"filter": {"field_name": "eventName", "string_filter": {"match_type": "BEGINS_WITH", "value": "add"}}}

2. A NOT filter:
   {"not_expression": {"filter": {"field_name": "eventName", "string_filter": {"match_type": "BEGINS_WITH", "value": "add"}}}}

3. An empty value filter:
   {"filter": {"field_name": "source", "empty_filter": {}}}

4. An AND group filter:
   {"and_group": {"expressions": [
     {"filter": {"field_name": "sourceMedium", "string_filter": {"match_type": "EXACT", "value": "google / cpc"}}},
     {"filter": {"field_name": "eventName", "in_list_filter": {"case_sensitive": true, "values": ["first_visit", "purchase", "add_to_cart"]}}}
   ]}}

5. An OR group filter:
   {"or_group": {"expressions": [
     {"filter": {"field_name": "sourceMedium", "string_filter": {"match_type": "EXACT", "value": "google / cpc"}}},
     {"filter": {"field_name": "eventName", "in_list_filter": {"case_sensitive": true, "values": ["first_visit", "purchase", "add_to_cart"]}}}
   ]}}
""" + _FILTER_NOTES


def get_metric_filter_hints() -> str:
    return """Example metric_filter arguments:
1. A simple filter:
   {"filter": {"field_name": "eventCount", "numeric_filter": {"operation": "GREATER_THAN", "value": {"int64_value": 10}}}}

2. A NOT filter:
   {"not_expression": {"filter": {"field_name": "eventCount", "numeric_filter": {"operation": "GREATER_THAN", "value": {"int64_value": 10}}}}}

3. An empty value filter:
   {"filter": {"field_name": "purchaseRevenue", "empty_filter": {}}}

4. An AND group filter:
   {"and_group": {"expressions": [
     {"filter": {"field_name": "eventCount", "numeric_filter": {"operation": "GREATER_THAN", "value": {"int64_value": 10}}}},
     {"filter": {"field_name": "purchaseRevenue", "between_filter": {"from_value": {"double_value": 10.0}, "to_value": {"double_value": 25.0}}}}
   ]}}

5. An OR group filter:
   {"or_group": {"expressions": [
     {"filter": {"field_name": "eventCount", "numeric_filter": {"operation": "GREATER_THAN", "value": {"int64_value": 10}}}},
     {"filter": {"field_name": "purchaseRevenue", "between_filter": {"from_value": {"double_value": 10.0}, "to_value": {"double_value": 25.0}}}}
   ]}}
""" + _FILTER_NOTES


def get_order_bys_hints() -> str:
    return """Example order_bys arguments:
1. Order by ascending 'eventName':
   [ {"dimension": {"dimension_name": "eventName", "order_type": "ALPHANUMERIC"}, "desc": false} ]

2. Order by descending campaign name, ignoring case:
   [ {"dimension": {"dimension_name": "campaignName", "order_type": "CASE_INSENSITIVE_ALPHANUMERIC"}, "desc": true} ]

3. Order by ascending 'audienceId':
   [ {"dimension": {"dimension_name": "audienceId", "order_type": "NUMERIC"}, "desc": false} ]

4. Order by descending 'eventValue':
   [ {"metric": {"metric_name": "eventValue"}, "desc": true} ]

5. Order by ascending 'eventCount':
   [ {"metric": {"metric_name": "eventCount"}, "desc": false} ]

6. Combination of dimension and metric order bys:
   [
     {"dimension": {"dimension_name": "eventName", "order_type": "ALPHANUMERIC"}, "desc": false},
     {"metric": {"metric_name": "eventValue"}, "desc": true}
   ]

The dimensions and metrics in order_bys must also be present in the report
request's "dimensions" and "metrics" arguments, respectively.
"""


def get_funnel_steps_hints() -> str:
    return """Example funnel_steps configurations:

1. Simple event-based step (shorthand):
   {"name": "Session start", "event": "session_start"}

2. Simple event filter (full expression):
   {"name": "Session start", "filter_expression": {"funnel_event_filter": {"event_name": "session_start"}}}

3. Multiple events with OR condition:
   {"name": "Screen/Page view", "filter_expression": {"or_group": {"expressions": [
     {"funnel_event_filter": {"event_name": "screen_view"}},
     {"funnel_event_filter": {"event_name": "page_view"}}
   ]}}}

4. Field filter for organic traffic:
   {"name": "Organic visitors", "filter_expression": {"funnel_field_filter": {
     "field_name": "firstUserMedium",
     "string_filter": {"match_type": "CONTAINS", "case_sensitive": false, "value": "organic"}
   }}}

5. Purchase events (multiple event types):
   {"name": "Purchase", "filter_expression": {"or_group": {"expressions": [
     {"funnel_event_filter": {"event_name": "purchase"}},
     {"funnel_event_filter": {"event_name": "in_app_purchase"}}
   ]}}}

6. Event with parameter filter (value > 50):
   {"name": "Add to cart (value > 50)", "filter_expression": {"funnel_event_filter": {
     "event_name": "add_to_cart",
     "funnel_parameter_filter_expression": {"funnel_parameter_filter": {
       "event_parameter_name": "value",
       "numeric_filter": {"operation": "GREATER_THAN", "value": {"double_value": 50.0}}
     }}
   }}}

7. Complex AND condition (page view + specific path):
   {"name": "Home page view", "filter_expression": {"and_group": {"expressions": [
     {"funnel_event_filter": {"event_name": "page_view"}},
     {"funnel_field_filter": {"field_name": "pageLocation", "string_filter": {"match_type": "CONTAINS", "value": "/"}}}
   ]}}}

## Complete funnel example

A typical e-commerce funnel with 5 steps:
[
  {"name": "First open/visit", "filter_expression": {"or_group": {"expressions": [
    {"funnel_event_filter": {"event_name": "first_open"}},
    {"funnel_event_filter": {"event_name": "first_visit"}}
  ]}}},
  {"name": "Organic visitors", "filter_expression": {"funnel_field_filter": {
    "field_name": "firstUserMedium",
    "string_filter": {"match_type": "CONTAINS", "case_sensitive": false, "value": "organic"}
  }}},
  {"name": "Session start", "event": "session_start"},
  {"name": "Screen/Page view", "filter_expression": {"or_group": {"expressions": [
    {"funnel_event_filter": {"event_name": "screen_view"}},
    {"funnel_event_filter": {"event_name": "page_view"}}
  ]}}},
  {"name": "Purchase", "filter_expression": {"or_group": {"expressions": [
    {"funnel_event_filter": {"event_name": "purchase"}},
    {"funnel_event_filter": {"event_name": "in_app_purchase"}}
  ]}}}
]
"""
