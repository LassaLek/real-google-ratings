"""Analysis engine for weighted rating and scam probability estimation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class AnalysisResult:
    original_rating: float
    adjusted_rating: float
    scam_probability: float
    total_reviews: int
    remaining_reviews: int
    breakdown: dict[str, int]


def _parse_relative_date(text: Any, now: datetime) -> pd.Timestamp:
    if isinstance(text, (pd.Timestamp, datetime)):
        return pd.Timestamp(text)

    value = str(text or "").strip().lower()
    if not value:
        return pd.NaT

    if value in {"today", "just now"}:
        return pd.Timestamp(now)
    if value == "yesterday":
        return pd.Timestamp(now) - pd.Timedelta(days=1)

    m = re.match(r"(a|an|\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", value)
    if m:
        qty_raw, unit = m.groups()
        qty = 1 if qty_raw in {"a", "an"} else int(qty_raw)
        if unit == "minute":
            return pd.Timestamp(now) - pd.Timedelta(minutes=qty)
        if unit == "hour":
            return pd.Timestamp(now) - pd.Timedelta(hours=qty)
        if unit == "day":
            return pd.Timestamp(now) - pd.Timedelta(days=qty)
        if unit == "week":
            return pd.Timestamp(now) - pd.Timedelta(weeks=qty)
        if unit == "month":
            return pd.Timestamp(now) - pd.DateOffset(months=qty)
        if unit == "year":
            return pd.Timestamp(now) - pd.DateOffset(years=qty)

    parsed = pd.to_datetime(value, errors="coerce", utc=False)
    return parsed


def analyze_reviews(reviews: list[dict[str, Any]]) -> AnalysisResult:
    now = datetime.utcnow()
    if not reviews:
        return AnalysisResult(0.0, 0.0, 0.0, 0, 0, {
            "rule_a_dropped": 0,
            "rule_b_penalized": 0,
            "rule_c_boosted": 0,
            "rule_d_spike_penalized": 0,
            "rule_e_zero_effort_penalized": 0,
        })

    df = pd.DataFrame(reviews)
    if df.empty or "rating" not in df:
        raise ValueError("No usable reviews found in API response.")

    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df = df.dropna(subset=["rating"]).copy()
    if df.empty:
        raise ValueError("No numeric ratings found in the reviews.")

    total_reviews = len(df)
    original_rating = round(float(df["rating"].mean()), 2)

    df["created_at"] = df["date_text"].apply(lambda x: _parse_relative_date(x, now))
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["Weight"] = 1.0

    # Rule A: novice + extreme ratings -> drop
    df["user_reviews"] = pd.to_numeric(df.get("user_reviews", 0), errors="coerce").fillna(0)
    novice_mask = (df["user_reviews"] < 5) & (df["rating"].isin([1, 5]))
    rule_a_dropped = int(novice_mask.sum())
    df = df.loc[~novice_mask].copy()

    if df.empty:
        return AnalysisResult(
            original_rating=original_rating,
            adjusted_rating=0.0,
            scam_probability=100.0,
            total_reviews=total_reviews,
            remaining_reviews=0,
            breakdown={
                "rule_a_dropped": rule_a_dropped,
                "rule_b_penalized": 0,
                "rule_c_boosted": 0,
                "rule_d_spike_penalized": 0,
                "rule_e_zero_effort_penalized": 0,
            },
        )

    # Rule B: time decay
    age_months = ((pd.Timestamp(now) - df["created_at"]).dt.days / 30.44).fillna(0)
    rule_b_penalized = int((age_months >= 6).sum())
    df.loc[(age_months >= 6) & (age_months < 12), "Weight"] *= 0.8
    df.loc[(age_months >= 12) & (age_months < 24), "Weight"] *= 0.5
    df.loc[age_months >= 24, "Weight"] *= 0.2

    # Rule C: local guide boost
    local_guide_mask = df.get("local_guide", False).astype(bool)
    rule_c_boosted = int(local_guide_mask.sum())
    df.loc[local_guide_mask, "Weight"] *= 1.2

    # Rule D: monthly spike penalty
    valid_dates = df.dropna(subset=["created_at"]).copy()
    spike_months: list[pd.Period] = []
    if not valid_dates.empty:
        valid_dates["month"] = valid_dates["created_at"].dt.to_period("M")
        monthly_counts = valid_dates.groupby("month").size().sort_index()
        baseline = monthly_counts.rolling(window=3, min_periods=1).mean().shift(1)
        spike_index = monthly_counts[(baseline > 0) & (monthly_counts > (3 * baseline))].index
        spike_months = list(spike_index)
        if spike_months:
            df["month"] = df["created_at"].dt.to_period("M")
            df.loc[df["month"].isin(spike_months), "Weight"] *= 0.1
    rule_d_spike_penalized = int(df["created_at"].dt.to_period("M").isin(spike_months).sum()) if spike_months else 0

    # Rule E: zero/low effort text
    word_counts = df.get("text", "").fillna("").astype(str).str.split().str.len()
    zero_words_mask = word_counts == 0
    low_words_mask = (word_counts > 0) & (word_counts < 5)
    rule_e_zero_effort_penalized = int((zero_words_mask | low_words_mask).sum())
    df.loc[zero_words_mask, "Weight"] *= 0.3
    df.loc[low_words_mask, "Weight"] *= 0.5

    # Final weighted rating
    total_weight = float(df["Weight"].sum())
    adjusted_rating = round(float((df["rating"] * df["Weight"]).sum() / total_weight), 2) if total_weight > 0 else 0.0

    # Scam probability = dropped + heavily penalized ratio
    penalized_mask = df["Weight"] < 0.7
    suspicious_count = rule_a_dropped + int(penalized_mask.sum())
    scam_probability = round(min(100.0, (suspicious_count / max(total_reviews, 1)) * 100), 2)

    return AnalysisResult(
        original_rating=original_rating,
        adjusted_rating=adjusted_rating,
        scam_probability=scam_probability,
        total_reviews=total_reviews,
        remaining_reviews=len(df),
        breakdown={
            "rule_a_dropped": rule_a_dropped,
            "rule_b_penalized": rule_b_penalized,
            "rule_c_boosted": rule_c_boosted,
            "rule_d_spike_penalized": rule_d_spike_penalized,
            "rule_e_zero_effort_penalized": rule_e_zero_effort_penalized,
        },
    )
