from pathlib import Path

from app.graph.workflow import create_analysis_graph


def test_analysis_graph_initializes_state(uploaded_sales_dataset, monkeypatch):
    from app.graph import workflow

    monkeypatch.setattr(
        workflow,
        "generate_analysis_plan",
        lambda query, profile: workflow._fallback_plan(query),
    )
    graph = create_analysis_graph()

    result = graph.invoke({
        "session_id": "test-session",
        "user_query": "What is the total revenue?",
        "dataset_id": uploaded_sales_dataset,
        "status": "created",
    })

    assert result["session_id"] == "test-session"
    assert result["current_step"] == 1
    assert result["tool_calls"]
    assert result["tool_results"]
    assert result["status"] == "analyzed"


def test_graph_executes_planner_and_analyst(uploaded_sales_dataset, monkeypatch):
    from app.graph import workflow

    monkeypatch.setattr(
        workflow,
        "generate_analysis_plan",
        lambda query, profile: workflow._fallback_plan(query),
    )
    graph = create_analysis_graph()

    result = graph.invoke({
        "session_id": "test-session",
        "user_query": "What is the total revenue by region?",
        "dataset_id": uploaded_sales_dataset,
        "status": "created",
    })

    assert result["status"] == "analyzed"

    assert len(result["analysis_plan"]) == 3

    assert (
        result["analysis_plan"][0]["action"]
        == "profile_dataset"
    )

    assert (
        result["analysis_plan"][1]["action"]
        == "group_and_aggregate"
    )

    assert (
        result["analysis_plan"][2]["action"]
        == "create_bar_chart"
    )

    assert len(result["tool_results"]) == 3

    assert result["tool_results"][0]["success"] is True
    assert result["tool_results"][1]["success"] is True
    assert result["tool_results"][2]["success"] is True

    assert len(result["visualizations"]) == 1
    assert Path(result["visualizations"][0]).exists()
