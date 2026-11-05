from pathlib import Path
from uuid import uuid4
import pandas as pd
import pytest

from app import dataset_storage
from app.agents import analyst
from app.agents.analyst import execute_analysis_plan
from app.agents.reporter import generate_report, _format_currency_or_number
from app.agents.validator import validate_analysis
from app.graph.workflow import create_analysis_graph, _fallback_plan, _profile_dataset
from app.services.semantic_detection import (
    profile_schema_semantics,
    find_best_date_column,
    match_query_column,
    is_currency_metric,
)
from app.services.suggestion_service import generate_suggested_questions
from app.storage import database


@pytest.fixture
def multi_domain_datasets(tmp_path, monkeypatch):
    """Create isolated deterministic datasets across retail, weather, education, and real estate."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)

    # 1. Retail
    retail_id = str(uuid4())
    retail_df = pd.DataFrame([
        {"order_date": "2026-01-10", "product": "Widget A", "region": "North", "quantity": 10, "unit_price": 50.0, "discount": 10.0},
        {"order_date": "2026-01-20", "product": "Widget B", "region": "South", "quantity": 5, "unit_price": 100.0, "discount": 0.0},
        {"order_date": "2026-02-15", "product": "Widget A", "region": "North", "quantity": 20, "unit_price": 50.0, "discount": 10.0},
        {"order_date": "2026-02-25", "product": "Widget C", "region": "East", "quantity": 8, "unit_price": 75.0, "discount": 5.0},
        {"order_date": "2026-03-05", "product": "Widget B", "region": "South", "quantity": 12, "unit_price": 100.0, "discount": 0.0},
    ])
    retail_df.to_csv(upload_dir / f"{retail_id}.csv", index=False)

    # 2. Weather
    weather_id = str(uuid4())
    weather_df = pd.DataFrame([
        {"timestamp": "2026-01-01 12:00:00", "temperature": 15.0, "humidity": 80.0, "pressure": 1013.2, "wind_speed": 12.5},
        {"timestamp": "2026-01-15 12:00:00", "temperature": 18.0, "humidity": 75.0, "pressure": 1015.0, "wind_speed": 10.0},
        {"timestamp": "2026-02-01 12:00:00", "temperature": 22.0, "humidity": 60.0, "pressure": 1012.0, "wind_speed": 15.0},
        {"timestamp": "2026-02-15 12:00:00", "temperature": 25.0, "humidity": 55.0, "pressure": 1010.5, "wind_speed": 18.0},
        {"timestamp": "2026-03-01 12:00:00", "temperature": 28.0, "humidity": 50.0, "pressure": 1008.0, "wind_speed": 20.0},
    ])
    weather_df.to_csv(upload_dir / f"{weather_id}.csv", index=False)

    # 3. Education
    education_id = str(uuid4())
    education_df = pd.DataFrame([
        {"student_id": "STU001", "subject": "Mathematics", "marks": 85.0, "attendance": 92.0, "grade": "A"},
        {"student_id": "STU002", "subject": "Mathematics", "marks": 70.0, "attendance": 80.0, "grade": "B"},
        {"student_id": "STU003", "subject": "Science", "marks": 90.0, "attendance": 95.0, "grade": "A"},
        {"student_id": "STU004", "subject": "Science", "marks": 60.0, "attendance": 70.0, "grade": "C"},
        {"student_id": "STU005", "subject": "History", "marks": 75.0, "attendance": 85.0, "grade": "B"},
        {"student_id": "STU006", "subject": "History", "marks": 80.0, "attendance": 88.0, "grade": "B"},
    ])
    education_df.to_csv(upload_dir / f"{education_id}.csv", index=False)

    # 4. Real Estate
    real_estate_id = str(uuid4())
    real_estate_df = pd.DataFrame([
        {"property_id": "PROP001", "area": 1200.0, "bedrooms": 2, "location": "Downtown", "property_price": 350000.0},
        {"property_id": "PROP002", "area": 1800.0, "bedrooms": 3, "location": "Downtown", "property_price": 520000.0},
        {"property_id": "PROP003", "area": 950.0, "bedrooms": 1, "location": "Suburbs", "property_price": 210000.0},
        {"property_id": "PROP004", "area": 2400.0, "bedrooms": 4, "location": "Suburbs", "property_price": 480000.0},
        {"property_id": "PROP005", "area": 1500.0, "bedrooms": 3, "location": "Midtown", "property_price": 410000.0},
    ])
    real_estate_df.to_csv(upload_dir / f"{real_estate_id}.csv", index=False)

    return {
        "retail": (retail_id, retail_df),
        "weather": (weather_id, weather_df),
        "education": (education_id, education_df),
        "real_estate": (real_estate_id, real_estate_df),
    }


# 1. Profiling unfamiliar schemas
def test_profiling_unfamiliar_schemas(multi_domain_datasets):
    for domain, (dataset_id, df) in multi_domain_datasets.items():
        profile = _profile_dataset(dataset_id)
        assert profile["rows"] == len(df)
        assert profile["columns"] == len(df.columns)
        assert set(profile["column_names"]) == set(df.columns)
        assert "numerical_columns" in profile


# 2. Generating relevant suggestions from schema
def test_generating_relevant_suggestions(multi_domain_datasets):
    # Weather
    weather_id, weather_df = multi_domain_datasets["weather"]
    weather_profile = _profile_dataset(weather_id)
    weather_sugg = generate_suggested_questions(weather_id, weather_profile)

    questions = [s["question"] for s in weather_sugg["suggestions"]]
    assert len(questions) >= 3
    # Check that temperature or humidity is in the questions
    assert any("temperature" in q.lower() or "humidity" in q.lower() for q in questions)
    # Check that retail columns like sales/revenue/profit are NOT suggested
    assert not any("sales" in q.lower() or "revenue" in q.lower() for q in questions)


# 3. Rejecting suggestions that reference missing columns
def test_rejecting_suggestions_with_missing_columns():
    profile = {
        "column_names": ["temperature", "humidity"],
        "dtypes": {"temperature": "float64", "humidity": "float64"},
    }
    sugg = generate_suggested_questions("test-ds", profile)
    for s in sugg["suggestions"]:
        for col in s.get("target_columns", []):
            assert col in ["temperature", "humidity"]


# 4. Fallback planning without retail-specific defaults
def test_fallback_planning_without_retail_defaults(multi_domain_datasets):
    weather_id, _ = multi_domain_datasets["weather"]
    weather_profile = _profile_dataset(weather_id)

    # Query for correlation in weather dataset
    plan = _fallback_plan("What is the correlation between temperature and humidity?", weather_profile)
    assert any(step["action"] == "calculate_correlation" for step in plan)
    corr_step = next(s for s in plan if s["action"] == "calculate_correlation")
    assert corr_step["parameters"]["column_a"] == "temperature"
    assert corr_step["parameters"]["column_b"] == "humidity"


# 5. Numeric descriptive statistics with verified calculations
def test_numeric_descriptive_statistics_accuracy(multi_domain_datasets):
    weather_id, weather_df = multi_domain_datasets["weather"]
    weather_profile = _profile_dataset(weather_id)

    plan = _fallback_plan("What is the average temperature?", weather_profile)
    state = {
        "dataset_id": weather_id,
        "user_query": "What is the average temperature?",
        "analysis_plan": plan,
        "dataset_profile": weather_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "evidence": [],
    }

    result_state = execute_analysis_plan(state)
    findings = result_state["findings"]
    stats_finding = next(f for f in findings if f.get("type") == "descriptive_statistics")

    # Mathematical truth: (15 + 18 + 22 + 25 + 28) / 5 = 21.6
    assert pytest.approx(stats_finding["mean"], 0.001) == 21.6
    assert stats_finding["min"] == 15.0
    assert stats_finding["max"] == 28.0
    assert stats_finding["count"] == 5


# 6. Categorical aggregation with verified grouping
def test_categorical_aggregation_accuracy(multi_domain_datasets):
    edu_id, edu_df = multi_domain_datasets["education"]
    edu_profile = _profile_dataset(edu_id)

    plan = _fallback_plan("Which subject has the highest average marks?", edu_profile)
    state = {
        "dataset_id": edu_id,
        "user_query": "Which subject has the highest average marks?",
        "analysis_plan": plan,
        "dataset_profile": edu_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "evidence": [],
    }

    result_state = execute_analysis_plan(state)
    group_finding = next(f for f in result_state["findings"] if f.get("type") == "group_aggregate")
    assert group_finding["metric"] == "marks"
    assert group_finding["dimension"] == "subject"

    # In education data: Maths (85+70)/2 = 77.5, History (75+80)/2 = 77.5, Science (90+60)/2 = 75.0
    assert pytest.approx(group_finding["highest"]["marks"], 0.01) == 77.5


# 7. Time-series aggregation
def test_time_series_aggregation_accuracy(multi_domain_datasets, tmp_path, monkeypatch):
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")
    weather_id, weather_df = multi_domain_datasets["weather"]
    weather_profile = _profile_dataset(weather_id)

    plan = _fallback_plan("Show monthly temperature trends.", weather_profile)
    state = {
        "dataset_id": weather_id,
        "user_query": "Show monthly temperature trends.",
        "analysis_plan": plan,
        "dataset_profile": weather_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "evidence": [],
        "session_id": str(uuid4()),
    }

    result_state = execute_analysis_plan(state)
    trend_finding = next(f for f in result_state["findings"] if f.get("type") == "time_series_trend")
    assert trend_finding["metric"] == "temperature"
    assert trend_finding["dimension"] == "month"
    # Months: 2026-01 (15+18=33), 2026-02 (22+25=47), 2026-03 (28)
    # Total temp sum: 15+18+22+25+28 = 108.0
    assert pytest.approx(trend_finding["total"], 0.01) == 108.0


# 8. Correlation with eligible numeric columns
def test_correlation_accuracy(multi_domain_datasets):
    weather_id, weather_df = multi_domain_datasets["weather"]
    weather_profile = _profile_dataset(weather_id)

    plan = _fallback_plan("Calculate correlation between temperature and humidity", weather_profile)
    state = {
        "dataset_id": weather_id,
        "user_query": "Calculate correlation between temperature and humidity",
        "analysis_plan": plan,
        "dataset_profile": weather_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "evidence": [],
    }

    result_state = execute_analysis_plan(state)
    corr_finding = next(f for f in result_state["findings"] if f.get("type") == "correlation")
    # Expected Pearson correlation is strongly negative: approx -0.993
    assert corr_finding["value"] < -0.95


# 9. Missing date columns handled without fabricating dates
def test_missing_date_column_graceful_handling(multi_domain_datasets):
    edu_id, _ = multi_domain_datasets["education"]
    edu_profile = _profile_dataset(edu_id)

    plan = _fallback_plan("Show monthly marks trends", edu_profile)
    # Since education has NO date column, fallback should NOT plan group by month line chart
    assert not any(s["action"] == "create_line_chart" for s in plan)
    # Instead it runs descriptive statistics
    assert any(s["action"] == "calculate_descriptive_statistics" for s in plan)


# 10. Constant or invalid numeric columns
def test_constant_numeric_columns(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)

    ds_id = str(uuid4())
    df = pd.DataFrame([
        {"item": "A", "val": 10.0, "val2": 15.0, "constant_col": 5.0},
        {"item": "B", "val": 20.0, "val2": 25.0, "constant_col": 5.0},
        {"item": "C", "val": 30.0, "val2": 35.0, "constant_col": 5.0},
    ])
    df.to_csv(upload_dir / f"{ds_id}.csv", index=False)
    profile = _profile_dataset(ds_id)

    # Fallback planning should pick columns with variation (val, val2)
    plan = _fallback_plan("What is the correlation between variables?", profile)
    corr_step = next(s for s in plan if s["action"] == "calculate_correlation")
    assert corr_step["parameters"]["column_a"] in ("val", "val2")
    assert corr_step["parameters"]["column_b"] in ("val", "val2")
    assert corr_step["parameters"]["column_a"] != corr_step["parameters"]["column_b"]


# 11. Ambiguous semantic matching
def test_semantic_query_column_matching():
    available = ["temp_c", "relative_humidity", "wind_velocity_kph"]
    assert match_query_column("What is the average temperature?", available) == "temp_c"
    assert match_query_column("Check humidity levels", available) == "relative_humidity"
    # Query with non-existent concept returns None rather than inventing a column
    assert match_query_column("What is the total revenue?", available) is None


# 12. Multi-currency and neutral unit formatting
def test_currency_and_unit_formatting():
    from app.services.semantic_detection import is_monetary_metric, detect_currency_symbol

    # Explicit currency headers
    assert _format_currency_or_number(50000, "salary_usd") == "$50,000.00"
    assert _format_currency_or_number(50000, "salary ($)") == "$50,000.00"
    assert _format_currency_or_number(50000, "salary_eur") == "€50,000.00"
    assert _format_currency_or_number(50000, "salary_gbp") == "£50,000.00"
    assert _format_currency_or_number(50000, "salary_inr") == "₹50,000.00"
    assert _format_currency_or_number(50000, "salary_jpy") == "¥50,000.00"

    # Explicit dataset-level configuration
    assert _format_currency_or_number(50000, "salary", {"currency": "INR"}) == "₹50,000.00"
    assert _format_currency_or_number(50000, "salary", {"currency": "EUR"}) == "€50,000.00"

    # Unknown / unstated currency: neutral formatting without assuming USD
    assert "$" not in _format_currency_or_number(100.5, "property_price")
    assert _format_currency_or_number(100.5, "property_price") == "100.50"
    assert "$" not in _format_currency_or_number(50000, "salary")
    assert _format_currency_or_number(50000, "salary") == "50,000.00"
    assert "$" not in _format_currency_or_number(1200, "revenue")
    assert _format_currency_or_number(1200, "revenue") == "1,200.00"

    # Monetary classification vs currency detection distinction
    assert is_monetary_metric("salary") is True
    assert detect_currency_symbol("salary")[1] is None
    assert detect_currency_symbol("salary_inr")[1] == "₹"

    # Non-monetary metrics NEVER receive currency symbols
    assert "$" not in _format_currency_or_number(24.5, "temperature")
    assert "$" not in _format_currency_or_number(65, "humidity")
    assert "$" not in _format_currency_or_number(85, "marks")
    assert "$" not in _format_currency_or_number(1500, "area")
    assert "$" not in _format_currency_or_number(92, "attendance")


# 13. Domain-agnostic report formatting
def test_domain_agnostic_report_formatting(multi_domain_datasets, tmp_path, monkeypatch):
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")
    real_estate_id, _ = multi_domain_datasets["real_estate"]
    real_estate_profile = _profile_dataset(real_estate_id)

    plan = _fallback_plan("What is the average property_price by location?", real_estate_profile)
    state = {
        "dataset_id": real_estate_id,
        "user_query": "What is the average property_price by location?",
        "analysis_plan": plan,
        "dataset_profile": real_estate_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "evidence": [],
        "session_id": str(uuid4()),
    }
    executed_state = execute_analysis_plan(state)
    validated_state = validate_analysis(executed_state)
    reported_state = generate_report(validated_state)

    report = reported_state["final_report"]
    assert "property_price" in report
    assert "location" in report
    # The methodology should NOT claim retail discount formulas on real estate
    assert "Item-level discounts are subtracted directly from gross transaction sales" not in report
    assert "Methodology & Calculation Assumptions" in report


# 14. Dataset ownership isolation for suggestions
def test_dataset_ownership_isolation(api_test_client, multi_domain_datasets):
    from app.auth import Principal, require_principal
    from app.api.main import app

    weather_id, _ = multi_domain_datasets["weather"]
    owner_a = database.get_or_create_user("https://test.auth0.com/", "user_a_owner")
    owner_b = database.get_or_create_user("https://test.auth0.com/", "user_b_attacker")

    # Register dataset under owner_a
    database.register_dataset(weather_id, owner_a, ".csv")

    # Attacker tries to get suggestions for owner_a's dataset
    app.dependency_overrides[require_principal] = lambda: Principal(
        issuer="https://test.auth0.com/",
        subject="user_b_attacker",
    )
    res = api_test_client.get(f"/api/datasets/{weather_id}/suggested-questions")
    assert res.status_code == 404

    # Legitimate owner accesses suggestions
    app.dependency_overrides[require_principal] = lambda: Principal(
        issuer="https://test.auth0.com/",
        subject="user_a_owner",
    )
    res_owner = api_test_client.get(f"/api/datasets/{weather_id}/suggested-questions")
    assert res_owner.status_code == 200
    assert len(res_owner.json()["suggestions"]) > 0


# 15. Existing retail analysis regression
def test_existing_retail_regression(multi_domain_datasets, tmp_path, monkeypatch):
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")
    retail_id, _ = multi_domain_datasets["retail"]
    retail_profile = _profile_dataset(retail_id)

    plan = _fallback_plan("Which region generated the most revenue?", retail_profile)
    state = {
        "dataset_id": retail_id,
        "user_query": "Which region generated the most revenue?",
        "analysis_plan": plan,
        "dataset_profile": retail_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "evidence": [],
        "session_id": str(uuid4()),
    }
    executed = execute_analysis_plan(state)
    assert executed["status"] in ("analyzed", "executed")
    group_finding = next(f for f in executed["findings"] if f.get("type") == "group_aggregate")
    assert group_finding["highest"]["region"] == "South"
    assert group_finding["highest"]["revenue"] == pytest.approx(1200.0)


# 16. BFF route validation
def test_bff_suggested_questions_route(api_test_client, multi_domain_datasets):
    from app.auth import Principal, require_principal
    from app.api.main import app

    edu_id, _ = multi_domain_datasets["education"]
    owner = database.get_or_create_user("https://test.auth0.com/", "edu_owner")
    database.register_dataset(edu_id, owner, ".csv")

    app.dependency_overrides[require_principal] = lambda: Principal(
        issuer="https://test.auth0.com/",
        subject="edu_owner",
    )
    res = api_test_client.get(f"/api/datasets/suggested-questions/{edu_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["dataset_id"] == edu_id
    assert len(body["suggestions"]) >= 3


# 17. Session and report persistence
def test_session_and_report_persistence(api_test_client, multi_domain_datasets, tmp_path, monkeypatch):
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")
    weather_id, _ = multi_domain_datasets["weather"]
    owner = database.get_or_create_user("https://test.auth0.com/", "weather_user")
    database.register_dataset(weather_id, owner, ".csv")

    graph = create_analysis_graph()
    session_id = str(uuid4())
    state = {
        "session_id": session_id,
        "user_query": "What is the average humidity?",
        "dataset_id": weather_id,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }
    result = graph.invoke(state)
    assert result["status"] == "analyzed"
    assert "humidity" in result["final_report"].lower()

    # Save session with ownership
    database.save_analysis_session_owned(result, owner)
    saved = database.get_owned_analysis_session(session_id, owner)
    assert saved is not None
    assert saved["session_id"] == session_id
    assert "humidity" in saved["final_report"].lower()


# 18. No stale suggestions across dataset changes
def test_no_stale_suggestions_across_dataset_changes(multi_domain_datasets):
    weather_id, _ = multi_domain_datasets["weather"]
    edu_id, _ = multi_domain_datasets["education"]

    weather_profile = _profile_dataset(weather_id)
    edu_profile = _profile_dataset(edu_id)

    weather_sugg = generate_suggested_questions(weather_id, weather_profile)
    edu_sugg = generate_suggested_questions(edu_id, edu_profile)

    weather_questions = [s["question"] for s in weather_sugg["suggestions"]]
    edu_questions = [s["question"] for s in edu_sugg["suggestions"]]

    # They should be completely distinct
    assert set(weather_questions) != set(edu_questions)
    # Education should not mention temperature
    assert not any("temperature" in q.lower() for q in edu_questions)
    # Weather should not mention marks
    assert not any("marks" in q.lower() for q in weather_questions)


# 19. Missing discount handling (no NaN propagation, no silent zero replacement)
def test_missing_discount_handling_mixed_valid_and_missing(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)

    ds_id = str(uuid4())
    df = pd.DataFrame([
        {"item": "A", "quantity": 10, "unit_price": 100.0, "discount_pct": 10.0},
        {"item": "B", "quantity": 20, "unit_price": 100.0, "discount_pct": None},  # Missing discount
        {"item": "C", "quantity": 30, "unit_price": 100.0, "discount_pct": 20.0},
    ])
    df.to_csv(upload_dir / f"{ds_id}.csv", index=False)

    loaded = analyst._load_dataset(ds_id)
    # Gross revenue must be computed across all records without NaN
    assert loaded["gross_sales"].tolist() == [1000.0, 2000.0, 3000.0]
    # Net revenue calculated strictly where discount is valid
    assert loaded.loc[0, "net_revenue"] == 900.0
    assert pd.isna(loaded.loc[1, "net_revenue"])
    assert loaded.loc[2, "net_revenue"] == 2400.0
    # Metadata records missing observation
    meta = loaded.attrs.get("discount_metadata", {})
    assert meta.get("missing_records_count") == 1
    assert meta.get("valid_records_count") == 2


# 20. Discount-scale ambiguity handling
def test_discount_scale_ambiguity(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)

    # Case A: Explicit percentage convention
    ds_a = str(uuid4())
    df_a = pd.DataFrame([{"quantity": 10, "unit_price": 100.0, "discount_pct": 0.5}])
    df_a.to_csv(upload_dir / f"{ds_a}.csv", index=False)
    loaded_a = analyst._load_dataset(ds_a)
    assert pytest.approx(loaded_a.loc[0, "net_revenue"], 0.01) == 995.0  # 0.5%

    # Case B: Explicit fractional rate convention
    ds_b = str(uuid4())
    df_b = pd.DataFrame([{"quantity": 10, "unit_price": 100.0, "discount_rate": 0.5}])
    df_b.to_csv(upload_dir / f"{ds_b}.csv", index=False)
    loaded_b = analyst._load_dataset(ds_b)
    assert pytest.approx(loaded_b.loc[0, "net_revenue"], 0.01) == 500.0  # 50%

    # Case C: Ambiguous convention (named 'discount' with max <= 1.0)
    ds_c = str(uuid4())
    df_c = pd.DataFrame([{"quantity": 10, "unit_price": 100.0, "discount": 0.5}])
    df_c.to_csv(upload_dir / f"{ds_c}.csv", index=False)
    loaded_c = analyst._load_dataset(ds_c)
    # Net revenue derivation must NOT be automatically applied on ambiguous convention
    assert "net_revenue" not in loaded_c.columns
    assert loaded_c.loc[0, "revenue"] == 1000.0  # Reports gross revenue
    meta_c = loaded_c.attrs.get("discount_metadata", {})
    assert "ambiguity_warning" in meta_c


# 21. Deterministic suggestion rotation and pagination
def test_suggestion_rotation_and_pagination(multi_domain_datasets):
    weather_id, weather_df = multi_domain_datasets["weather"]
    weather_profile = _profile_dataset(weather_id)

    sugg_page1 = generate_suggested_questions(weather_id, weather_profile, max_suggestions=4, offset=0)
    sugg_page2 = generate_suggested_questions(weather_id, weather_profile, max_suggestions=4, offset=4)

    q_page1 = [s["question"] for s in sugg_page1["suggestions"]]
    q_page2 = [s["question"] for s in sugg_page2["suggestions"]]

    # When enough candidates exist, regenerating with offset rotates candidates
    assert q_page1 != q_page2
    # All questions reference valid columns
    all_cols = set(weather_df.columns)
    for s in sugg_page1["suggestions"] + sugg_page2["suggestions"]:
        for col in s.get("target_columns", []):
            assert col in all_cols


# 22. No numeric columns handling
def test_no_numeric_columns_handling(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)

    # Entirely categorical dataset
    cat_id = str(uuid4())
    cat_df = pd.DataFrame([
        {"department": "HR", "status": "Active", "location": "NY"},
        {"department": "IT", "status": "Active", "location": "SF"},
        {"department": "IT", "status": "On Leave", "location": "NY"},
    ])
    cat_df.to_csv(upload_dir / f"{cat_id}.csv", index=False)
    cat_profile = _profile_dataset(cat_id)

    # Query asking for numerical calculation (average)
    plan_avg = _fallback_plan("What is the average?", cat_profile)
    # Never selects string column for descriptive statistics
    assert not any(s["action"] == "calculate_descriptive_statistics" for s in plan_avg)

    # Execute analysis plan
    state = {
        "dataset_id": cat_id,
        "user_query": "What is the average?",
        "analysis_plan": plan_avg,
        "dataset_profile": cat_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "errors": [],
    }
    executed = execute_analysis_plan(state)
    assert executed["status"] == "analyzed"
    # Explanatory finding returned rather than unhandled TypeError
    exp = next((f for f in executed["findings"] if f.get("type") == "explanation"), None)
    assert exp is not None
    assert "no numerical columns" in exp["message"]


# 23. Empty dataset and all-null column handling
def test_empty_dataset_and_all_null_columns(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)

    # Empty dataset
    empty_id = str(uuid4())
    empty_df = pd.DataFrame(columns=["col_a", "col_b"])
    empty_df.to_csv(upload_dir / f"{empty_id}.csv", index=False)
    empty_profile = _profile_dataset(empty_id)

    state_empty = {
        "dataset_id": empty_id,
        "user_query": "Summarize data",
        "analysis_plan": [{"step": 1, "action": "profile_dataset"}],
        "dataset_profile": empty_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "errors": [],
    }
    exec_empty = execute_analysis_plan(state_empty)
    assert exec_empty["status"] == "analyzed"
    assert any("empty" in f.get("message", "").lower() for f in exec_empty["findings"])

    # All-null numeric column
    null_id = str(uuid4())
    null_df = pd.DataFrame([
        {"item": "A", "val": None},
        {"item": "B", "val": None},
    ])
    null_df.to_csv(upload_dir / f"{null_id}.csv", index=False)
    null_profile = _profile_dataset(null_id)

    state_null = {
        "dataset_id": null_id,
        "user_query": "What is the average val?",
        "analysis_plan": [
            {"step": 1, "action": "profile_dataset"},
            {"step": 2, "action": "calculate_descriptive_statistics", "parameters": {"columns": ["val"]}},
        ],
        "dataset_profile": null_profile,
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "errors": [],
    }
    exec_null = execute_analysis_plan(state_null)
    assert exec_null["status"] == "analyzed"
    stat_finding = next((f for f in exec_null["findings"] if f.get("type") == "descriptive_statistics"), None)
    assert stat_finding is not None
    assert stat_finding.get("all_null") is True


# 24. Transaction status tracking
def test_transaction_status_handling(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)

    status_id = str(uuid4())
    status_df = pd.DataFrame([
        {"order_id": "ORD01", "quantity": 10, "unit_price": 50.0, "status": "Completed"},
        {"order_id": "ORD02", "quantity": 5, "unit_price": 100.0, "status": "Cancelled"},
        {"order_id": "ORD03", "quantity": 8, "unit_price": 50.0, "status": "Completed"},
        {"order_id": "ORD04", "quantity": 2, "unit_price": 75.0, "status": "Returned"},
    ])
    status_df.to_csv(upload_dir / f"{status_id}.csv", index=False)
    loaded = analyst._load_dataset(status_id)
    meta = loaded.attrs.get("status_metadata", {})
    assert meta.get("cancelled_count") == 1
    assert meta.get("returned_count") == 1
    assert meta.get("completed_count") == 2
