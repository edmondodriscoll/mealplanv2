
# Macro-Aware Meal Planner (Streamlit)

This Streamlit app helps you build a daily meal plan under custom macro caps (Protein, Carbs, Fat).
It uses a CSV with at least these columns:

- `Meal name`
- `Meal type`
- `Protein`
- `Carb`
- `Fat`

## How it works

1. Set your daily macro caps in the sidebar.
2. (Optional) Filter by `Meal type`.
3. Add meals from the list. The list auto-hides any meal that would push you over the remaining caps.
4. Remove meals if needed, and download your plan as CSV.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app loads the bundled `Macro_Meals.csv` by default. You can also upload your own CSV via the sidebar.

## Deploy to Streamlit Community Cloud

1. Create a new GitHub repo and add these files:
   - `app.py`
   - `requirements.txt`
   - `Macro_Meals.csv`
   - `README.md`
2. In Streamlit Community Cloud, create a new app and point it at your repo's `app.py`.
3. Click Deploy.

## Notes

- If your CSV has extra columns, they'll be ignored; only `Meal name`, `Meal type`, and macro columns are used.
- Macro columns are coerced to numbers; blanks default to 0.
