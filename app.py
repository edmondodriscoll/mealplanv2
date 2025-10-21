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
    Reads a Google Sheet into a DataFrame using a Service Ac
