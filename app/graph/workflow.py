
from app.agents.reporter import generate_report

from app.tools.data_tools import load_dataset_by_id
from langgraph.graph import StateGraph, START, END

from app.agents.analyst import execute_analysis_plan
from app.agents.validator import validate_analysis
from app.agents.llm_planner import generate_analysis_plan
from app.state import AgentState
from app.services.semantic_detection import (
    profile_schema_semantics,
    find_best_date_column,
    match_query_column,
    is_identifier_column,
)


MAX_REPLANS = 2


def _profile_dataset(dataset_id: str) -> dict:
    try:
        df = load_dataset_by_id(dataset_id)
    except ValueError as exc:
        if "Dataset is empty" in str(exc):
            return {"rows": 0, "columns": 0, "column_names": [], "numerical_columns": [], "dtypes": {}, "missing_values": {}, "empty": True}
        raise
    num_cols = df.select_dtypes(include="number").columns.tolist()

    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": df.columns.tolist(),
        "numerical_columns": num_cols,
        "dtypes": {
            column: str(dtype)
            for column, dtype in df.dtypes.items()
        },
        "missing_values": {
            column: int(value)
            for column, value in df.isna().sum().items()
        },
        "duplicate_rows": int(df.duplicated().sum()),
    }


def _find_date_column(available_cols: list[str]) -> str | None:
    return find_best_date_column(available_cols)


def _fallback_plan(query: str, dataset_profile: dict | None = None) -> list:
    query = query.lower()

    plan = [
        {
            "step": 1,
            "action": "profile_dataset",
        }
    ]

    available_cols = []
    dtypes = {}
    if dataset_profile and isinstance(dataset_profile, dict):
        available_cols = dataset_profile.get("column_names", [])
        dtypes = dataset_profile.get("dtypes") or dataset_profile.get("data_types") or {}

    available_cols_lower = [c.lower() for c in available_cols]
    col_map = {c.lower(): c for c in available_cols}

    semantics = profile_schema_semantics(
        column_names=available_cols,
        dtypes=dtypes,
    )
    eligible_numeric = semantics["eligible_numeric_metrics"]
    categorical_dims = semantics["eligible_categorical_dimensions"]

    # Target column / metric determination
    metric = None

    # 1. Did the user mention an eligible numeric column?
    matched_col = match_query_column(query, available_cols, eligible_numeric)
    if matched_col:
        metric = matched_col
    else:
        # Check all available columns
        matched_any = match_query_column(query, available_cols)
        if matched_any and matched_any in eligible_numeric:
            metric = matched_any

    # If still not found, check direct substrings
    if not metric:
        for c in eligible_numeric:
            if c.lower() in query:
                metric = c
                break

    # If still not found, check known domain synonyms / queries
    if not metric and ("revenue" in query or "sales" in query):
        if "revenue" in available_cols_lower:
            metric = col_map["revenue"]
        elif "sales" in available_cols_lower:
            metric = col_map["sales"]

    # When dataset_profile is absent or did not yield a metric, match query tokens
    if not metric:
        for m_cand in ["revenue", "sales", "profit", "quantity", "price", "marks", "temperature", "humidity"]:
            if m_cand in query:
                metric = m_cand
                break

    # If still not found, select first eligible numeric column
    if not metric and eligible_numeric:
        metric = eligible_numeric[0]
    elif not metric and not eligible_numeric:
        metric = None

    # Resolve grouping column if any
    group_by = None
    # 1. Explicit syntax: "by <col>", "per <col>", "across <col>"
    if "by " in query or "per " in query or "across " in query:
        for col in available_cols:
            c_low = col.lower()
            if f"by {c_low}" in query or f"per {c_low}" in query or f"across {c_low}" in query:
                group_by = col
                break

    # 2. Categorical dimensions mentioned in query
    if not group_by:
        for cand in categorical_dims:
            if cand.lower() in query:
                group_by = cand
                break

    # 3. Any available column mentioned in query (excluding target metric and IDs)
    if not group_by:
        for col in available_cols:
            if col != metric and col.lower() in query and not is_identifier_column(col):
                group_by = col
                break

    # 4. Standard semantic grouping keywords if dataset_profile is absent or empty
    if not group_by:
        for cand in [
            "region", "country", "category", "subcategory", "city", "state",
            "paymentmethod", "shippingmode", "customersegment", "location",
            "subject", "product", "item", "department", "grade"
        ]:
            if cand in query:
                group_by = cand
                break

    # Determine operation
    is_trend = any(
        w in query
        for w in [
            "trend", "trends", "monthly", "month", "months", "over time",
            "by month", "per month", "timeline", "seasonality", "progression"
        ]
    )
    is_avg = any(w in query for w in ["average", "mean", "avg"])
    is_median = "median" in query
    is_min = any(w in query for w in ["min", "minimum", "lowest"])
    is_max = any(w in query for w in ["max", "maximum", "highest", "most", "top"])
    is_sum = any(w in query for w in ["total", "sum"])
    is_corr = any(w in query for w in ["correlation", "correlat", "relation", "relate", "associated", "association"])
    is_outlier = any(w in query for w in ["outlier", "outliers", "anomal", "anomalies"])

    if dataset_profile is not None and not eligible_numeric:
        if not (is_avg or is_sum or is_median or is_min or is_max or is_corr or is_outlier):
            cat_dim = group_by or (categorical_dims[0] if categorical_dims else (available_cols[0] if available_cols else None))
            if cat_dim:
                plan.extend([
                    {
                        "step": 2,
                        "action": "group_and_aggregate",
                        "parameters": {
                            "group_by": cat_dim,
                            "metric": cat_dim,
                            "aggregation": "count",
                        },
                    },
                    {
                        "step": 3,
                        "action": "create_bar_chart",
                        "parameters": {
                            "x_column": cat_dim,
                            "y_column": "count",
                        },
                    },
                ])
        return plan

    if is_trend:
        date_col = find_best_date_column(available_cols, dtypes)
        if date_col and metric:
            agg = "mean" if is_avg else "sum"
            plan.extend([
                {
                    "step": 2,
                    "action": "group_and_aggregate",
                    "parameters": {
                        "group_by": "month",
                        "metric": metric,
                        "aggregation": agg,
                    },
                },
                {
                    "step": 3,
                    "action": "create_line_chart",
                    "parameters": {
                        "x_column": "month",
                        "y_column": metric,
                    },
                },
            ])
        else:
            # Date column is missing; do NOT fabricate a fake date
            if metric:
                plan.append({
                    "step": 2,
                    "action": "calculate_descriptive_statistics",
                    "parameters": {"columns": [metric]},
                })
    elif is_corr:
        mentioned_numeric = [
            c for c in eligible_numeric
            if c.lower() in query
        ]
        if len(mentioned_numeric) >= 2:
            col_a, col_b = mentioned_numeric[0], mentioned_numeric[1]
        elif len(eligible_numeric) >= 2:
            col_a = mentioned_numeric[0] if mentioned_numeric else eligible_numeric[0]
            col_b = next((c for c in eligible_numeric if c != col_a), eligible_numeric[1])
        else:
            col_a, col_b = None, None

        if col_a and col_b:
            plan.append({
                "step": 2,
                "action": "calculate_correlation",
                "parameters": {"column_a": col_a, "column_b": col_b},
            })
        elif metric:
            plan.append({
                "step": 2,
                "action": "calculate_descriptive_statistics",
                "parameters": {"columns": [metric]},
            })
    elif is_outlier:
        if metric:
            plan.append({
                "step": 2,
                "action": "detect_outliers",
                "parameters": {"column": metric},
            })
    elif group_by and metric:
        agg = "mean" if is_avg else "median" if is_median else "min" if is_min else "max" if is_max else "sum"
        plan.extend([
            {
                "step": 2,
                "action": "group_and_aggregate",
                "parameters": {
                    "group_by": group_by,
                    "metric": metric,
                    "aggregation": agg,
                },
            },
            {
                "step": 3,
                "action": "create_bar_chart",
                "parameters": {
                    "x_column": group_by,
                    "y_column": metric,
                },
            },
        ])
    elif metric:
        plan.append({
            "step": 2,
            "action": "calculate_descriptive_statistics",
            "parameters": {
                "columns": [metric],
            },
        })

    return plan


def planner(state: AgentState) -> AgentState:
    state["dataset_profile"] = _profile_dataset(
        state["dataset_id"]
    )

    try:
        state["analysis_plan"] = generate_analysis_plan(
            state["user_query"],
            state["dataset_profile"],
        )

    except Exception as exc:
        state.setdefault("errors", []).append({
            "type": "planner",
            "message": str(exc),
        })

        state["analysis_plan"] = _fallback_plan(
            state["user_query"],
            state.get("dataset_profile"),
        )

    state["current_step"] = (
        state.get("current_step", 0) + 1
    )

    state["status"] = "planned"

    return state


def analyst(state: AgentState) -> AgentState:
    return execute_analysis_plan(state)


def observe(state: AgentState) -> AgentState:
    """
    Inspect the latest execution and determine whether
    the workflow needs another planning attempt.
    """

    tool_results = state.get(
        "tool_results",
        [],
    )

    if not tool_results:
        state["status"] = "needs_replan"
        return state

    failed_tools = [
        result
        for result in tool_results
        if result.get("success") is not True
    ]

    if not failed_tools:
        state["status"] = "analysis_complete"
        return state

    state["status"] = "needs_replan"

    return state


def should_replan(state: AgentState) -> str:
    """
    Bounded routing decision.

    The workflow can never replan indefinitely.
    """

    if state.get("status") != "needs_replan":
        return "validate"

    replan_count = state.get(
        "replan_count",
        0,
    )

    if replan_count >= MAX_REPLANS:
        return "validate"

    state["replan_count"] = replan_count + 1

    return "replan"


def replan(state: AgentState) -> AgentState:
    """
    Generate a new plan after an unsuccessful analysis.

    The original user question and latest dataset profile
    remain the planning context.
    """

    try:
        state["analysis_plan"] = generate_analysis_plan(
            state["user_query"],
            state["dataset_profile"],
        )

        state["status"] = "replanned"

    except Exception as exc:
        state.setdefault("errors", []).append({
            "type": "replan",
            "message": str(exc),
        })

        state["analysis_plan"] = _fallback_plan(
            state["user_query"],
            state.get("dataset_profile"),
        )

        state["status"] = "replanned"

    return state


def validator(state: AgentState) -> AgentState:
    return validate_analysis(state)


def finalize(state: AgentState) -> AgentState:
    state = generate_report(state)

    if state.get("status") == "validated":
        state["status"] = "analyzed"

    elif state.get("status") == "validation_failed":
        state["status"] = "failed"

    return state


def create_analysis_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner)
    graph.add_node("analyst", analyst)
    graph.add_node("observe", observe)
    graph.add_node("replan", replan)
    graph.add_node("validator", validator)
    graph.add_node("finalize", finalize)

    graph.add_edge(
        START,
        "planner",
    )

    graph.add_edge(
        "planner",
        "analyst",
    )

    graph.add_edge(
        "analyst",
        "observe",
    )

    graph.add_conditional_edges(
        "observe",
        should_replan,
        {
            "replan": "replan",
            "validate": "validator",
        },
    )

    graph.add_edge(
        "replan",
        "analyst",
    )

    graph.add_edge(
        "validator",
        "finalize",
    )

    graph.add_edge(
        "finalize",
        END,
    )

    return graph.compile()
