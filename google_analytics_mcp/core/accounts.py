"""Account and property tools for the Google Analytics Admin API."""

from typing import Any, Dict, List, Optional, Union

from .api import (
    create_admin_alpha_client,
    create_admin_client,
    ga_api_tool,
    proto_to_dict,
    run_sync,
)
from .server import mcp_server
from .utils import construct_property_rn


@mcp_server.tool()
@ga_api_tool
async def get_account_summaries(access_token: Optional[str] = None) -> str:
    """Retrieves information about the user's Google Analytics accounts and properties."""

    def _sync_call():
        summary_pager = create_admin_client(access_token).list_account_summaries()
        return [proto_to_dict(summary_page) for summary_page in summary_pager]

    return await run_sync(_sync_call)


@mcp_server.tool()
@ga_api_tool
async def get_property_details(
    property_id: Union[int, str],
    access_token: Optional[str] = None,
) -> str:
    """Returns details about a Google Analytics property.

    Args:
        property_id: The Google Analytics property ID. Accepted formats are:
          - A number
          - A string consisting of 'properties/' followed by a number
    """
    from google.analytics import admin_v1beta

    request = admin_v1beta.GetPropertyRequest(name=construct_property_rn(property_id))

    def _sync_call():
        return create_admin_client(access_token).get_property(request=request)

    response = await run_sync(_sync_call)
    return proto_to_dict(response)


@mcp_server.tool()
@ga_api_tool
async def list_google_ads_links(
    property_id: Union[int, str],
    access_token: Optional[str] = None,
) -> str:
    """Returns a list of links to Google Ads accounts for a property.

    Args:
        property_id: The Google Analytics property ID. Accepted formats are:
          - A number
          - A string consisting of 'properties/' followed by a number
    """
    from google.analytics import admin_v1beta

    request = admin_v1beta.ListGoogleAdsLinksRequest(parent=construct_property_rn(property_id))

    def _sync_call():
        links_pager = create_admin_client(access_token).list_google_ads_links(request=request)
        return [proto_to_dict(link_page) for link_page in links_pager]

    return await run_sync(_sync_call)


@mcp_server.tool()
@ga_api_tool
async def list_property_annotations(
    property_id: Union[int, str],
    access_token: Optional[str] = None,
) -> str:
    """Returns annotations for a property.

    Annotations are a feature that allows you to leave notes on GA4 for specific
    dates or periods. They are typically used to record service releases,
    marketing campaign launches or changes, and rapid traffic increases or
    decreases due to external factors.

    Args:
        property_id: The Google Analytics property ID. Accepted formats are:
          - A number
          - A string consisting of 'properties/' followed by a number
    """
    from google.analytics import admin_v1alpha

    request = admin_v1alpha.ListReportingDataAnnotationsRequest(
        parent=construct_property_rn(property_id)
    )

    def _sync_call():
        annotations_pager = create_admin_alpha_client(access_token).list_reporting_data_annotations(
            request=request
        )
        return [proto_to_dict(annotation_page) for annotation_page in annotations_pager]

    return await run_sync(_sync_call)
