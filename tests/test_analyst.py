from pathlib import Path
from uuid import uuid4

from app.agents.analyst import execute_analysis_plan


def test_analyst_executes_revenue_plan(uploaded_sales_dataset):
    state = {
        "user_query": "What is the total revenue by region?",
        "dataset_id": uploaded_sales_dataset,
        "analysis_plan": [
            {
                "step": 1,
                "action": "profile_dataset",
            },
            {
                "step": 2,
                "action": "group_and_aggregate",
                "parameters": {
                    "group_by": "region",
                    "metric": "revenue",
                    "aggregation": "sum",
                },
            },
        ],
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "errors": [],
        "status": "planned",
    }

    result = execute_analysis_plan(state)

    assert result["status"] == "analyzed"
    assert len(result["tool_calls"]) == 2
    assert len(result["tool_results"]) == 2
    assert result["errors"] == []


def test_analyst_creates_visualization(uploaded_sales_dataset):
    state = {
        "user_query": "Show revenue by region.",
        "dataset_id": uploaded_sales_dataset,
        "analysis_plan": [
            {
                "step": 1,
                "action": "create_bar_chart",
                "parameters": {
                    "x_column": "region",
                    "y_column": "revenue",
                },
            },
        ],
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "errors": [],
        "status": "planned",
    }

    result = execute_analysis_plan(state)

    assert result["status"] == "analyzed"
    assert len(result["visualizations"]) == 1
    assert Path(result["visualizations"][0]).exists()


def test_analyst_handles_missing_dataset():
    state = {
        "user_query": "Analyze the dataset.",
        "dataset_id": str(uuid4()),
        "analysis_plan": [],
        "tool_calls": [],
        "tool_results": [],
        "findings": [],
        "visualizations": [],
        "errors": [],
        "status": "planned",
    }

    result = execute_analysis_plan(state)

    assert result["status"] == "failed"
    assert len(result["errors"]) == 1
    assert result["errors"][0]["type"] == "fatal"
