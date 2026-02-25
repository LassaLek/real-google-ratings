"""Streamlit app for Google Maps review trust analysis."""

from __future__ import annotations

import os

import streamlit as st

from analyzer import analyze_reviews
from scraper import ScraperError, fetch_reviews
from url_helper import UrlExpansionError, expand_google_maps_url

st.set_page_config(page_title="Google Ratings Analyzer", page_icon="📍", layout="centered")
st.title("📍 Real Google Ratings Analyzer")
st.write(
    "Paste a Google Maps place link to estimate an adjusted rating "
    "and scam probability based on review quality signals."
)

url_input = st.text_input("Paste Google Maps Link", placeholder="https://maps.app.goo.gl/...")

# IMPORTANT: API key is server-side only (Streamlit secrets / env), never shown in UI.
try:
    serpapi_key = st.secrets.get("SERPAPI_KEY", "")
except Exception:
    serpapi_key = ""
if not serpapi_key:
    serpapi_key = os.getenv("SERPAPI_KEY", "")

no_limit = st.checkbox("Analyze all available reviews (no cap)", value=False)
if no_limit:
    review_limit: int | None = None
    st.caption("No cap selected: app will paginate through all available SerpApi review pages.")
else:
    review_limit = st.select_slider("Reviews to analyze", options=[100, 200, 500, 1000, 2500, 5000], value=1000)

if url_input:
    if not serpapi_key:
        st.error(
            "Missing SerpApi key on server. Please set `SERPAPI_KEY` in Streamlit secrets "
            "or as an environment variable before running the app."
        )
    else:
        try:
            with st.spinner("Analyzing reviews..."):
                expanded = expand_google_maps_url(url_input)
                reviews = fetch_reviews(expanded["data_id"], api_key=serpapi_key, limit=review_limit)
                result = analyze_reviews(reviews)

            st.success(f"Processed {result.total_reviews} reviews from resolved place URL.")

            col1, col2 = st.columns(2)
            col1.metric("Original Rating", f"{result.original_rating:.2f}")
            col2.metric("Adjusted Rating", f"{result.adjusted_rating:.2f}")

            st.subheader("Scam Probability")
            st.progress(min(int(result.scam_probability), 100))
            st.markdown(f"**{result.scam_probability:.2f}%**")

            with st.expander("See Analysis Breakdown"):
                st.write(f"Remaining reviews after Rule A filter: **{result.remaining_reviews}**")
                st.write(f"Rule A (Novice extreme reviews dropped): **{result.breakdown['rule_a_dropped']}**")
                st.write(f"Rule B (Time-decay penalized): **{result.breakdown['rule_b_penalized']}**")
                st.write(f"Rule C (Local guide boosted): **{result.breakdown['rule_c_boosted']}**")
                st.write(f"Rule D (Time-series spike penalized): **{result.breakdown['rule_d_spike_penalized']}**")
                st.write(f"Rule E (Zero/low-effort penalized): **{result.breakdown['rule_e_zero_effort_penalized']}**")
                st.caption(f"Resolved URL: {expanded['final_url']}")

        except (UrlExpansionError, ScraperError, ValueError) as exc:
            st.error(f"Analysis failed: {exc}")
