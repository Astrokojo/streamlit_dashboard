"""Allocation logic: split newly available stock across facilities.


    from data_loader import load_data
    from allocation import historical_requests, recommend
    df = load_data()
    facilities = sorted(df["facility"].unique())
    req = historical_requests(df, "Paracetamol Tablet, 500mg", facilities, months=24)
    rec = recommend(req, stock=100_000)

Method (MVP): each facility's recommended share equals its share of the
quantity it requested for that drug over the chosen history window. The
CSV holds requests only (no consumption), so requests are the only basis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# label -> months of history counted back from the latest date in the data
LOOKBACKS: dict[str, int | None] = {
    "All history": None,
    "Last 36 months": 36,
    "Last 24 months": 24,
    "Last 12 months": 12,
}


def window_start(data: pd.DataFrame, months: int | None) -> pd.Timestamp:
    """Start of the history window. Counted back from the latest date in the
    whole dataset (not today), so every drug uses the same window."""
    if months is None:
        return data["date"].min()
    return data["date"].max() - pd.DateOffset(months=months)


def historical_requests(
    data: pd.DataFrame, drug_name: str, facilities: list[str], months: int | None
) -> pd.Series:
    """Total quantity requested per facility for one drug inside the window.
    Facilities with no requests are kept with 0."""
    start = window_start(data, months)
    sub = data[(data["drug_name"] == drug_name) & (data["date"] >= start)]
    return sub.groupby("facility")["quantity"].sum().reindex(facilities, fill_value=0).astype("int64")


def recommend(requested: pd.Series, stock: int) -> pd.Series:
    """Split `stock` in proportion to `requested`, in whole units.

    Uses largest-remainder rounding so the recommendations add up to exactly
    `stock` (ties go to the facility listed first). If there is no stock or no
    request history there is no basis, so every recommendation is 0.
    """
    total = int(requested.sum())
    if stock <= 0 or total <= 0:
        return pd.Series(0, index=requested.index, dtype="int64")
    raw = requested / total * stock
    base = np.floor(raw).astype("int64")
    leftover = int(stock - base.sum())
    if leftover > 0:
        winners = (raw - base).sort_values(ascending=False, kind="stable").index[:leftover]
        base.loc[winners] += 1
    return base
