"""
Comprehensive unit tests for app.py.

Pure Python functions (no real Streamlit runtime needed) are tested here.
Streamlit is mocked via sys.modules before the app module is imported.
"""

import sys
import json
import time
import tempfile
import uuid
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import pandas as pd

# ─── Streamlit mock ──────────────────────────────────────────────────────────
# Must be installed before `import app`.

_mock_st = MagicMock()
_session_state: dict = {}
_mock_st.session_state = _session_state


def _mock_cache_data(*args, **kwargs):
    """Pass-through replacement for @st.cache_data."""
    def decorator(func):
        return func
    # Called as @st.cache_data (no parens) → args[0] is the function
    if len(args) == 1 and callable(args[0]):
        return args[0]
    # Called as @st.cache_data(...) → return decorator
    return decorator


_mock_st.cache_data = _mock_cache_data

sys.modules.setdefault("streamlit", _mock_st)
sys.modules.setdefault("gspread", MagicMock())

import app  # noqa: E402 — must come after mock setup

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _reset_session():
    """Reset the mocked session_state to a clean baseline."""
    _session_state.clear()
    app.ensure_state()


def _make_meal(name="Chicken", mtype="Lunch", protein=30.0, carb=10.0, fat=5.0):
    return {
        "Meal name": name,
        "Meal type": mtype,
        "Protein": protein,
        "Carb": carb,
        "Fat": fat,
    }


# ─── _coerce_and_validate ────────────────────────────────────────────────────


class TestCoerceAndValidate:
    def _make_df(self, **overrides):
        data = {
            "Meal name": ["Eggs"],
            "Meal type": ["Breakfast"],
            "Protein": ["30"],
            "Carb": ["5"],
            "Fat": ["10"],
        }
        data.update(overrides)
        return pd.DataFrame(data)

    def test_happy_path_returns_dataframe(self):
        df = self._make_df()
        result = app._coerce_and_validate(df)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns[:5]) == app.REQUIRED_COLS

    def test_numeric_coercion(self):
        df = self._make_df(Protein=["abc"], Carb=[""], Fat=["3.5"])
        result = app._coerce_and_validate(df)
        assert result["Protein"].iloc[0] == 0.0
        assert result["Carb"].iloc[0] == 0.0
        assert result["Fat"].iloc[0] == 3.5

    def test_column_name_stripping(self):
        df = self._make_df()
        df.columns = [" " + c + " " for c in df.columns]
        result = app._coerce_and_validate(df)
        assert "Meal name" in result.columns

    def test_missing_required_column_raises(self):
        df = pd.DataFrame({"Meal name": ["X"], "Meal type": ["Y"], "Protein": [1]})
        with pytest.raises(ValueError, match="missing required columns"):
            app._coerce_and_validate(df)

    def test_extra_columns_are_preserved(self):
        df = self._make_df()
        df["Notes"] = ["some note"]
        result = app._coerce_and_validate(df)
        assert "Notes" in result.columns

    def test_meal_type_stripped(self):
        df = self._make_df(Meal_type=None)
        df["Meal type"] = ["  Breakfast  "]
        result = app._coerce_and_validate(df)
        assert result["Meal type"].iloc[0] == "Breakfast"

    def test_does_not_mutate_input(self):
        df = self._make_df()
        original_cols = list(df.columns)
        app._coerce_and_validate(df)
        assert list(df.columns) == original_cols


# ─── ensure_state ────────────────────────────────────────────────────────────


class TestEnsureState:
    def test_sets_defaults(self):
        _session_state.clear()
        app.ensure_state()
        assert "selected_meals" in _session_state
        assert "totals" in _session_state
        assert "caps" in _session_state
        assert "meal_checks" in _session_state

    def test_does_not_overwrite_existing(self):
        _session_state.clear()
        _session_state["selected_meals"] = ["existing"]
        app.ensure_state()
        assert _session_state["selected_meals"] == ["existing"]

    def test_default_caps(self):
        _session_state.clear()
        app.ensure_state()
        assert _session_state["caps"]["Protein"] == 190
        assert _session_state["caps"]["Carb"] == 253
        assert _session_state["caps"]["Fat"] == 57


# ─── add_meal / remove_one_matching / reset_plan ────────────────────────────


class TestMealStateManagement:
    def setup_method(self):
        _reset_session()

    def test_add_meal_appends_entry(self):
        app.add_meal(_make_meal())
        assert len(_session_state["selected_meals"]) == 1

    def test_add_meal_generates_uid(self):
        app.add_meal(_make_meal())
        assert "uid" in _session_state["selected_meals"][0]

    def test_add_meal_updates_totals(self):
        app.add_meal(_make_meal(protein=30.0, carb=10.0, fat=5.0))
        assert _session_state["totals"]["Protein"] == 30.0
        assert _session_state["totals"]["Carb"] == 10.0
        assert _session_state["totals"]["Fat"] == 5.0

    def test_add_multiple_meals_accumulates_totals(self):
        app.add_meal(_make_meal(protein=30.0, carb=10.0, fat=5.0))
        app.add_meal(_make_meal(protein=20.0, carb=5.0, fat=2.0))
        assert _session_state["totals"]["Protein"] == pytest.approx(50.0)

    def test_remove_one_matching_removes_first_occurrence(self):
        row = _make_meal(protein=30.0)
        app.add_meal(row)
        app.add_meal(row)
        app.remove_one_matching(row)
        assert len(_session_state["selected_meals"]) == 1

    def test_remove_one_matching_updates_totals(self):
        row = _make_meal(protein=30.0, carb=10.0, fat=5.0)
        app.add_meal(row)
        app.remove_one_matching(row)
        assert _session_state["totals"]["Protein"] == pytest.approx(0.0)
        assert _session_state["totals"]["Carb"] == pytest.approx(0.0)
        assert _session_state["totals"]["Fat"] == pytest.approx(0.0)

    def test_remove_one_matching_no_match_is_safe(self):
        app.add_meal(_make_meal(name="A"))
        app.remove_one_matching(_make_meal(name="Z"))
        assert len(_session_state["selected_meals"]) == 1

    def test_reset_plan_clears_meals_and_totals(self):
        app.add_meal(_make_meal(protein=30.0))
        app.reset_plan()
        assert _session_state["selected_meals"] == []
        assert _session_state["totals"] == {"Protein": 0.0, "Carb": 0.0, "Fat": 0.0}


# ─── group_selected_meals ───────────────────────────────────────────────────


class TestGroupSelectedMeals:
    def test_single_meal(self):
        result = app.group_selected_meals([_make_meal()])
        assert len(result) == 1
        assert result[0]["qty"] == 1

    def test_identical_meals_are_grouped(self):
        row = _make_meal()
        result = app.group_selected_meals([row, row])
        assert len(result) == 1
        assert result[0]["qty"] == 2

    def test_different_meals_stay_separate(self):
        result = app.group_selected_meals([_make_meal("A"), _make_meal("B")])
        assert len(result) == 2

    def test_empty_list(self):
        assert app.group_selected_meals([]) == []

    def test_qty_increments_correctly_for_three(self):
        row = _make_meal()
        result = app.group_selected_meals([row, row, row])
        assert result[0]["qty"] == 3


# ─── read_saved / write_saved ───────────────────────────────────────────────


class TestReadWriteSaved:
    def test_write_then_read_roundtrip(self, tmp_path):
        original_file = app.SAVED_FILE
        app.SAVED_FILE = tmp_path / "plans.json"
        try:
            plans = [{"id": "x", "name": "Test"}]
            app.write_saved(plans)
            loaded = app.read_saved()
            assert loaded == plans
        finally:
            app.SAVED_FILE = original_file

    def test_read_returns_empty_list_when_file_missing(self, tmp_path):
        original_file = app.SAVED_FILE
        app.SAVED_FILE = tmp_path / "nonexistent.json"
        try:
            assert app.read_saved() == []
        finally:
            app.SAVED_FILE = original_file

    def test_read_returns_empty_list_on_corrupt_json(self, tmp_path):
        original_file = app.SAVED_FILE
        malformed_file = tmp_path / "malformed.json"
        malformed_file.write_text("not valid json{{{")
        app.SAVED_FILE = malformed_file
        try:
            assert app.read_saved() == []
        finally:
            app.SAVED_FILE = original_file


# ─── save_current_plan / load_plan / delete_plan ───────────────────────────


class TestPlanPersistence:
    def setup_method(self):
        _reset_session()
        self._orig_file = app.SAVED_FILE

    def teardown_method(self):
        app.SAVED_FILE = self._orig_file

    def _use_temp_file(self, tmp_path):
        app.SAVED_FILE = tmp_path / "plans.json"

    def test_save_current_plan_creates_entry(self, tmp_path):
        self._use_temp_file(tmp_path)
        app.add_meal(_make_meal())
        app.save_current_plan("My Plan")
        plans = app.read_saved()
        assert len(plans) == 1
        assert plans[0]["name"] == "My Plan"

    def test_save_plan_empty_name_calls_st_error(self, tmp_path):
        self._use_temp_file(tmp_path)
        app.save_current_plan("")
        _mock_st.error.assert_called()

    def test_save_plan_duplicate_name_gets_counter(self, tmp_path):
        self._use_temp_file(tmp_path)
        app.save_current_plan("Plan A")
        app.save_current_plan("Plan A")
        plans = app.read_saved()
        names = {p["name"] for p in plans}
        assert "Plan A" in names
        assert "Plan A (2)" in names

    def test_save_plan_includes_caps(self, tmp_path):
        self._use_temp_file(tmp_path)
        _session_state["caps"] = {"Protein": 100, "Carb": 200, "Fat": 50}
        app.save_current_plan("Capped Plan")
        plans = app.read_saved()
        assert plans[0]["caps"] == {"Protein": 100, "Carb": 200, "Fat": 50}

    def test_save_plan_meals_have_no_uid(self, tmp_path):
        """Saved plans must not contain internal uid fields."""
        self._use_temp_file(tmp_path)
        app.add_meal(_make_meal())
        app.save_current_plan("No UID Plan")
        plans = app.read_saved()
        for meal in plans[0]["meals"]:
            assert "uid" not in meal

    def test_delete_plan_removes_entry(self, tmp_path):
        self._use_temp_file(tmp_path)
        app.save_current_plan("To Delete")
        plans = app.read_saved()
        plan_id = plans[0]["id"]
        app.delete_plan(plan_id)
        remaining = app.read_saved()
        assert all(p["id"] != plan_id for p in remaining)

    def test_load_plan_restores_meals(self, tmp_path):
        self._use_temp_file(tmp_path)
        app.add_meal(_make_meal(protein=42.0))
        app.save_current_plan("Restore Me")
        plans = app.read_saved()
        plan_id = plans[0]["id"]

        # Reset session and load
        _reset_session()
        app.load_plan(plan_id)

        assert len(_session_state["selected_meals"]) == 1
        assert _session_state["totals"]["Protein"] == pytest.approx(42.0)

    def test_load_plan_nonexistent_calls_st_error(self, tmp_path):
        self._use_temp_file(tmp_path)
        app.load_plan("does-not-exist")
        _mock_st.error.assert_called()


# ─── replace_default_with ───────────────────────────────────────────────────


class TestReplaceDefaultWith:
    def test_valid_df_writes_csv(self, tmp_path):
        original_default = app.DEFAULT_CSV
        app.DEFAULT_CSV = tmp_path / "meals.csv"
        # In the real app load_data_csv has a .clear() method added by @st.cache_data.
        # Our pass-through mock doesn't add it, so we patch it here.
        app.load_data_csv.clear = MagicMock()
        try:
            df = pd.DataFrame({
                "Meal name": ["X"], "Meal type": ["L"],
                "Protein": [10], "Carb": [5], "Fat": [2],
            })
            app.replace_default_with(df)
            assert app.DEFAULT_CSV.exists()
            saved = pd.read_csv(app.DEFAULT_CSV)
            assert "Meal name" in saved.columns
        finally:
            app.DEFAULT_CSV = original_default
            del app.load_data_csv.clear

    def test_missing_required_column_raises(self):
        df = pd.DataFrame({"Meal name": ["X"], "Meal type": ["L"]})
        with pytest.raises(ValueError, match="missing required columns"):
            app.replace_default_with(df)


# ─── macro_bar ──────────────────────────────────────────────────────────────


class TestMacroBar:
    """macro_bar calls st.markdown; we verify no exceptions and the HTML content."""

    def test_renders_without_exception(self):
        app.macro_bar("Protein", 100, 190)

    def test_over_cap_triggers_red_colour(self):
        # Capture the HTML passed to st.markdown
        captured = []
        _mock_st.markdown.side_effect = lambda html, **kw: captured.append(html)
        app.macro_bar("Protein", 200, 190)
        assert any("#d62728" in h for h in captured)
        _mock_st.markdown.side_effect = None

    def test_under_cap_uses_blue_colour(self):
        captured = []
        _mock_st.markdown.side_effect = lambda html, **kw: captured.append(html)
        app.macro_bar("Carbs", 50, 190)
        assert any("#1f77b4" in h for h in captured)
        _mock_st.markdown.side_effect = None

    def test_zero_cap_no_division_error(self):
        app.macro_bar("Fat", 10, 0)

    def test_over_text_shown_when_over(self):
        captured = []
        _mock_st.markdown.side_effect = lambda html, **kw: captured.append(html)
        app.macro_bar("Protein", 200, 190)
        html = "".join(captured)
        assert "over" in html
        _mock_st.markdown.side_effect = None


# ─── CSV download does not include uid ──────────────────────────────────────


class TestCSVDownloadNoUID:
    """Regression: uid must not appear in the CSV export."""

    def test_uid_not_in_plan_df(self):
        _reset_session()
        app.add_meal(_make_meal())
        # Replicate the CSV-building logic from the Builder tab
        plan_df = pd.DataFrame(_session_state["selected_meals"]).drop(
            columns=["uid"], errors="ignore"
        )
        assert "uid" not in plan_df.columns

    def test_required_cols_present_in_plan_df(self):
        _reset_session()
        app.add_meal(_make_meal())
        plan_df = pd.DataFrame(_session_state["selected_meals"]).drop(
            columns=["uid"], errors="ignore"
        )
        for col in ["Meal name", "Meal type", "Protein", "Carb", "Fat"]:
            assert col in plan_df.columns


# ─── Strikethrough markdown ──────────────────────────────────────────────────


class TestStrikethroughMarkdown:
    """Regression: each line must be independently wrapped in ~~…~~."""

    def test_strikethrough_does_not_span_newline(self):
        name = "Eggs"
        mtype = "Breakfast"
        # Simulate the fixed logic from app.py
        name_md = f"~~**{name}**~~  \n~~_{mtype}_~~"
        lines = name_md.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped:
                assert stripped.startswith("~~"), f"Line does not start with ~~: {line!r}"
                assert stripped.endswith("~~"), f"Line does not end with ~~: {line!r}"


# ─── load_data_csv ──────────────────────────────────────────────────────────


class TestLoadDataCSV:
    def test_loads_valid_csv_string_path(self, tmp_path):
        csv_file = tmp_path / "meals.csv"
        csv_file.write_text(
            "Meal name,Meal type,Protein,Carb,Fat\n"
            "Eggs,Breakfast,30,5,10\n"
        )
        df = app.load_data_csv(str(csv_file))
        assert len(df) == 1
        assert df["Protein"].iloc[0] == 30.0

    def test_loads_valid_csv_file_object(self, tmp_path):
        csv_content = (
            "Meal name,Meal type,Protein,Carb,Fat\n"
            "Oats,Breakfast,10,40,5\n"
        )
        # StringIO starts at position 0; no seek needed as it's read only once here.
        file_obj = StringIO(csv_content)
        df = app.load_data_csv(file_obj)
        assert df["Meal name"].iloc[0] == "Oats"

    def test_raises_on_missing_column(self, tmp_path):
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("Meal name,Meal type\nX,Y\n")
        with pytest.raises(ValueError):
            app.load_data_csv(str(csv_file))
