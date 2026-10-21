"""Drug request dashboard.

Run with:  streamlit run app.py

Reads the same CSV as the notebook through data_loader.load_data and never
writes to it. The file's modified time is part of the cache key, so saving a
new version of the CSV shows up on the next interaction or browser refresh.
"""
from __future__ import annotations

import os
from pathlib import Path

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from allocation import LOOKBACKS, historical_requests, recommend
from data_loader import DEFAULT_PATH, data_quality, load_data

st.set_page_config(page_title="Drug requests", page_icon="💊", layout="wide")

# ---- visual tokens (light theme; matches .streamlit/config.toml) -----------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
# Categorical slots in fixed order. A facility keeps its colour whatever the
# filters are. The first three are validated together; extras only appear if
# the CSV ever gains more facilities.
CATEGORICAL = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#6250d6", "#e34948",
]
SEQ_BLUE = ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"]
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


@st.cache_data(show_spinner=False)
def _load(path: str, mtime: float):
    return load_data(path)


def _style(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=8, b=0),
        font=dict(family=FONT, size=13, color=INK_2),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
        hoverlabel=dict(bgcolor=SURFACE, font=dict(family=FONT, color=INK, size=13)),
    )
    fig.update_xaxes(linecolor=AXIS, tickfont=dict(color=MUTED), zeroline=False)
    fig.update_yaxes(linecolor=AXIS, tickfont=dict(color=MUTED), zeroline=False)
    return fig


# ---- data source ------------------------------------------------------------
def render_allocation(data: pd.DataFrame, facility_order: list[str], facility_color: dict[str, str]) -> None:
    """Allocation tab: recommended split of new stock + officer's surplus."""
    st.subheader("Stock allocation")
    st.caption(
        "The recommendation splits the new stock in proportion to each facility's historical "
        "requests for the drug. Add any surplus per facility, then review the final allocation. "
        "This tab uses the whole file; the sidebar filters don't apply here."
    )

    c1, c2, c3 = st.columns([2, 1, 1])
    drug = c1.selectbox("Drug to allocate", sorted(data["drug_name"].unique()))
    sub = data[data["drug_name"] == drug]
    form = ", ".join(sorted(sub["drug_form"].str.lower().unique()))
    latest = sub[sub["month"] == sub["month"].max()]
    stock = int(
        c2.number_input(
            f"New stock available ({form})",
            min_value=0,
            value=int(latest["quantity"].sum()),
            step=10,
            key=f"stock::{drug}",
            help="Prefilled with the total requested in this drug's latest period, as a starting "
            "point. Replace it with the stock you actually have.",
        )
    )
    lookback = c3.selectbox("History used", list(LOOKBACKS), help="Counted back from the latest date in the file.")

    requested = historical_requests(data, drug, facility_order, LOOKBACKS[lookback])
    rec = recommend(requested, stock)
    if requested.sum() == 0:
        st.warning(
            "This drug has no requests in the selected history, so there is no basis for a "
            "recommendation. Try a longer history window."
        )

    last = (
        sub[sub["quantity"] > 0].sort_values("date").groupby("facility").tail(1).set_index("facility")
        .reindex(facility_order)
    )
    table = pd.DataFrame(
        {
            "Facility": facility_order,
            "Requested in window": requested.to_numpy(),
            "Share of requests (%)": (requested / requested.sum() * 100).to_numpy() if requested.sum() else 0.0,
            "Last request": last["quantity"].fillna(0).astype("int64").to_numpy(),
            "Last request date": [d.strftime("%d %b %Y") if pd.notna(d) else "–" for d in last["date"]],
            "Recommended": rec.to_numpy(),
            "Additional surplus": 0,
        }
    )
    st.markdown("**Recommended allocation and surplus**")
    edited = st.data_editor(
        table,
        key=f"alloc_editor::{drug}::{lookback}",
        hide_index=True,
        width="stretch",
        disabled=[c for c in table.columns if c != "Additional surplus"],
        column_config={
            "Requested in window": st.column_config.NumberColumn(format="localized"),
            "Share of requests (%)": st.column_config.NumberColumn(format="%.1f"),
            "Last request": st.column_config.NumberColumn(format="localized"),
            "Recommended": st.column_config.NumberColumn(format="localized"),
            "Additional surplus": st.column_config.NumberColumn(
                "Additional surplus ✎", min_value=0, step=1, format="localized",
                help="Editable. Extra units on top of the recommendation, for operational need, "
                "expected demand or professional judgement.",
            ),
        },
    )
    surplus = pd.to_numeric(edited["Additional surplus"], errors="coerce").fillna(0).clip(lower=0).astype("int64")
    final = rec.to_numpy() + surplus.to_numpy()

    remaining = stock - int(final.sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Stock available", f"{stock:,}")
    m2.metric("Surplus applied", f"{int(surplus.sum()):,}")
    m3.metric("Final allocation", f"{int(final.sum()):,}")
    m4.metric("Stock remaining", f"{remaining:,}")
    if remaining < 0:
        st.warning(
            f"The final allocation is {-remaining:,} units more than the stock available. "
            "Reduce a surplus or confirm extra stock before issuing."
        )

    left, right = st.columns([3, 2])
    with left:
        colors = [facility_color[f] for f in facility_order]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=facility_order, y=rec.to_numpy(), name="Recommended",
                marker=dict(color=colors, line=dict(color=SURFACE, width=2)),
                hovertemplate="%{x}<br>Recommended: %{y:,}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Bar(
                x=facility_order, y=surplus.to_numpy(), name="Surplus",
                marker=dict(
                    color=colors, line=dict(color=colors, width=1.5),
                    pattern=dict(shape="/", bgcolor=SURFACE, fgcolor=colors, size=7, solidity=0.5),
                ),
                hovertemplate="%{x}<br>Surplus: %{y:,}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=facility_order, y=final, mode="text", text=[f"{v:,}" for v in final],
                textposition="top center", textfont=dict(color=INK_2, size=12),
                showlegend=False, hoverinfo="skip",
            )
        )
        fig.update_layout(barmode="stack", bargap=0.45, showlegend=False)
        fig.update_yaxes(gridcolor=GRID, tickformat="~s", range=[0, max(int(final.max()), 1) * 1.15])
        fig.update_xaxes(showgrid=False)
        st.plotly_chart(_style(fig, 300), width="stretch", config={"displaylogo": False})
        st.caption("Solid = recommended · hatched = surplus · label = final allocation")
    with right:
        result = pd.DataFrame(
            {
                "Facility": facility_order,
                "Recommended": rec.to_numpy(),
                "Surplus": surplus.to_numpy(),
                "Final allocation": final,
            }
        )
        st.markdown("**Final allocation**")
        st.dataframe(
            result.style.format({"Recommended": "{:,}", "Surplus": "{:,}", "Final allocation": "{:,}"}),
            width="stretch", hide_index=True,
        )
        plan = pd.DataFrame(
            {
                "prepared_on": date.today().isoformat(),
                "drug": drug,
                "facility": facility_order,
                "history_used": lookback,
                "stock_available": stock,
                "requested_in_window": requested.to_numpy(),
                "recommended": rec.to_numpy(),
                "surplus": surplus.to_numpy(),
                "final_allocation": final,
            }
        )
        st.download_button(
            "Download allocation plan (CSV)", plan.to_csv(index=False),
            f"allocation_{drug.split(',')[0].split()[0].lower()}_{date.today().isoformat()}.csv", "text/csv",
        )


with st.sidebar:
    st.header("Filters")
    with st.expander("Data source"):
        csv_path = st.text_input(
            "CSV path", os.environ.get("DASHBOARD_CSV", str(DEFAULT_PATH))
        )

path = Path(csv_path).expanduser()
if not path.is_file():
    st.error(f"CSV not found: {path}")
    st.stop()
try:
    data = _load(str(path), path.stat().st_mtime)
except Exception as exc:  # unreadable CSV, wrong columns, unexpected date format
    st.error(f"Could not read {path.name}: {exc}")
    st.stop()

facility_order = sorted(data["facility"].unique())
facility_color = {f: CATEGORICAL[i % len(CATEGORICAL)] for i, f in enumerate(facility_order)}

# ---- filters ----------------------------------------------------------------
with st.sidebar:
    facilities = st.multiselect("Facility", facility_order, default=facility_order)
    d_min, d_max = data["date"].min().date(), data["date"].max().date()
    date_range = st.date_input("Date range", (d_min, d_max), min_value=d_min, max_value=d_max)
    drugs = st.multiselect("Drug", sorted(data["drug_name"].unique()), placeholder="All drugs")
    forms = st.multiselect("Drug form", sorted(data["drug_form"].unique()), placeholder="All forms")
    exclude_zero = st.checkbox(
        "Exclude zero-quantity rows",
        value=True,
        help="Rows where nothing was requested. Excluding them keeps the request "
        "count to actual requests; totals are unaffected either way.",
    )

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
else:  # user is mid-selection in the date picker
    start, end = d_min, d_max

mask = data["facility"].isin(facilities) & data["date"].between(str(start), str(end))
if drugs:
    mask &= data["drug_name"].isin(drugs)
if forms:
    mask &= data["drug_form"].isin(forms)
if exclude_zero:
    mask &= data["quantity"] > 0
df = data[mask]

with st.sidebar:
    st.caption(f"{len(df):,} of {len(data):,} rows after filters")

# ---- header + KPIs ------------------------------------------------------------
st.title("Drug requests")
st.caption(f"{path.name} · {data['date'].min():%d %b %Y} to {data['date'].max():%d %b %Y}")

kpi_area = st.container()  # filled below, once we know the filters matched rows
tab_overview, tab_alloc, tab_heat, tab_data = st.tabs(["Overview", "Allocation", "Facility × drug", "Data"])

with tab_alloc:  # independent of the sidebar filters, so it renders even if they match nothing
    render_allocation(data, facility_order, facility_color)

if df.empty:
    kpi_area.warning("No rows match the current filters.")
    st.stop()

k1, k2, k3, k4 = kpi_area.columns(4)
k1.metric("Total quantity requested", f"{df['quantity'].sum():,}")
k2.metric("Requests", f"{len(df):,}")
k3.metric("Distinct drugs", f"{df['drug_name'].nunique():,}")
k4.metric("Facilities", f"{df['facility'].nunique():,}")

# ---- overview -----------------------------------------------------------------
with tab_overview:
    st.subheader("Quantity requested over time")
    monthly = df.groupby(["month", "facility"], as_index=False)["quantity"].sum()
    fig = go.Figure()
    for fac in facility_order:
        sub = monthly[monthly["facility"] == fac]
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["month"], y=sub["quantity"], name=fac, mode="lines+markers",
                line=dict(color=facility_color[fac], width=2),
                marker=dict(size=8, color=facility_color[fac], line=dict(color=SURFACE, width=2)),
                connectgaps=True, hovertemplate="%{y:,}",
            )
        )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(tickformat="%b %Y", showgrid=False)
    fig.update_yaxes(gridcolor=GRID, tickformat="~s", title_text="Quantity requested")
    st.plotly_chart(_style(fig, 380), width="stretch", config={"displaylogo": False})
    st.caption(
        "Quantities are summed as recorded. Units differ by drug form (tablets, vials, "
        "bottles), so pick a single drug in the sidebar for a like-for-like trend."
    )

    st.subheader("Quantity requested by drug")
    by_drug = df.pivot_table(index="drug_name", columns="facility", values="quantity", aggfunc="sum", fill_value=0)
    by_drug = by_drug.loc[by_drug.sum(axis=1).sort_values().index]  # largest ends up on top
    fig = go.Figure()
    for fac in facility_order:
        if fac not in by_drug.columns:
            continue
        fig.add_trace(
            go.Bar(
                y=by_drug.index, x=by_drug[fac], name=fac, orientation="h",
                marker=dict(color=facility_color[fac], line=dict(color=SURFACE, width=2)),
                hovertemplate="%{y}<br>" + fac + ": %{x:,}<extra></extra>",
            )
        )
    totals = by_drug.sum(axis=1)
    fig.add_trace(  # end-of-bar totals, so drugs with tiny quantities stay readable
        go.Scatter(
            x=totals, y=totals.index, mode="text", text=[f"{v:,.0f}" for v in totals],
            textposition="middle right", textfont=dict(color=INK_2, size=12),
            showlegend=False, hoverinfo="skip",
        )
    )
    fig.update_layout(barmode="stack", bargap=0.35, hovermode="closest", legend_traceorder="normal")
    fig.update_xaxes(gridcolor=GRID, tickformat="~s", title_text="Quantity requested",
                     range=[0, float(totals.max()) * 1.2])
    fig.update_yaxes(showgrid=False, automargin=True)
    st.plotly_chart(_style(fig, 120 + 32 * len(by_drug)), width="stretch", config={"displaylogo": False})

# ---- facility × drug heatmap ---------------------------------------------------
with tab_heat:
    st.subheader("Facility × drug")
    log_scale = st.radio("Colour scale", ["Logarithmic", "Linear"], horizontal=True,
                         help="Tablet quantities are thousands of times larger than injections; "
                              "a log scale keeps small requests visible.")
    pivot = df.pivot_table(index="drug_name", columns="facility", values="quantity", aggfunc="sum", fill_value=0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
    z = pivot.to_numpy()
    use_log = log_scale == "Logarithmic"
    z_plot = np.log10(1 + z) if use_log else z
    colorbar = dict(title=dict(text="Quantity"), outlinewidth=0, thickness=14)
    if use_log:
        top = int(np.ceil(z_plot.max())) if z_plot.max() > 0 else 1
        ticks = list(range(top + 1))
        colorbar.update(tickvals=ticks, ticktext=["0" if t == 0 else f"{10 ** t:,.0f}" for t in ticks])
    fig = go.Figure(
        go.Heatmap(
            z=z_plot, x=pivot.columns, y=pivot.index, customdata=z,
            colorscale=[[i / (len(SEQ_BLUE) - 1), c] for i, c in enumerate(SEQ_BLUE)],
            xgap=2, ygap=2, colorbar=colorbar,
            hovertemplate="%{y}<br>%{x}: %{customdata:,}<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True)
    fig.update_xaxes(showgrid=False, side="top")
    st.plotly_chart(_style(fig, 140 + 32 * len(pivot)), width="stretch", config={"displaylogo": False})
    with st.expander("Table view"):
        st.dataframe(pivot.style.format("{:,}"), width="stretch")

# ---- data + notes ---------------------------------------------------------------
with tab_data:
    st.subheader("Filtered rows")
    shown = df[["date", "facility", "drug_code", "drug_name", "drug_form", "quantity"]].copy()
    shown["date"] = shown["date"].dt.date
    st.dataframe(shown, width="stretch", hide_index=True)
    st.download_button("Download filtered rows (CSV)", shown.to_csv(index=False), "filtered_requests.csv", "text/csv")

    q = data_quality(data)
    st.subheader("Notes on the data")
    st.markdown(
        f"These describe the whole file ({q['rows']:,} rows), not the current filters. "
        "Nothing is removed or edited in the source CSV.\n\n"
        f"- **{q['zero_quantity_rows']}** rows have a quantity of 0.\n"
        f"- **{q['exact_duplicate_rows']}** rows are exact duplicates of another row "
        "(same facility, drug, quantity and date). They are kept, since repeat requests are possible.\n"
        "- Drug codes are trimmed of padding spaces, drug names have doubled spaces collapsed, "
        "and drug forms are case-normalised (for example `Gel` and `GEL` are the same form).\n"
        "- Dates are read as DD/MM/YYYY.\n"
        + (f"- Codes carrying more than one drug name: `{'`, `'.join(q['codes_with_several_names'])}`.\n"
           if q["codes_with_several_names"] else "")
        + (f"- Drug names carrying more than one code: `{'`, `'.join(q['names_with_several_codes'])}`.\n"
           if q["names_with_several_codes"] else "")
    )
