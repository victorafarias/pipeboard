"""Image asset upload and App ad image updates."""

import base64
import ipaddress
import re
import socket
from io import BytesIO
from typing import List, Optional, Sequence
from urllib.parse import urlparse

import httpx
from google.protobuf.field_mask_pb2 import FieldMask
from PIL import Image, UnidentifiedImageError

from .api import google_api_tool, get_client, run_gaql, McpToolError
from .server import mcp_server
from .utils import normalize_customer_id

_ALLOWED_URL_SCHEMES = ("http", "https")


class BlockedURLError(Exception):
    """Raised when a URL targets a disallowed address."""


def _ip_is_disallowed(ip) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_public_url(url: str) -> None:
    """Reject non-public URLs so the server cannot be used as a proxy."""
    if not url or not isinstance(url, str):
        raise BlockedURLError("No URL provided")
    parsed = urlparse(url.strip())
    if (parsed.scheme or "").lower() not in _ALLOWED_URL_SCHEMES:
        raise BlockedURLError(
            f"URL scheme '{parsed.scheme}' is not allowed; only http and https URLs can be fetched"
        )
    host = parsed.hostname
    if not host:
        raise BlockedURLError("URL has no host")
    try:
        candidate_ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise BlockedURLError(f"Could not resolve host '{host}': {exc}") from exc
        candidate_ips = []
        for info in infos:
            ip_text = info[4][0].split("%")[0]
            try:
                candidate_ips.append(ipaddress.ip_address(ip_text))
            except ValueError:
                continue
        if not candidate_ips:
            raise BlockedURLError(f"Could not resolve host '{host}' to any IP address")
    for ip in candidate_ips:
        if _ip_is_disallowed(ip):
            raise BlockedURLError(
                f"Refusing to fetch '{host}': it resolves to a non-public address "
                f"({ip}). Private, loopback, link-local, and cloud-metadata "
                "addresses are blocked to prevent server-side request forgery."
            )


async def _ssrf_guard_request_hook(request: httpx.Request) -> None:
    """Re-check the URL on every request, including redirect hops."""
    _validate_public_url(str(request.url))

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_APP_AD_IMAGES = 20
_ASSET_NAME_MAX = 255
_ASSET_RESOURCE_RE = re.compile(r"^customers/\d+/assets/\d+$")
_DATA_URL_RE = re.compile(r"^data:image/(?:png|jpe?g);base64,", re.IGNORECASE)
# Relative tolerance so 1200x628 (1.9108) matches the documented 1.91:1 ratio.
_ASPECT_RATIOS = (
    ("1.91:1", 1.91),
    ("1:1", 1.0),
    ("4:5", 4 / 5),
)
_ASPECT_TOLERANCE = 0.02
_AD_TYPE_NUMBERS = {17: "APP_AD"}


def _enum_name(value) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return _AD_TYPE_NUMBERS.get(value, str(value))
    text = str(value).strip()
    if text.isdigit():
        return _AD_TYPE_NUMBERS.get(int(text), text)
    return text.split(".")[-1].upper()


def _require_customer_id(customer_id: str) -> str:
    if not customer_id or not str(customer_id).strip():
        raise McpToolError("customer_id is required")
    cid = normalize_customer_id(customer_id)
    if not cid:
        raise McpToolError("customer_id is required")
    return cid


def _require_numeric_id(value, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text.isdigit():
        raise McpToolError(f"{label} must be a numeric ID")
    return str(int(text))


def _decode_base64_image(value: str) -> bytes:
    text = value.strip()
    if text.lower().startswith("data:"):
        if not _DATA_URL_RE.match(text):
            raise McpToolError("image_base64 data URL must be a base64 PNG or JPG")
        text = text.split(",", 1)[1]
    text = "".join(text.split())
    if not text:
        raise McpToolError("image_base64 is empty")
    try:
        return base64.b64decode(text, validate=True)
    except Exception as exc:
        raise McpToolError("image_base64 is not valid base64") from exc


def _match_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        raise McpToolError("Image has invalid dimensions")
    ratio = width / height
    best_label = ""
    best_delta = None
    for label, target in _ASPECT_RATIOS:
        delta = abs(ratio - target) / target
        if best_delta is None or delta < best_delta:
            best_label = label
            best_delta = delta
    if best_delta is None or best_delta > _ASPECT_TOLERANCE:
        raise McpToolError(
            f"Image is {width}x{height} (ratio {ratio:.3f}). "
            "App campaign images must be 1.91:1, 1:1, or 4:5."
        )
    return best_label


def _validate_image_bytes(data: bytes) -> dict:
    if not data:
        raise McpToolError("Image is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise McpToolError(
            f"Image is {len(data)} bytes. The maximum is 5 MB ({MAX_IMAGE_BYTES} bytes)."
        )
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            image_format = (image.format or "").upper()
            width, height = image.size
    except UnidentifiedImageError as exc:
        raise McpToolError("Image could not be decoded. Use a PNG or JPG file.") from exc
    except McpToolError:
        raise
    except Exception as exc:
        raise McpToolError("Image could not be decoded. Use a PNG or JPG file.") from exc
    if image_format not in {"PNG", "JPEG"}:
        raise McpToolError(
            f"Image format {image_format or 'unknown'} is not supported. Use PNG or JPG."
        )
    aspect_ratio = _match_aspect_ratio(width, height)
    return {
        "mime_type": "IMAGE_PNG" if image_format == "PNG" else "IMAGE_JPEG",
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "file_size_bytes": len(data),
    }


async def _fetch_image_url(url: str) -> bytes:
    try:
        _validate_public_url(url)
    except BlockedURLError as exc:
        raise McpToolError(str(exc)) from exc
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=60.0,
            event_hooks={"request": [_ssrf_guard_request_hook]},
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise McpToolError(f"Image URL returned HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                    raise McpToolError(
                        f"Image is {declared} bytes. The maximum is 5 MB ({MAX_IMAGE_BYTES} bytes)."
                    )
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise McpToolError(
                            f"Image is larger than 5 MB ({MAX_IMAGE_BYTES} bytes)."
                        )
                    chunks.append(chunk)
    except McpToolError:
        raise
    except BlockedURLError as exc:
        raise McpToolError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise McpToolError(f"Could not download image: {exc}") from exc
    data = b"".join(chunks)
    if not data:
        raise McpToolError("Image URL returned an empty body")
    return data


def _asset_resource_names(values, *, label: str) -> List[str]:
    if not isinstance(values, (list, tuple)):
        raise McpToolError(f"{label} must be a list of asset resource names")
    cleaned = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str) or not value.strip():
            raise McpToolError(f"{label} {index} must be a non-empty string")
        resource_name = value.strip()
        if not _ASSET_RESOURCE_RE.match(resource_name):
            raise McpToolError(
                f"{label} {index} must be an asset resource name like "
                f"customers/1234567890/assets/9876543210. Got: {value!r}"
            )
        cleaned.append(resource_name)
    return cleaned


def _dedupe(values: Sequence[str]) -> List[str]:
    seen = set()
    unique = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _ad_from_row(row) -> dict:
    if not isinstance(row, dict):
        return {}
    if isinstance(row.get("ad"), dict):
        return row["ad"]
    ad_group_ad = row.get("ad_group_ad")
    if isinstance(ad_group_ad, dict) and isinstance(ad_group_ad.get("ad"), dict):
        return ad_group_ad["ad"]
    return row


def _existing_image_assets(ad: dict) -> List[str]:
    app_ad = ad.get("app_ad") if isinstance(ad.get("app_ad"), dict) else {}
    images = app_ad.get("images") or []
    names = []
    for item in images:
        if isinstance(item, dict) and item.get("asset"):
            names.append(str(item["asset"]))
        elif isinstance(item, str) and item:
            names.append(item)
    return names


def _load_app_ad(customer_id: str, ad_id: str, access_token: Optional[str]) -> dict:
    query = f"""
        SELECT
          ad.id,
          ad.type,
          ad.app_ad.images
        FROM ad
        WHERE ad.id = {ad_id}
        LIMIT 1
    """
    rows = run_gaql(customer_id, query, access_token)
    if not rows:
        raise McpToolError(f"Ad {ad_id} not found")
    ad = _ad_from_row(rows[0])
    ad_type = _enum_name(ad.get("type_") or ad.get("type"))
    if ad_type != "APP_AD":
        raise McpToolError(
            f"Ad {ad_id} is not an App ad (type is {ad_type or 'unknown'}). "
            "update_app_ad_images only changes app_ad.images."
        )
    return ad


@mcp_server.tool()
@google_api_tool
async def upload_image_asset(
    customer_id: str,
    name: str,
    image_base64: Optional[str] = None,
    url: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Create an IMAGE asset from a PNG or JPG and return its resource name.

    Provide image_base64 or url, not both. image_base64 may be raw base64 or a
    data URL. The decoded file must be PNG or JPG, at most 5 MB, and one of
    the App campaign ratios 1.91:1, 1:1, or 4:5. A 3.5 MB PNG is about 4.7 MB
    of base64; the HTTP transport accepts bodies up to 12 MiB.

    Args:
        customer_id: Google Ads customer ID
        name: Asset name (required, 255 characters or fewer)
        image_base64: PNG or JPG contents, base64-encoded
        url: Public http(s) URL of a PNG or JPG
    """
    has_base64 = isinstance(image_base64, str) and bool(image_base64.strip())
    has_url = isinstance(url, str) and bool(url.strip())
    if has_base64 == has_url:
        raise McpToolError("Provide either image_base64 or url, not both")
    asset_name = (name or "").strip() if isinstance(name, str) else ""
    if not asset_name:
        raise McpToolError("name is required")
    if len(asset_name) > _ASSET_NAME_MAX:
        raise McpToolError(f"name must be {_ASSET_NAME_MAX} characters or fewer")
    cid = _require_customer_id(customer_id)
    if has_base64:
        image_bytes = _decode_base64_image(image_base64)
    else:
        image_bytes = await _fetch_image_url(url.strip())
    info = _validate_image_bytes(image_bytes)

    client = get_client(access_token)
    asset_service = client.get_service("AssetService")
    operation = client.get_type("AssetOperation")
    asset = operation.create
    asset.name = asset_name
    asset.type_ = client.enums.AssetTypeEnum.IMAGE
    asset.image_asset.data = image_bytes
    request = client.get_type("MutateAssetsRequest")
    request.customer_id = cid
    request.operations.append(operation)
    response = asset_service.mutate_assets(request=request)
    results = getattr(response, "results", None) or []
    if not results or not getattr(results[0], "resource_name", ""):
        raise McpToolError("Image asset mutate returned no resource name")
    resource_name = results[0].resource_name
    return {
        "customer_id": cid,
        "asset_resource_name": resource_name,
        "asset_id": resource_name.rsplit("/", 1)[-1],
        "name": asset_name,
        **info,
    }


@mcp_server.tool()
@google_api_tool
async def update_app_ad_images(
    customer_id: str,
    ad_id: str,
    image_asset_resource_names: List[str],
    mode: str = "replace",
    access_token: Optional[str] = None,
) -> dict:
    """Replace or append images on an existing App ad.

    Uses AdService.MutateAds with update_mask app_ad.images only, so status,
    headlines, and descriptions stay as they are. An App ad can have at most
    20 images. mode is replace (default) or append.

    Args:
        customer_id: Google Ads customer ID
        ad_id: Ad ID of an existing App ad
        image_asset_resource_names: IMAGE asset resource names
            (customers/{id}/assets/{id})
        mode: replace or append
    """
    mode_value = (mode or "replace").strip().lower()
    if mode_value not in {"replace", "append"}:
        raise McpToolError("mode must be replace or append")
    requested = _dedupe(
        _asset_resource_names(image_asset_resource_names, label="Image asset")
    )
    cid = _require_customer_id(customer_id)
    ad_id_value = _require_numeric_id(ad_id, "ad_id")
    ad = _load_app_ad(cid, ad_id_value, access_token)
    existing = _dedupe(_existing_image_assets(ad))
    if mode_value == "append":
        final_images = _dedupe([*existing, *requested])
    else:
        final_images = requested
    if len(final_images) > MAX_APP_AD_IMAGES:
        raise McpToolError(
            f"App ads allow at most {MAX_APP_AD_IMAGES} images (got {len(final_images)}). "
            f"The ad currently has {len(existing)}."
        )

    client = get_client(access_token)
    ad_service = client.get_service("AdService")
    operation = client.get_type("AdOperation")
    updated = operation.update
    updated.resource_name = ad_service.ad_path(cid, ad_id_value)
    for resource_name in final_images:
        image = client.get_type("AdImageAsset")
        image.asset = resource_name
        updated.app_ad.images.append(image)
    operation.update_mask.CopyFrom(FieldMask(paths=["app_ad.images"]))
    response = ad_service.mutate_ads(customer_id=cid, operations=[operation])
    results = getattr(response, "results", None) or []
    resource_name = ""
    if results:
        resource_name = getattr(results[0], "resource_name", "") or ""
    if not resource_name:
        resource_name = ad_service.ad_path(cid, ad_id_value)
    verb = "replaced" if mode_value == "replace" else "appended"
    return {
        "customer_id": cid,
        "ad_id": ad_id_value,
        "ad_resource_name": resource_name,
        "mode": mode_value,
        "image_asset_resource_names": final_images,
        "image_count": len(final_images),
        "message": (
            f"App ad images {verb}. Status, headlines, and descriptions were not changed."
        ),
    }
