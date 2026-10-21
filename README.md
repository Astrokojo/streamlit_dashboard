# Drug Requests Dashboard

A Streamlit dashboard for exploring facility drug requests and planning how to split newly available stock across facilities. It reads a single CSV file, which can also be the data source for a Jupyter notebook. The dashboard never modifies the CSV.

## Features

- **Overview**: monthly request trends by facility, and total quantity by drug.
- **Allocation**: recommends how to split new stock across facilities in proportion to their historical requests, lets the logistics officer add a surplus per facility, and exports the final plan as a CSV.
- **Facility × drug**: a heatmap of total quantity for every facility and drug, with a log or linear colour scale.
- **Data**: the filtered rows, a CSV download, and notes on data quality.
- **Sidebar filters**: facility, date range, drug, drug form, and a toggle to exclude zero-quantity rows.

## Requirements

- Python 3.10 or newer
- The packages in `requirements.txt` (Streamlit, Plotly, pandas)

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.

## Data

The app expects a CSV named `DATA.csv` in the same folder as `app.py`, with these columns:   


| Column | Example |
| --- | --- |
| `FACILITY CODE` | `1` |
| `DRUG CODE` | `PARA520` |
| `DRUG NAME` | `Paracetamol Tablet, 500mg` |
| `DRUG FORM` | `TABLET` |
| `QUANTITY REQUESTED` | `24000` |
| `DATE` | `08/01/2020` (day/month/year) |

The `DATA.csv` included in this repository is a sample. To use a file stored elsewhere, either:

- type its path under **Data source** in the sidebar, or
- set an environment variable before starting the app:

```bash
DASHBOARD_CSV=/path/to/DATA.csv streamlit run app.py
```

The app reloads the file when its modified time changes, so refresh the browser page after saving a new version.

## Allocation method

For a chosen drug, stock quantity and history window (all history, or the last 36, 24 or 12 months), each facility's recommended share is:

```
recommended = stock × (facility's requests for the drug) / (all facilities' requests for the drug)
```

Results are whole units that add up exactly to the stock, with leftover units going to the largest fractional remainders. The officer then enters an additional surplus per facility. Final allocation is the recommendation plus the surplus, so a surplus can take the total above the stock, and the app shows a warning when it does.

The CSV holds requests only, with no consumption figures, so recommendations reflect what facilities asked for, not what they used. The dashboard does not save or issue allocations; users download the plan CSV before leaving the tab.

## Using the same CSV in a notebook

```python
from data_loader import load_data
from allocation import historical_requests, recommend

df = load_data()                                   # same cleaning as the dashboard
facilities = sorted(df["facility"].unique())
requested = historical_requests(df, "Paracetamol Tablet, 500mg", facilities, months=24)
recommend(requested, stock=100_000)
```

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | The Streamlit app: filters, charts and the Allocation tab |
| `data_loader.py` | Reads and tidies the CSV, shared with notebooks |
| `allocation.py` | Allocation logic, with no Streamlit dependency |
| `requirements.txt` | Python dependencies |
| `.streamlit/config.toml` | Theme and toolbar settings |

## Deployment notes

- The app has **no authentication**. Anyone who can reach its address can see all requests and use the Allocation tab. Run it on an internal network or behind a login (single sign-on or a reverse proxy), and use HTTPS. Do not expose port 8501 directly to the internet.
- Keep the real CSV out of version control, and mount or copy it onto the server separately.
- The dataset is small, so about 1 CPU and 1 GB of memory is enough.

See the user manual for step-by-step deployment instructions.

## Data notes

- Dates are read as day/month/year.
- Rows are never removed. Drug codes and names are trimmed, and drug form case is unified (for example `Gel` and `GEL` are the same form).
- The app groups by drug name, not drug code, because the same drug can appear under more than one code. The **Notes on the data** section of the Data tab lists the exceptions found in the current file.

## Troubleshooting

- **"CSV not found"**: check the path under Data source, or put `DATA.csv` next to `app.py`.
- **"Could not read DATA.csv"**: check that all six column headings match the table above and that every date is DD/MM/YYYY.
- **A NumPy `longdouble` warning on WSL**: this is a harmless warning on WSL1. Switching to WSL2, or keeping the virtual environment on the Linux filesystem instead of under `/mnt/c`, usually removes it.
