
import streamlit as st
import pandas as pd
import uuid
import json
import time
from pathlib import Path

APP_TITLE = "Macro-Aware Meal Planner"
SAVED_FILE = Path("saved_meal_plans.json")
DEFAULT_CSV = Path("Macro_Meals.csv")
REQUIRED_COLS = ["Meal name","Meal type","Protein","Carb","Fat"]

@st.cache_data
def load_data(file):
    df = pd.read_csv(file)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")
    for col in ["Protein","Carb","Fat"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["Meal type"] = df["Meal type"].astype(str).str.strip()
    return df

def ensure_state():
    st.session_state.setdefault("selected_meals", [])
    st.session_state.setdefault("totals", {"Protein":0.0,"Carb":0.0,"Fat":0.0})
    st.session_state.setdefault("caps", {"Protein":190,"Carb":253,"Fat":57})

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
      <div style="display:flex;justify-content:space-between;font-weight:600;">
        <span>{label}</span>
        <span>{used:.1f} / {cap:.0f}g{over_text}</span>
      </div>
      <div style="background:#e6e6e6;border-radius:8px;height:14px;overflow:hidden;">
        <div style="height:14px;width:{pct_clamped}%;background:{colour};border-radius:8px;"></div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def group_selected_meals(rows):
    groups = {}
    for m in rows:
        key = (m["Meal name"], m.get("Meal type",""), float(m["Protein"]), float(m["Carb"]), float(m["Fat"]))
        if key not in groups:
            groups[key] = {"Meal name": key[0], "Meal type": key[1], "Protein": key[2], "Carb": key[3], "Fat": key[4], "qty": 0}
        groups[key]["qty"] += 1
    return list(groups.values())

def read_saved():
    if SAVED_FILE.exists():
        with open(SAVED_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def write_saved(plans):
    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(plans, f, indent=2)

def save_current_plan(name):
    if not name.strip():
        st.error("Please enter a plan name.")
        return
    payload = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "timestamp": int(time.time()),
        "caps": st.session_state["caps"],
        "meals": [
            {k: v for k, v in m.items() if k != "uid"}
            for m in st.session_state["selected_meals"]
        ]
    }
    plans = read_saved()
    existing_names = {p["name"] for p in plans}
    base = payload["name"]
    counter = 2
    while payload["name"] in existing_names:
        payload["name"] = f"{base} ({counter})"
        counter += 1
    plans.append(payload)
    write_saved(plans)
    st.success(f"Saved plan as “{payload['name']}”.")

def load_plan(plan_id):
    plans = read_saved()
    match = next((p for p in plans if p["id"] == plan_id), None)
    if not match:
        st.error("Plan not found.")
        return
    st.session_state["selected_meals"] = []
    st.session_state["totals"] = {"Protein":0.0,"Carb":0.0,"Fat":0.0}
    st.session_state["caps"] = match.get("caps", st.session_state["caps"])
    for m in match.get("meals", []):
        add_meal(m)
    st.success(f"Loaded plan “{match['name']}”.")
    st.experimental_rerun()

def delete_plan(plan_id):
    plans = read_saved()
    new_plans = [p for p in plans if p["id"] != plan_id]
    write_saved(new_plans)
    st.success("Deleted saved plan.")
    st.experimental_rerun()

def replace_default_with(df: pd.DataFrame):
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Uploaded CSV missing required columns: {missing}")
    cols = REQUIRED_COLS + [c for c in df.columns if c not in REQUIRED_COLS]
    df = df[cols]
    df.to_csv(DEFAULT_CSV, index=False, encoding="utf-8")
    load_data.clear()
    st.success("Default CSV replaced successfully. The app now uses this as the default dataset.")

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🥗", layout="wide")
    st.title(APP_TITLE)
    ensure_state()

    tabs = st.tabs(["🧰 Builder", "💾 Saved Plans"])

    with tabs[0]:
        with st.sidebar:
            st.header("Data")
            st.caption(f"Current default file: `{DEFAULT_CSV}`")

            src = st.radio("Choose data source", ["Bundled CSV", "Upload CSV"])
            if src == "Bundled CSV":
                data_file = str(DEFAULT_CSV)
                upload = None
            else:
                upload = st.file_uploader(
                    "Upload a CSV with columns: Meal name, Meal type, Protein, Carb, Fat",
                    type=["csv"],
                    accept_multiple_files=False
                )
                data_file = upload if upload is not None else str(DEFAULT_CSV)

            try:
                df = load_data(data_file)
            except Exception as e:
                st.error(f"Error loading data: {e}")
                st.stop()

            if upload is not None:
                st.markdown("**Uploaded CSV preview:**")
                st.dataframe(df.head(20), use_container_width=True)
                if st.button("Make this the new default CSV (overwrite Macro_Meals.csv)", type="primary"):
                    try:
                        raw_df = pd.read_csv(upload)
                        replace_default_with(raw_df)
                    except Exception as e:
                        st.error(f"Couldn't replace default: {e}")

            st.header("Daily Macro Caps")
            max_protein = st.number_input("Max Protein (g)", min_value=0, value=int(st.session_state["caps"]["Protein"]), step=5)
            max_carb = st.number_input("Max Carbs (g)", min_value=0, value=int(st.session_state["caps"]["Carb"]), step=5)
            max_fat = st.number_input("Max Fat (g)", min_value=0, value=int(st.session_state["caps"]["Fat"]), step=1)
            caps = {"Protein": max_protein, "Carb": max_carb, "Fat": max_fat}
            set_caps(max_protein, max_carb, max_fat)

            st.header("Filters")
            meal_types = sorted(df["Meal type"].dropna().unique().tolist()) if "Meal type" in df.columns else []
            selected_types = st.multiselect("Meal types to include", options=meal_types, default=meal_types)

            st.button("Reset plan", on_click=reset_plan, use_container_width=True)

        view = df.copy()
        if selected_types and "Meal type" in view.columns:
            view = view[view["Meal type"].isin(selected_types)]

        left, right = st.columns([2,1])

        with left:
            st.subheader("Available meals")
            if view.empty:
                st.info("No meals available with current filters.")
            else:
                for idx, row in view.sort_values(by=["Meal type","Meal name"]).iterrows():
                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns([3,2,2,2,2])
                        c1.markdown(f"**{row['Meal name']}**  \n_{row.get('Meal type','')}_")
                        c2.metric("Protein", f"{row['Protein']:.1f} g")
                        c3.metric("Carbs", f"{row['Carb']:.1f} g")
                        c4.metric("Fat", f"{row['Fat']:.1f} g")
                        if c5.button("Add ➕", key=f"add_{idx}"):
                            add_meal(row[["Meal name","Meal type","Protein","Carb","Fat"]].to_dict())
                            st.rerun()

        with right:
            st.subheader("Your plan")
            st.button("Reset All Meals", on_click=reset_plan, use_container_width=True)
            if len(st.session_state["selected_meals"]) == 0:
                st.caption("No meals selected yet.")
            else:
                totals = st.session_state["totals"]
                caps = st.session_state["caps"]
                over_list = [k for k in ["Protein","Carb","Fat"] if caps[k] and totals[k] > caps[k]]
                if over_list:
                    st.warning("You're over your caps for: " + ", ".join(over_list))

                macro_bar("Protein", totals["Protein"], caps["Protein"])
                macro_bar("Carbs", totals["Carb"], caps["Carb"])
                macro_bar("Fat", totals["Fat"], caps["Fat"])

                grouped = group_selected_meals(st.session_state["selected_meals"])
                for g in grouped:
                    with st.container(border=True):
                        c1, c2, c3, c4, c5, c6 = st.columns([3,2,2,2,2,2])
                        c1.markdown(f"**{g['Meal name']}**  \n_{g.get('Meal type','')}_")
                        c2.metric("Qty", f"{g['qty']}")
                        c3.metric("Protein", f"{g['Protein']*g['qty']:.1f} g")
                        c4.metric("Carbs", f"{g['Carb']*g['qty']:.1f} g")
                        c5.metric("Fat", f"{g['Fat']*g['qty']:.1f} g")

                        unit = {"Meal name": g["Meal name"], "Meal type": g.get("Meal type",""),
                                "Protein": g["Protein"], "Carb": g["Carb"], "Fat": g["Fat"]}

                        group_hash = hash((g['Meal name'], g.get('Meal type',''), g['Protein'], g['Carb'], g['Fat']))
                        cols = c6.columns(2)
                        if cols[0].button("＋", key=f"inc_{group_hash}"):
                            add_meal(unit)
                            st.rerun()
                        if cols[1].button("－", key=f"dec_{group_hash}"):
                            remove_one_matching(unit)
                            st.rerun()

                with st.container(border=True):
                    st.markdown("**Save or export your plan**")
                    plan_name = st.text_input("Plan name", placeholder="e.g., High Protein Monday")
                    colA, colB = st.columns(2)
                    if colA.button("💾 Save plan", use_container_width=True):
                        save_current_plan(plan_name or f"Plan {time.strftime('%Y-%m-%d %H:%M')}")
                    plan_df = pd.DataFrame(st.session_state["selected_meals"])
                    plan_df["Count"] = 1
                    totals_row = pd.DataFrame([{
                        "Meal name":"TOTALS",
                        "Meal type":"",
                        "Protein":plan_df["Protein"].sum() if not plan_df.empty else 0.0,
                        "Carb":plan_df["Carb"].sum() if not plan_df.empty else 0.0,
                        "Fat":plan_df["Fat"].sum() if not plan_df.empty else 0.0,
                        "Count":len(plan_df)
                    }])
                    out_df = pd.concat([plan_df, totals_row], ignore_index=True)
                    colB.download_button(
                        "⬇️ Download CSV",
                        data=out_df.to_csv(index=False).encode("utf-8"),
                        file_name="meal_plan.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

        with st.expander("Preview full dataset"):
            st.dataframe(df, use_container_width=True)

    with tabs[1]:
        st.subheader("Saved Meal Plans")
        plans = read_saved()
        if not plans:
            st.info("No saved plans yet. Build a plan in the **Builder** tab and click **Save plan**.")
        else:
            plans_sorted = sorted(plans, key=lambda p: p.get("timestamp", 0), reverse=True)
            names = [f"{p['name']} — {time.strftime('%Y-%m-%d %H:%M', time.localtime(p.get('timestamp',0)))}" for p in plans_sorted]
            sel = st.selectbox("Choose a saved plan", options=list(range(len(plans_sorted))), format_func=lambda i: names[i])
            chosen = plans_sorted[sel]
            caps = chosen.get("caps", {"Protein":0,"Carb":0,"Fat":0})
            meals_df = pd.DataFrame(chosen.get("meals", []))
            totals = {
                "Protein": float(meals_df["Protein"].sum()) if not meals_df.empty else 0.0,
                "Carb": float(meals_df["Carb"].sum()) if not meals_df.empty else 0.0,
                "Fat": float(meals_df["Fat"].sum()) if not meals_df.empty else 0.0,
            }
            st.write(f"**Caps:** P {caps.get('Protein',0)}g • C {caps.get('Carb',0)}g • F {caps.get('Fat',0)}g")
            st.write(f"**Totals:** P {totals['Protein']:.1f}g • C {totals['Carb']:.1f}g • F {totals['Fat']:.1f}g")
            st.dataframe(meals_df, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            if c1.button("📥 Load this plan into Builder", use_container_width=True):
                load_plan(chosen["id"])
            if c2.button("🗑️ Delete", use_container_width=True):
                delete_plan(chosen["id"])
            c3.download_button(
                "⬇️ Export JSON",
                data=json.dumps(chosen, indent=2).encode("utf-8"),
                file_name=f"{chosen['name'].replace(' ','_')}.json",
                mime="application/json",
                use_container_width=True
            )

if __name__ == "__main__":
    main()
