import os
from pathlib import Path
from shutil import copyfile
from uuid import uuid4

import pandas as pd
import pytest

from app import dataset_storage
from app.graph.workflow import create_analysis_graph, _fallback_plan
from app.agents.analyst import execute_analysis_plan
from app.agents.validator import validate_analysis
from app.agents.reporter import generate_report


@pytest.fixture
def deterministic_sales_dataset(tmp_path, monkeypatch):
    """Create a deterministic sales dataset with date, quantity, price, discount, and revenue."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    dataset_id = str(uuid4())

    # Deterministic test rows with known calendar dates
    data = [
        {"OrderDate": "2026-01-05", "region": "North", "Quantity": 2, "UnitSellingPrice": 60000.0, "DiscountPercentage": 0, "revenue": 120000.0},
        {"OrderDate": "2026-01-12", "region": "South", "Quantity": 5, "UnitSellingPrice": 15000.0, "DiscountPercentage": 0, "revenue": 75000.0},
        {"OrderDate": "2026-01-20", "region": "East", "Quantity": 1, "UnitSellingPrice": 60000.0, "DiscountPercentage": 0, "revenue": 60000.0},
        {"OrderDate": "2026-02-03", "region": "West", "Quantity": 3, "UnitSellingPrice": 30000.0, "DiscountPercentage": 0, "revenue": 90000.0},
        {"OrderDate": "2026-02-14", "region": "North", "Quantity": 4, "UnitSellingPrice": 15000.0, "DiscountPercentage": 0, "revenue": 60000.0},
        {"OrderDate": "2026-02-22", "region": "South", "Quantity": 2, "UnitSellingPrice": 60000.0, "DiscountPercentage": 0, "revenue": 120000.0},
        {"OrderDate": "2026-03-04", "region": "East", "Quantity": 3, "UnitSellingPrice": 15000.0, "DiscountPercentage": 0, "revenue": 45000.0},
        {"OrderDate": "2026-03-18", "region": "West", "Quantity": 2, "UnitSellingPrice": 60000.0, "DiscountPercentage": 0, "revenue": 120000.0},
        {"OrderDate": "2026-03-25", "region": "North", "Quantity": 4, "UnitSellingPrice": 30000.0, "DiscountPercentage": 0, "revenue": 120000.0},
        {"OrderDate": "2026-04-02", "region": "South", "Quantity": 6, "UnitSellingPrice": 15000.0, "DiscountPercentage": 0, "revenue": 90000.0},
    ]
    df = pd.DataFrame(data)
    csv_path = upload_dir / f"{dataset_id}.csv"
    df.to_csv(csv_path, index=False)

    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)
    return dataset_id


@pytest.fixture
def dataset_without_date(tmp_path, monkeypatch):
    """Create a dataset that intentionally has NO date or timestamp column."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    dataset_id = str(uuid4())

    data = [
        {"product": "Laptop", "category": "Tech", "Quantity": 10, "UnitSellingPrice": 500.0, "DiscountPercentage": 0, "revenue": 5000.0},
        {"product": "Phone", "category": "Tech", "Quantity": 20, "UnitSellingPrice": 300.0, "DiscountPercentage": 10, "revenue": 5400.0},
        {"product": "Desk", "category": "Furniture", "Quantity": 5, "UnitSellingPrice": 150.0, "DiscountPercentage": 0, "revenue": 750.0},
    ]
    df = pd.DataFrame(data)
    csv_path = upload_dir / f"{dataset_id}.csv"
    df.to_csv(csv_path, index=False)

    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)
    return dataset_id


def test_monthly_revenue_trend_intent_and_execution(deterministic_sales_dataset, tmp_path, monkeypatch):
    """1, 2, 3, 4: Monthly revenue question selects time-series aggregation, groups by month chronologically, matches line chart."""
    from app.agents import analyst
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")

    graph = create_analysis_graph()
    initial_state = {
        "session_id": str(uuid4()),
        "user_query": "Show monthly revenue trends.",
        "dataset_id": deterministic_sales_dataset,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }

    result = graph.invoke(initial_state)

    assert result["status"] == "analyzed"

    # Verify plan executed group_and_aggregate on month with line chart
    actions = [tc["action"] for tc in result["tool_calls"]]
    assert "group_and_aggregate" in actions
    assert "create_line_chart" in actions

    # Verify parameters used "month" and "revenue"
    group_call = next(tc for tc in result["tool_calls"] if tc["action"] == "group_and_aggregate")
    assert group_call["parameters"]["group_by"] == "month"
    assert group_call["parameters"]["metric"] == "revenue"

    line_call = next(tc for tc in result["tool_calls"] if tc["action"] == "create_line_chart")
    assert line_call["parameters"]["x_column"] == "month"
    assert line_call["parameters"]["y_column"] == "revenue"

    # Verify chronological ordering and exact aggregation values
    group_res = next(tr["result"] for tr in result["tool_results"] if tr["action"] == "group_and_aggregate")
    months = [r["month"] for r in group_res]
    revenues = [r["revenue"] for r in group_res]

    expected_months = ["2026-01", "2026-02", "2026-03", "2026-04"]
    expected_revenues = [255000.0, 270000.0, 285000.0, 90000.0]

    assert months == expected_months, f"Expected {expected_months}, got {months}"
    assert revenues == expected_revenues, f"Expected {expected_revenues}, got {revenues}"

    # Verify time_series_trend finding was created
    trend_finding = next((f for f in result["findings"] if f.get("type") == "time_series_trend"), None)
    assert trend_finding is not None
    assert trend_finding["highest"]["month"] == "2026-03"
    assert trend_finding["highest"]["revenue"] == 285000.0
    assert trend_finding["lowest"]["month"] == "2026-04"
    assert trend_finding["lowest"]["revenue"] == 90000.0
    assert trend_finding["total"] == 900000.0

    # Verify line chart file was created
    assert len(result["visualizations"]) == 1
    assert Path(result["visualizations"][0]).exists()


def test_dataset_without_date_does_not_fabricate_trend(dataset_without_date):
    """5: A dataset without a date column does not produce a fabricated trend."""
    graph = create_analysis_graph()
    initial_state = {
        "session_id": str(uuid4()),
        "user_query": "Show monthly revenue trends.",
        "dataset_id": dataset_without_date,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }

    result = graph.invoke(initial_state)

    # Workflow must NOT execute a fake monthly group_and_aggregate or line chart
    actions = [tc["action"] for tc in result["tool_calls"]]
    assert "create_line_chart" not in actions

    # Validation must catch the missing date dimension
    dim_check = next((c for c in result["validation_results"] if c["check"] == "dimension_and_metric_presence"), None)
    assert dim_check is not None
    assert dim_check["passed"] is False
    assert "date" in dim_check["message"].lower() or "timestamp" in dim_check["message"].lower()


def test_population_label_never_appears_in_sales_analysis(deterministic_sales_dataset, tmp_path, monkeypatch):
    """6: Population labels never appear in an unrelated sales analysis."""
    from app.agents import analyst
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")

    graph = create_analysis_graph()
    initial_state = {
        "session_id": str(uuid4()),
        "user_query": "What are the average sales across all records?",
        "dataset_id": deterministic_sales_dataset,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }

    result = graph.invoke(initial_state)

    # Check findings messages
    for f in result["findings"]:
        msg = f.get("message", "").lower()
        assert "population" not in msg, f"Found 'population' in finding: {msg}"

    # Check final report
    report = result["final_report"].lower()
    assert "population" not in report, "Found 'population' in final report text"

    # Check validation check
    val_check = next(c for c in result["validation_results"] if c["check"] == "result_metric_alignment")
    assert val_check["passed"] is True


def test_previous_session_findings_do_not_leak(deterministic_sales_dataset, tmp_path, monkeypatch):
    """7: Previous session findings do not leak into a new report."""
    from app.agents import analyst
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")

    graph = create_analysis_graph()

    # Session 1: Revenue by region
    session_1 = {
        "session_id": str(uuid4()),
        "user_query": "What is the total revenue by region?",
        "dataset_id": deterministic_sales_dataset,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }
    result_1 = graph.invoke(session_1)

    # Session 2: Descriptive statistics on sales
    session_2 = {
        "session_id": str(uuid4()),
        "user_query": "What are the average sales across all records?",
        "dataset_id": deterministic_sales_dataset,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }
    result_2 = graph.invoke(session_2)

    # Session 2 must not contain any region grouping findings from session 1
    session_2_types = [f.get("type") for f in result_2["findings"]]
    assert "group_aggregate" not in session_2_types
    assert "North" not in result_2["final_report"]
    assert "South" not in result_2["final_report"]


def test_descriptive_statistics_still_works(deterministic_sales_dataset, tmp_path, monkeypatch):
    """8: Descriptive-statistics questions still work."""
    from app.agents import analyst
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")

    graph = create_analysis_graph()
    initial_state = {
        "session_id": str(uuid4()),
        "user_query": "What are the average sales across all records?",
        "dataset_id": deterministic_sales_dataset,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }

    result = graph.invoke(initial_state)

    assert result["status"] == "analyzed"
    stats_finding = next(f for f in result["findings"] if f.get("type") == "descriptive_statistics")
    assert stats_finding["mean"] == 90000.0  # (900000 / 10)
    assert stats_finding["count"] == 10
    assert stats_finding["min"] == 45000.0
    assert stats_finding["max"] == 120000.0


def test_redesigned_final_report_structure(deterministic_sales_dataset, tmp_path, monkeypatch):
    """10, 11: Report contains user-friendly content, 10 sections, and collapsed technical details."""
    from app.agents import analyst
    monkeypatch.setattr(analyst, "PRIVATE_REPORT_ROOT", tmp_path / "charts")

    graph = create_analysis_graph()
    initial_state = {
        "session_id": str(uuid4()),
        "user_query": "Show monthly revenue trends.",
        "dataset_id": deterministic_sales_dataset,
        "status": "created",
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "evidence": [],
        "validation_results": [],
        "errors": [],
    }

    result = graph.invoke(initial_state)
    report = result["final_report"]

    # Verify all 10 required sections are present
    assert "# Autonomous Data Analyst Report" in report
    assert "**Analytical Question:**" in report
    assert "**Dataset Overview:**" in report
    assert "## 1. Executive Summary" in report
    assert "## 2. Key Numerical Findings" in report
    assert "## 3. Visualizations & Charts" in report
    assert "## 4. Observations & Business Insights" in report
    assert "## 5. Methodology & Calculation Assumptions" in report
    assert "## 6. Limitations & Caveats" in report
    assert "## 7. Conclusion" in report

    # Verify technical details are in collapsed <details> tag
    assert "<details>" in report
    assert "<summary><b>Technical Details & Execution Provenance</b> (Click to expand)</summary>" in report
    assert "</details>" in report

    # Verify no raw dict dump in Executive Summary
    first_section = report.split("## 2. Key Numerical Findings")[0]
    assert "{'rows':" not in first_section
    assert "{'OrderDate':" not in first_section


def test_analytical_validation_rejects_mismatch():
    """12: Analytical validation rejects mismatched questions and results."""
    mismatched_state = {
        "user_query": "Show monthly revenue trends.",
        "dataset_profile": {"column_names": ["sales", "profit"]},  # NO date column
        "tool_calls": [
            {"action": "profile_dataset", "parameters": {}},
            {"action": "calculate_descriptive_statistics", "parameters": {"columns": ["sales"]}},
        ],
        "tool_results": [
            {"action": "profile_dataset", "success": True, "result": {"rows": 100}},
            {"action": "calculate_descriptive_statistics", "success": True, "result": {"sales": {"mean": 100.0}}},
        ],
        "findings": [
            {"type": "descriptive_statistics", "metric": "sales", "mean": 100.0, "message": "Average sales: 100"}
        ],
        "visualizations": [],
        "errors": [],
    }

    validated = validate_analysis(mismatched_state)
    assert validated["status"] == "validation_failed"

    intent_check = next(c for c in validated["validation_results"] if c["check"] == "operation_intent_consistency")
    assert intent_check["passed"] is False

    dim_check = next(c for c in validated["validation_results"] if c["check"] == "dimension_and_metric_presence")
    assert dim_check["passed"] is False
