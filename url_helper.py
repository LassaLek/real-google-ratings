"""Utilities for expanding Google Maps short links and extracting data identifiers."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import requests


class UrlExpansionError(ValueError):
    """Raised when a Google Maps URL cannot be expanded or parsed."""


def _extract_data_id_from_url(url: str) -> str | None:
    """Extract a SerpApi-compatible `data_id` from known Google Maps URL shapes."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    data_value = query.get("data", [None])[0]
    if data_value:
        return unquote(data_value)

    # Some share links encode the final target URL as `link=<...>`.
    nested_link = query.get("link", [None])[0]
    if nested_link:
        nested = _extract_data_id_from_url(unquote(nested_link))
        if nested:
            return nested

    # Many standard maps URLs include a stable place identifier in the path.
    # Example segment: `!1s0x89c258f4f3f6f7f7:0xb2b....`
    place_match = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", url, flags=re.IGNORECASE)
    if place_match:
        return place_match.group(1)

    return None


def expand_google_maps_url(short_url: str, timeout: int = 15) -> dict[str, str]:
    """Follow redirects and extract the place `data_id` from the final URL.

    Args:
        short_url: Google Maps link (short or long form).
        timeout: Request timeout in seconds.

    Returns:
        Dictionary with `final_url` and extracted `data_id`.

    Raises:
        UrlExpansionError: If URL cannot be resolved or a data id isn't found.
    """
    if not short_url or not short_url.strip():
        raise UrlExpansionError("Please provide a valid Google Maps URL.")

    try:
        response = requests.get(short_url.strip(), allow_redirects=True, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise UrlExpansionError(f"Unable to expand URL: {exc}") from exc

    final_url = response.url
    data_id = _extract_data_id_from_url(final_url)

    if not data_id:
        raise UrlExpansionError(
            "Could not extract a supported Google Maps place identifier from the resolved URL. "
            "Please try a full place URL from maps.google.com."
        )

    return {
        "final_url": final_url,
        "data_id": data_id,
    }
