import streamlit as st
import pandas as pd
import uuid
import json
import time
from pathlib import Path

# NEW: gspread for Google Sheets
import gspread

APP_TITLE = "Macro-Aware Meal Planner"
SAVED_FILE = Path("saved_meal_plans.json")
DEFAULT_CSV = Path("Macro_Meals.csv")
REQUIRED_COLS = ["Meal name","Meal type","Protein","Carb","Fat"]

# -------------------------------
# Data loading
# -------------------------------

@st.cache_data(show_spinner=False)
def _coerce_and_validate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    for col in ["Protein","Carb","Fat"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["Meal type"] = df["Meal type"].astype(str).str.strip()
    # keep required cols first (then any extras)
    cols = REQUIRED_COLS + [c for c in df.columns if c not in REQUIRED_COLS]
    return df[cols]

@st.cache_data(show_spinner=False)
def load_data_csv(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    return _coerce_and_validate(df)

@st.cache_data(show_spinner=True, ttl=300)
def load_data_gsheet(sheet_id: str, worksheet_name: str) -> pd.DataFrame:
    """
    Reads a Google Sheet into a DataFrame using a Service Account from st.secrets.
    Requires:
      - st.secrets["gcp_service_account"] (the full service-account JSON as a TOML table)
      - st.secrets["GOOGLE_SHEET_ID"]
      - st.secrets["GOOGLE_WORKSHEET_NAME"]
    """
    try:
        sa_info = st.secrets["gcp_service_account"]
    except Exception:
        raise RuntimeError(
            "No Google credentials found. Add a [gcp_service_account] block to your secrets."
        )

    # Authenticate using dict (no local file needed)
    gc = gspread.service_account_from_dict(dict(sa_info))
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(worksheet_name)

    # Fetch all values (first row = header)
    data = ws.get_all_records(numericise_ignore=['all'])  # don't auto-coerce; we handle below
    if not data:
        # fallback to header-only if sheet is empty
        header = ws.row_values(1) if ws.row_values(1) else REQUIRED_COLS
        df = pd.DataFrame(columns=header)
    else:
        df = pd.DataFrame(data)

    return _coerce_and_validate(df)

# -------------------------------
# App state & helpers
# -------------------------------

def ensure_state():
    st.session_state.setdefault("selected_meals", [])
    st.session_state.setdefault("totals", {"Protein":0.0,"Carb":0.0,"Fat":0.0})
    st.session_state.setdefault("caps", {"Protein":190,"Carb":253,"Fat":57})
    st.session_state.setdefault("meal_checks", {})  # plan_id -> list[bool] tick state for Saved Plans

def add_meal(row_dict):
    entry = dict(row_dict)
    entry["uid"] = str(uuid.uuid4())
    st.session_state["selected_meals"].append(entry)
    for k in ["Protein","Carb","Fat"]:
        st.session_state["totals"][k] += float(entry.get(k,0.0))

def remove_one_matching(row_dict):
    keys = ["Meal name","Meal type","Protein","Carb","Fat"]
    removed = None
    keep = []
    for m in st.session_state["selected_meals"]:
        if removed is None and all(m.get(k)==row_dict.get(k) for k in keys):
            removed = m
        else:
            keep.append(m)
    st.session_state["selected_meals"] = keep
    if removed:
        for k in ["Protein","Carb","Fat"]:
            st.session_state["totals"][k] -= float(removed.get(k,0.0))

def reset_plan():
    st.session_state["selected_meals"] = []
    st.session_state["totals"] = {"Protein":0.0,"Carb":0.0,"Fat":0.0}

def set_caps(p,c,f):
    st.session_state["caps"] = {"Protein":p, "Carb":c, "Fat":f}

def macro_bar(label, used, cap):
    used = float(used)
    cap = float(cap) if cap else 0.0
    pct = int(round((used / cap * 100) if cap > 0 else 0))
    pct_clamped = max(0, min(100, pct))
    over = cap > 0 and used > cap
    colour = "#1f77b4" if not over else "#d62728"
    over_text = f" (+{used-cap:.1f} over)" if over else ""
    html = f"""
    <div style="margin:6px 0 12px 0;">
      <div style="display:flex;justify-content:space-between;font-weight
