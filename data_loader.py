"""Shared data loading for the Streamlit dashboard and the Jupyter notebook.

Both import `load_data` so they clean the CSV identically. The CSV itself is
never modified: this only reads it and returns a tidy DataFrame.

    from data_loader import load_data
    df = load_data()                      # DATA.csv next to this file
    df = load_data("path/to/DATA.csv")    # or any other path
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_PATH = Path(__file__).with_name("DATA.csv")

_RENAME = {
    "FACILITY CODE": "facility",
    "DRUG CODE": "drug_code",
    "DRUG NAME": "drug_name",
    "DRUG FORM": "drug_form",
    "QUANTITY REQUESTED": "quantity",
    "DATE": "date",
}


def load_data(path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    """Read and tidy the CSV.

    Cleaning applied (nothing is dropped, so row counts match the file):
      * drug codes: trailing/leading spaces stripped
      * drug names: repeated internal spaces collapsed
      * drug forms: whitespace stripped and case unified (e.g. "Gel" -> "GEL")
      * dates: parsed as DD/MM/YYYY (the first field runs 1-14 and the second
        only takes values 1-12, so the file is day-first)
      * facility: shown as "Facility <code>"
      * month: first day of the date's month, for monthly aggregation
    """
    raw = pd.read_csv(path, dtype=str)
    missing = set(_RENAME) - set(raw.columns)
    if missing:
        raise ValueError(f"CSV is missing expected columns: {sorted(missing)}")

    df = raw.rename(columns=_RENAME)[list(_RENAME.values())].copy()
    df["facility"] = "Facility " + df["facility"].str.strip()
    df["drug_code"] = df["drug_code"].str.strip()
    df["drug_name"] = df["drug_name"].str.split().str.join(" ")
    df["drug_form"] = df["drug_form"].str.strip().str.upper()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="raise").astype("int64")
    df["date"] = pd.to_datetime(df["date"].str.strip(), format="%d/%m/%Y")
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df.sort_values(["date", "facility", "drug_name"]).reset_index(drop=True)


def data_quality(df: pd.DataFrame) -> dict:
    """Counts of the quirks worth knowing about in this dataset."""
    names_per_code = df.groupby("drug_code")["drug_name"].nunique()
    codes_per_name = df.groupby("drug_name")["drug_code"].nunique()
    return {
        "rows": len(df),
        "zero_quantity_rows": int((df["quantity"] == 0).sum()),
        "exact_duplicate_rows": int(df.duplicated().sum()),
        "codes_with_several_names": sorted(names_per_code[names_per_code > 1].index),
        "names_with_several_codes": sorted(codes_per_name[codes_per_name > 1].index),
    }
