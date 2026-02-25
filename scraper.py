"""SerpApi integration for fetching Google Maps reviews."""

from __future__ import annotations

from typing import Any

from serpapi import GoogleSearch


class ScraperError(ValueError):
    """Raised when SerpApi review fetching fails."""


def _extract_local_guide(review: dict[str, Any]) -> bool:
    badges = review.get("user", {}).get("badges", []) or review.get("badges", [])
    if isinstance(badges, list):
        return any("local guide" in str(badge).lower() for badge in badges)
    return "local guide" in str(badges).lower()


def _normalize_review(review: dict[str, Any]) -> dict[str, Any]:
    user = review.get("user", {}) or {}
    return {
        "rating": review.get("rating"),
        "text": review.get("snippet") or review.get("excerpt") or review.get("text") or "",
        "date_text": review.get("iso_date") or review.get("date") or review.get("published_at") or "",
        "user_reviews": user.get("reviews") or review.get("user_reviews") or 0,
        "local_guide": review.get("local_guide") if review.get("local_guide") is not None else _extract_local_guide(review),
        "raw": review,
    }


def fetch_reviews(data_id: str, api_key: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Fetch reviews for a Google Maps place from SerpApi.

    Uses `google_maps_reviews` engine and paginates until exhausted,
    or until `limit` is reached when a limit is provided.
    """
    if not data_id:
        raise ScraperError("Missing place `data_id`.")
    if not api_key:
        raise ScraperError("Missing SerpApi API key.")

    reviews: list[dict[str, Any]] = []
    next_page_token: str | None = None

    while limit is None or len(reviews) < limit:
        params: dict[str, Any] = {
            "engine": "google_maps_reviews",
            "data_id": data_id,
            "api_key": api_key,
            "sort_by": "newestFirst",
            "hl": "en",
        }
        if next_page_token:
            params["next_page_token"] = next_page_token

        search = GoogleSearch(params)
        result = search.get_dict()

        if "error" in result:
            raise ScraperError(f"SerpApi error: {result['error']}")

        page_reviews = result.get("reviews", [])
        if not page_reviews:
            break

        for item in page_reviews:
            reviews.append(_normalize_review(item))
            if limit is not None and len(reviews) >= limit:
                break

        pagination = result.get("serpapi_pagination", {})
        next_page_token = pagination.get("next_page_token")
        if not next_page_token:
            break

    return reviews
