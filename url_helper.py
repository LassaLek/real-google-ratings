"""Utilities for expanding Google Maps short links and extracting data identifiers."""

from __future__ import annotations

import re
from urllib.parse import unquote

import requests


class UrlExpansionError(ValueError):
    """Raised when a Google Maps URL cannot be expanded or parsed."""


def expand_google_maps_url(short_url: str, timeout: int = 15) -> dict[str, str]:
    """Follow redirects and extract the `data=` identifier from the final URL.

    Args:
        short_url: Google Maps link (short or long form).
        timeout: Request timeout in seconds.

    Returns:
        Dictionary with `final_url` and extracted `data_id`.

    Raises:
        UrlExpansionError: If URL cannot be resolved or `data=` isn't found.
    """
    if not short_url or not short_url.strip():
        raise UrlExpansionError("Please provide a valid Google Maps URL.")

    try:
        response = requests.get(short_url.strip(), allow_redirects=True, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise UrlExpansionError(f"Unable to expand URL: {exc}") from exc

    final_url = response.url
    match = re.search(r"[?&]data=([^&]+)", final_url)

    if not match:
        raise UrlExpansionError(
            "Could not find a `data=` identifier in the resolved URL. "
            "Please try a different Google Maps link."
        )

    return {
        "final_url": final_url,
        "data_id": unquote(match.group(1)),
    }
