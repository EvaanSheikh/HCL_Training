from typing import Any
from app.services.semantic_detection import is_temporal_column


def validate_analysis(state: dict) -> dict:
    validation_results = []
    errors = state.setdefault("errors", [])

    tool_results = state.get("tool_results", [])
    user_query = state.get("user_query", "").lower()
    tool_calls = state.get("tool_calls", [])
    findings = state.get("findings", [])
    dataset_profile = state.get("dataset_profile") or {}
    available_cols = [c.lower() for c in dataset_profile.get("column_names", [])]

    # 1. tool_execution
    if not tool_results:
        validation_results.append({
            "check": "tool_execution",
            "passed": False,
            "message": "No tool results were produced.",
        })
        errors.append({
            "type": "validation",
            "message": "Analysis produced no tool results.",
        })
        state["status"] = "validation_failed"
        state["validation_results"] = validation_results
        return state

    all_tools_successful = all(
        result.get("success") is True
        for result in tool_results
    )
    validation_results.append({
        "check": "tool_execution",
        "passed": all_tools_successful,
        "message": (
            "All analysis tools executed successfully."
            if all_tools_successful
            else "One or more analysis tools failed."
        ),
    })

    # 2. result_presence
    has_results = any(
        result.get("result") is not None
        for result in tool_results
        if result.get("success") is True
    )
    validation_results.append({
        "check": "result_presence",
        "passed": has_results,
        "message": (
            "Analysis produced results."
            if has_results
            else "Analysis produced no usable results."
        ),
    })

    # 3. visualization_consistency
    visualizations = state.get("visualizations", [])
    visualization_paths_valid = True
    for path in visualizations:
        if not isinstance(path, str):
            visualization_paths_valid = False
            break

    validation_results.append({
        "check": "visualization_consistency",
        "passed": visualization_paths_valid,
        "message": (
            "Visualization references are valid."
            if visualization_paths_valid
            else "Invalid visualization reference detected."
        ),
    })

    # 4. operation_intent_consistency
    is_trend = any(
        w in user_query
        for w in [
            "trend", "trends", "monthly", "month", "over time",
            "by month", "per month", "timeline", "seasonality", "progression"
        ]
    )
    is_corr = any(w in user_query for w in ["correlation", "correlat"])
    is_outlier = any(w in user_query for w in ["outlier", "anomal"])
    has_group_by = (
        "by " in user_query
        or "per " in user_query
        or ("across " in user_query and "across all" not in user_query and "across the" not in user_query)
        or "which " in user_query
        or "compare " in user_query
        or any(
            cand in user_query
            for cand in [
                "region", "country", "category", "subcategory", "location", "subject",
                "city", "state", "paymentmethod", "shippingmode", "customersegment",
                "department", "grade", "product", "status"
            ]
        )
    )

    executed_actions = [tc.get("action") for tc in tool_calls]
    intent_passed = True
    intent_msg = "Requested operation matches executed analysis."

    if is_trend:
        has_time_agg = any(
            tc.get("action") == "group_and_aggregate"
            and (is_temporal_column(tc.get("parameters", {}).get("group_by", "")) or tc.get("parameters", {}).get("group_by") in ("month", "date", "year", "orderdate"))
            for tc in tool_calls
        ) or any(
            tc.get("action") == "create_line_chart"
            for tc in tool_calls
        )
        only_descriptive = all(
            tc.get("action") in ("profile_dataset", "calculate_descriptive_statistics")
            for tc in tool_calls
        )
        if only_descriptive or not has_time_agg:
            intent_passed = False
            intent_msg = "Requested time-series trend analysis was executed as static descriptive statistics without temporal aggregation."
    elif is_corr:
        if "calculate_correlation" not in executed_actions:
            intent_passed = False
            intent_msg = "Requested correlation analysis was not executed."
    elif is_outlier:
        if "detect_outliers" not in executed_actions:
            intent_passed = False
            intent_msg = "Requested outlier detection was not executed."
    elif has_group_by and not is_trend:
        if "group_and_aggregate" not in executed_actions:
            intent_passed = False
            intent_msg = "Requested grouped aggregation was not executed."

    validation_results.append({
        "check": "operation_intent_consistency",
        "passed": intent_passed,
        "message": intent_msg,
    })

    # 5. dimension_and_metric_presence
    dim_passed = True
    dim_msg = "Required dimensions and metrics are present and utilized."
    if is_trend:
        date_candidates = [
            "orderdate", "order_date", "date", "invoicedate", "invoice_date",
            "transactiondate", "transaction_date", "created_at", "timestamp", "time"
        ]
        has_date_col = (
            any(c in available_cols for c in date_candidates)
            or any("date" in c or "time" in c for c in available_cols)
        )
        if not has_date_col:
            dim_passed = False
            dim_msg = "Dataset lacks a valid date or timestamp column required for time-series trend analysis."

    validation_results.append({
        "check": "dimension_and_metric_presence",
        "passed": dim_passed,
        "message": dim_msg,
    })

    # 6. time_series_chronology
    chrono_passed = True
    chrono_msg = "Temporal periods follow valid chronological ordering."
    for res in tool_results:
        if res.get("action") == "group_and_aggregate" and isinstance(res.get("result"), list):
            rows = res["result"]
            if rows:
                first_row = rows[0]
                time_keys = [
                    k for k in first_row
                    if is_temporal_column(k) or k.lower() in ("month", "date", "year") or "date" in k.lower()
                ]
                if time_keys:
                    k = time_keys[0]
                    period_values = [str(r.get(k, "")) for r in rows]
                    if period_values != sorted(period_values):
                        chrono_passed = False
                        chrono_msg = f"Time-series periods in '{k}' are not chronologically sorted."
                        break

    validation_results.append({
        "check": "time_series_chronology",
        "passed": chrono_passed,
        "message": chrono_msg,
    })

    # 7. result_metric_alignment
    alignment_passed = True
    alignment_msg = "Answer labels and returned metrics correctly match analysis."
    for f in findings:
        f_msg = str(f.get("message", "")).lower()
        if "population" in f_msg and "population" not in available_cols:
            alignment_passed = False
            alignment_msg = "Findings contain unrelated 'population' terminology on a non-population dataset."
            break

    validation_results.append({
        "check": "result_metric_alignment",
        "passed": alignment_passed,
        "message": alignment_msg,
    })

    # 8. visualization_field_alignment
    viz_field_passed = True
    viz_field_msg = "Visualizations reference valid result fields."
    for tc in tool_calls:
        if tc.get("action") in ("create_line_chart", "create_bar_chart", "create_scatter_plot"):
            params = tc.get("parameters", {})
            x = params.get("x_column")
            y = params.get("y_column")
            if not x or not y:
                viz_field_passed = False
                viz_field_msg = f"Visualization tool '{tc.get('action')}' is missing x_column or y_column parameters."
                break

    validation_results.append({
        "check": "visualization_field_alignment",
        "passed": viz_field_passed,
        "message": viz_field_msg,
    })

    # Overall validation verdict
    validation_passed = all(r["passed"] for r in validation_results)
    if validation_passed:
        state["status"] = "validated"
    else:
        state["status"] = "validation_failed"
        failed_checks = [r["check"] for r in validation_results if not r["passed"]]
        errors.append({
            "type": "validation",
            "message": f"Analytical validation failed on checks: {', '.join(failed_checks)}.",
        })

    state["validation_results"] = validation_results
    return state
