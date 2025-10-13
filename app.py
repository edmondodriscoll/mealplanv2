
import streamlit as st
import pandas as pd
import uuid
from collections import defaultdict

APP_TITLE = "Macro-Aware Meal Planner"

@st.cache_data
def load_data(file):
    df = pd.read_csv(file)
    # standardize column names
    df.columns = [c.strip() for c in df.columns]
    # coerce numeric macros
    for col in ["Protein","Carb","Fat"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    # tidy meal type text
    if "Meal type" in df.columns:
        df["Meal type"] = df["Meal type"].astype(str).str.strip()
    return df

def ensure_state():
    st.session_state.setdefault("selected_meals", [])  # list of individual entries (allows duplicates)
    st.session_state.setdefault("totals", {"Protein":0.0,"Carb":0.0,"Fat":0.0})

def add_meal(row_dict):
    # Allow duplicates by assigning a unique id per added instance
    entry = dict(row_dict)
    entry["uid"] = str(uuid.uuid4())
    st.session_state["selected_meals"].append(entry)
    for k in ["Protein","Carb","Fat"]:
        st.session_state["totals"][k] += float(entry.get(k,0.0))

def remove_one_matching(row_dict):
    """Remove exactly one instance matching the provided meal macro tuple."""
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

def macro_badge(label, value, max_value):
    used = float(value)
    cap = float(max_value) if max_value else 0.0
    if cap > 0:
        pct = min(100, int(round(used / cap * 100)))
        return f"{label}: {used:.1f} / {cap:.0f} ({pct}%)"
    else:
        return f"{label}: {used:.1f}"

def fits_caps(row, remaining):
    return (row["Protein"] <= remaining["Protein"]) and (row["Carb"] <= remaining["Carb"]) and (row["Fat"] <= remaining["Fat"])

def group_selected_meals(rows):
    """Group identical meals and count occurrences; return list of dicts with qty."""
    groups = {}
    for m in rows:
        key = (m["Meal name"], m.get("Meal type",""), float(m["Protein"]), float(m["Carb"]), float(m["Fat"]))
        if key not in groups:
            groups[key] = {"Meal name": key[0], "Meal type": key[1], "Protein": key[2], "Carb": key[3], "Fat": key[4], "qty": 0}
        groups[key]["qty"] += 1
    return list(groups.values())

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🥗", layout="wide")
    st.title(APP_TITLE)
    st.write("Pick your daily macro caps, filter by meal type, and add meals. "
             "The list will auto-hide meals that would push you over your caps.")

    ensure_state()

    # Sidebar: data source
    with st.sidebar:
        st.header("Data")
        src = st.radio("Choose data source", ["Bundled CSV", "Upload CSV"])
        if src == "Bundled CSV":
            data_file = "Macro_Meals.csv"
        else:
            upload = st.file_uploader("Upload a CSV with columns: Meal name, Meal type, Protein, Carb, Fat", type=["csv"])
            if upload is None:
                st.info("Please upload a CSV to proceed.")
                st.stop()
            data_file = upload

        df = load_data(data_file)

        # Macro caps
        st.header("Daily Macro Caps")
        max_protein = st.number_input("Max Protein (g)", min_value=0, value=190, step=5)
        max_carb = st.number_input("Max Carbs (g)", min_value=0, value=253, step=5)
        max_fat = st.number_input("Max Fat (g)", min_value=0, value=57, step=1)
        caps = {"Protein": max_protein, "Carb": max_carb, "Fat": max_fat}

        st.header("Filters")
        meal_types = sorted(df["Meal type"].dropna().unique().tolist()) if "Meal type" in df.columns else []
        selected_types = st.multiselect("Meal types to include", options=meal_types, default=meal_types)

        st.button("Reset plan", on_click=reset_plan, use_container_width=True)

    # Compute remaining capacity
    rem = {k: max(0.0, caps[k] - st.session_state["totals"][k]) for k in ["Protein","Carb","Fat"]}

    # Filter base dataframe by selected types
    view = df.copy()
    if selected_types and "Meal type" in view.columns:
        view = view[view["Meal type"].isin(selected_types)]

    # Now filter by not exceeding remaining capacity for a single add
    safe = view[view.apply(lambda r: fits_caps(r, rem), axis=1)]

    # Left: available meals; Right: selected plan and summary
    left, right = st.columns([2,1])

    with left:
        st.subheading = st.subheader("Available meals (won't exceed your remaining caps on next add)")
        if safe.empty:
            st.info("No meals fit under the remaining caps. Remove a meal or increase your caps.")
        else:
            # Render a compact table with an "Add" button per row
            for idx, row in safe.sort_values(by=["Meal type","Meal name"]).iterrows():
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
        if len(st.session_state["selected_meals"]) == 0:
            st.caption("No meals selected yet.")
        else:
            # Totals
            st.markdown("**Totals vs caps**")
            st.write(
                f"- {macro_badge('Protein', st.session_state['totals']['Protein'], caps['Protein'])}\n"
                f"- {macro_badge('Carbs', st.session_state['totals']['Carb'], caps['Carb'])}\n"
                f"- {macro_badge('Fat', st.session_state['totals']['Fat'], caps['Fat'])}"
            )
            st.progress(min(1.0, st.session_state['totals']['Protein']/caps['Protein'] if caps['Protein'] else 0.0))
            st.progress(min(1.0, st.session_state['totals']['Carb']/caps['Carb'] if caps['Carb'] else 0.0))
            st.progress(min(1.0, st.session_state['totals']['Fat']/caps['Fat'] if caps['Fat'] else 0.0))

            # Group duplicates for a cleaner UI and unlimited repeats
            grouped = group_selected_meals(st.session_state["selected_meals"])
            for g in grouped:
                with st.container(border=True):
                    c1, c2, c3, c4, c5, c6 = st.columns([3,2,2,2,2,2])
                    c1.markdown(f"**{g['Meal name']}**  \n_{g.get('Meal type','')}_")
                    c2.metric("Qty", f"{g['qty']}")
                    c3.metric("Protein", f"{g['Protein']*g['qty']:.1f} g")
                    c4.metric("Carbs", f"{g['Carb']*g['qty']:.1f} g")
                    c5.metric("Fat", f"{g['Fat']*g['qty']:.1f} g")

                    # Build a row dict representing one unit of this meal
                    unit = {"Meal name": g["Meal name"], "Meal type": g.get("Meal type",""),
                            "Protein": g["Protein"], "Carb": g["Carb"], "Fat": g["Fat"]}

                    # Plus button: only add if the next one fits remaining caps
                    rem_now = {k: max(0.0, caps[k] - st.session_state["totals"][k]) for k in ["Protein","Carb","Fat"]}
                    can_add_one_more = fits_caps(unit, rem_now)

                    # Keys unique per meal group
                    group_hash = hash((g['Meal name'], g.get('Meal type',''), g['Protein'], g['Carb'], g['Fat']))
                    add_key = f"inc_{group_hash}"
                    dec_key = f"dec_{group_hash}"

                    cols = c6.columns(2)
                    if cols[0].button("＋", key=add_key, disabled=not can_add_one_more):
                        add_meal(unit)
                        st.rerun()
                    if cols[1].button("－", key=dec_key):
                        remove_one_matching(unit)
                        st.rerun()

            # Download plan
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
            st.download_button(
                "Download plan as CSV",
                data=out_df.to_csv(index=False).encode("utf-8"),
                file_name="meal_plan.csv",
                mime="text/csv",
                use_container_width=True
            )

    with st.expander("Preview full dataset"):
        st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
