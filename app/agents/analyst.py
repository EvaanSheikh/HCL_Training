
from app.security import validate_analysis_limits
from app.tools.data_tools import load_dataset_by_id

from app.agents.tool_validation import validate_tool_call

import pandas as pd

from app.services.semantic_detection import (
    find_best_date_column,
    is_temporal_column,
)
from app.agents.provenance import record_tool_evidence
from app.tools.statistics_tools import (
    calculate_descriptive_statistics,
    calculate_correlation,
    detect_outliers,
    calculate_percentage_change,
)
from app.tools.visualization_tools import (
    create_bar_chart,
    create_line_chart,
    create_histogram,
    create_scatter_plot,
)
from pathlib import Path

PRIVATE_REPORT_ROOT = Path(__file__).resolve().parents[2] / "reports" / "private"


def _load_dataset(dataset_id: str) -> pd.DataFrame:
    df = load_dataset_by_id(dataset_id)
    original_columns = list(df.columns)
    added_columns: set[str] = set()
    derived_metrics: dict[str, str] = {}

    # ---------------------------------------------------------
    # Optional semantic metric derivation
    # Only derive when required input columns exist and semantics are clear
    # ---------------------------------------------------------
    discount_metadata = {}
    status_metadata = {}

    if df.empty:
        df.attrs["original_columns"] = original_columns
        df.attrs["added_columns"] = set()
        df.attrs["derived_metrics"] = {}
        df.attrs["discount_metadata"] = {}
        df.attrs["status_metadata"] = {}
        return df

    # Order and transaction status tracking
    status_col = next((c for c in df.columns if str(c).lower() in ("status", "order_status", "transaction_status", "orderstatus")), None)
    if status_col:
        status_series = df[status_col].astype(str).str.strip().str.lower()
        cancelled_mask = status_series.isin(["cancelled", "canceled", "void", "voided", "aborted", "failed"])
        returned_mask = status_series.isin(["returned", "refunded"])
        pending_mask = status_series.isin(["pending", "processing", "on hold", "awaiting"])
        completed_mask = status_series.isin(["completed", "delivered", "shipped", "paid", "success", "closed", "complete"])
        if not completed_mask.any():
            completed_mask = ~cancelled_mask

        status_metadata = {
            "status_column": status_col,
            "total_records": len(df),
            "cancelled_count": int(cancelled_mask.sum()),
            "returned_count": int(returned_mask.sum()),
            "pending_count": int(pending_mask.sum()),
            "completed_count": int(completed_mask.sum()),
        }

    if "revenue" not in df.columns:
        q_col = next((c for c in df.columns if str(c).lower() in ("quantity", "qty")), None)
        p_col = next((c for c in df.columns if str(c).lower() in ("unitsellingprice", "unit_selling_price", "unit_price", "selling_price")), None)
        if q_col and p_col:
            gross_sales = df[q_col] * df[p_col]
            df["gross_sales"] = gross_sales
            added_columns.add("gross_sales")
            derived_metrics["gross_sales"] = f"{q_col} * {p_col}"

            d_col = next((c for c in df.columns if str(c).lower() in ("discountpercentage", "discount_percentage", "discount_pct", "discount_rate", "discount")), None)
            if d_col:
                valid_mask = df[d_col].notna()
                missing_count = int(df[d_col].isna().sum())
                valid_count = int(valid_mask.sum())
                discount_metadata = {
                    "discount_column": d_col,
                    "missing_records_count": missing_count,
                    "valid_records_count": valid_count,
                }

                d_name = d_col.lower()
                is_explicit_pct = any(tok in d_name for tok in ("pct", "percent", "%", "percentage"))
                is_explicit_frac = any(tok in d_name for tok in ("rate", "ratio", "fraction"))

                scale = None
                if is_explicit_pct:
                    scale = 100.0
                elif is_explicit_frac:
                    scale = 1.0
                elif valid_count > 0:
                    max_d = float(df.loc[valid_mask, d_col].max())
                    min_d = float(df.loc[valid_mask, d_col].min())
                    if max_d > 1.0:
                        scale = 100.0
                    else:
                        scale = None
                        discount_metadata["ambiguity_warning"] = (
                            f"Column '{d_col}' values range in [{min_d}, {max_d}] without explicit scale metadata. "
                            "Net revenue derivation suspended to prevent mathematical convention errors; reporting gross sales."
                        )

                if scale is not None:
                    net_rev = gross_sales * (1.0 - (df[d_col] / scale))
                    df["net_revenue"] = net_rev
                    added_columns.add("net_revenue")

                    if missing_count == 0:
                        df["revenue"] = net_rev
                        derived_metrics["revenue"] = f"{q_col} * {p_col} * (1 - {d_col} / {scale})"
                    else:
                        df["revenue"] = gross_sales
                        derived_metrics["revenue"] = f"{q_col} * {p_col} (gross; {missing_count} missing discounts preserved)"
                        derived_metrics["net_revenue"] = f"{q_col} * {p_col} * (1 - {d_col} / {scale}) ({valid_count} valid records)"
                else:
                    df["revenue"] = gross_sales
                    derived_metrics["revenue"] = f"{q_col} * {p_col} (gross; discount scale convention ambiguous)"
            else:
                df["revenue"] = gross_sales
                derived_metrics["revenue"] = f"{q_col} * {p_col}"

            added_columns.add("revenue")

    if "profit" not in df.columns:
        q_col = next((c for c in df.columns if str(c).lower() in ("quantity", "qty")), None)
        cost_col = next((c for c in df.columns if str(c).lower() in ("unitcostprice", "unit_cost_price", "unit_cost", "cost_price")), None)
        base_rev = "net_revenue" if ("net_revenue" in df.columns and df["net_revenue"].notna().all()) else "revenue"
        if base_rev in df.columns and q_col and cost_col:
            total_cost = df[q_col] * df[cost_col]
            ship_col = next((c for c in df.columns if str(c).lower() in ("shippingcost", "shipping_cost", "shipping")), None)
            shipping = df[ship_col] if ship_col else 0
            df["profit"] = df[base_rev] - total_cost - shipping
            derived_metrics["profit"] = f"{base_rev} - ({q_col} * {cost_col}) - {ship_col or '0'}"
            added_columns.add("profit")

    # Map sales to revenue only if revenue exists and sales is absent
    if "sales" not in df.columns:
        if "revenue" in df.columns and "revenue" in added_columns:
            df["sales"] = df["revenue"]
            added_columns.add("sales")
        elif "Sales" in df.columns:
            df["sales"] = df["Sales"]
            added_columns.add("sales")

    # ---------------------------------------------------------
    # Universal case-insensitive aliases (non-destructive)
    # ---------------------------------------------------------
    for col in original_columns:
        col_lower = str(col).lower()
        if col_lower not in df.columns:
            df[col_lower] = df[col]
            added_columns.add(col_lower)

    # ---------------------------------------------------------
    # Date and temporal normalization
    # ---------------------------------------------------------
    dtypes_map = {c: str(df[c].dtype) for c in df.columns}
    best_date = find_best_date_column(original_columns, dtypes_map)
    if best_date and "month" not in df.columns:
        try:
            parsed_dates = pd.to_datetime(df[best_date], errors="coerce", format="mixed")
            if parsed_dates.notna().any():
                df["month"] = parsed_dates.dt.strftime("%Y-%m")
                added_columns.add("month")
                if "date" not in df.columns:
                    df["date"] = df[best_date]
                    added_columns.add("date")
        except Exception:
            pass

    df.attrs["original_columns"] = original_columns
    df.attrs["added_columns"] = added_columns
    df.attrs["derived_metrics"] = derived_metrics
    df.attrs["discount_metadata"] = discount_metadata
    df.attrs["status_metadata"] = status_metadata

    return df


def _execute_action(
    df: pd.DataFrame,
    action: str,
    parameters: dict,
    session_id: str | None = None,
    dataset_profile: dict | None = None,
):
    chart_output_dir = PRIVATE_REPORT_ROOT / session_id if session_id else None
    # ---------------------------------------------------------
    # Dataset profiling
    # ---------------------------------------------------------
    if action == "profile_dataset":
        if dataset_profile is not None and isinstance(dataset_profile, dict) and "rows" in dataset_profile:
            return dataset_profile
        source_columns = df.attrs.get("original_columns")
        if not source_columns:
            added = df.attrs.get("added_columns", set())
            source_columns = [col for col in df.columns if col not in added]

        return {
            "rows": int(df.shape[0]),
            "columns": len(source_columns),
            "column_names": source_columns,
            "missing_values": {
                column: int(df[column].isna().sum())
                for column in source_columns
            },
            "duplicate_rows": int(df[source_columns].duplicated().sum()),
        }

    # ---------------------------------------------------------
    # Descriptive statistics
    # ---------------------------------------------------------
    if action == "calculate_descriptive_statistics":
        columns = parameters.get("columns", [])
        if isinstance(columns, str):
            columns = [columns]
        if not columns:
            # Fallback to all numerical columns
            columns = df.select_dtypes(include="number").columns.tolist()
        return calculate_descriptive_statistics(df, columns)

    # ---------------------------------------------------------
    # Correlation
    # ---------------------------------------------------------
    if action == "calculate_correlation":
        column_a = parameters["column_a"]
        column_b = parameters["column_b"]
        return calculate_correlation(df, column_a, column_b)

    # ---------------------------------------------------------
    # Outliers
    # ---------------------------------------------------------
    if action == "detect_outliers":
        column = parameters["column"]
        return detect_outliers(df, column)

    # ---------------------------------------------------------
    # Percentage change
    # ---------------------------------------------------------
    if action == "calculate_percentage_change":
        old_val = parameters["old_value"]
        new_val = parameters["new_value"]
        return calculate_percentage_change(old_val, new_val)

    # ---------------------------------------------------------
    # Group and aggregate
    # ---------------------------------------------------------
    if action == "group_and_aggregate":
        group_by = parameters["group_by"]
        metric = parameters["metric"]
        aggregation = parameters.get(
            "aggregation",
            "sum",
        )

        if group_by not in df.columns:
            raise ValueError(
                f"Column not found: {group_by}"
            )

        if metric not in df.columns:
            raise ValueError(
                f"Metric not found: {metric}"
            )

        result = (
            df.groupby(
                group_by,
                dropna=False,
            )[metric]
            .agg(aggregation)
            .reset_index()
        )

        if str(group_by).lower() in ("month", "date", "year", "orderdate") or "date" in str(group_by).lower():
            result = result.sort_values(by=group_by).reset_index(drop=True)

        return result.to_dict(
            orient="records"
        )

    # ---------------------------------------------------------
    # Bar chart
    # ---------------------------------------------------------
    if action == "create_bar_chart":
        x_column = parameters["x_column"]
        y_column = parameters["y_column"]

        if x_column not in df.columns:
            raise ValueError(
                f"Column not found: {x_column}"
            )

        if y_column not in df.columns:
            raise ValueError(
                f"Column not found: {y_column}"
            )

        chart_df = df

        # Never send hundreds of thousands of categorical
        # observations directly to Matplotlib.
        if (
            len(df) > 5000
            and not pd.api.types.is_numeric_dtype(
                df[x_column]
            )
        ):
            chart_df = (
                df.groupby(
                    x_column,
                    dropna=False,
                )[y_column]
                .sum()
                .reset_index()
            )

        return str(
            create_bar_chart(
                chart_df,
                x_column,
                y_column,
                **({"output_dir": chart_output_dir} if chart_output_dir else {}),
            )
        )

    # ---------------------------------------------------------
    # Line chart
    # ---------------------------------------------------------
    if action == "create_line_chart":
        x_column = parameters["x_column"]
        y_column = parameters["y_column"]

        if x_column not in df.columns:
            raise ValueError(
                f"Column not found: {x_column}"
            )

        if y_column not in df.columns:
            raise ValueError(
                f"Column not found: {y_column}"
            )

        chart_df = df
        if not pd.api.types.is_numeric_dtype(df[x_column]) or df[x_column].duplicated().any():
            chart_df = (
                df.groupby(
                    x_column,
                    dropna=False,
                )[y_column]
                .sum()
                .reset_index()
            )
        chart_df = chart_df.sort_values(by=x_column).reset_index(drop=True)

        return str(
            create_line_chart(
                chart_df,
                x_column,
                y_column,
                **({"output_dir": chart_output_dir} if chart_output_dir else {}),
            )
        )

    # ---------------------------------------------------------
    # Histogram
    # ---------------------------------------------------------
    if action == "create_histogram":
        column = parameters["column"]

        if column not in df.columns:
            raise ValueError(
                f"Column not found: {column}"
            )

        return str(
            create_histogram(
                df,
                column,
                **({"output_dir": chart_output_dir} if chart_output_dir else {}),
            )
        )

    # ---------------------------------------------------------
    # Scatter plot
    # ---------------------------------------------------------
    if action == "create_scatter_plot":
        x_column = parameters["x_column"]
        y_column = parameters["y_column"]

        if x_column not in df.columns:
            raise ValueError(
                f"Column not found: {x_column}"
            )

        if y_column not in df.columns:
            raise ValueError(
                f"Column not found: {y_column}"
            )

        return str(
            create_scatter_plot(
                df,
                x_column,
                y_column,
                **({"output_dir": chart_output_dir} if chart_output_dir else {}),
            )
        )

    raise ValueError(
        f"Unsupported analysis action: {action}"
    )


def _extract_findings(
    action: str,
    result,
) -> list:
    findings = []

    if (
        action == "group_and_aggregate"
        and isinstance(result, list)
    ):
        if not result:
            return findings

        numeric_keys = [
            key
            for key, value in result[0].items()
            if isinstance(value, (int, float))
        ]

        if not numeric_keys:
            return findings

        metric = numeric_keys[0]

        highest = max(
            result,
            key=lambda row: row.get(
                metric,
                float("-inf"),
            ),
        )

        lowest = min(
            result,
            key=lambda row: row.get(
                metric,
                float("inf"),
            ),
        )

        category_keys = [
            key
            for key in result[0]
            if key != metric
        ]

        category = (
            category_keys[0]
            if category_keys
            else "category"
        )

        is_time_dim = (
            is_temporal_column(category)
            or str(category).lower() in ("month", "date", "year", "orderdate")
            or "date" in str(category).lower()
        )
        if is_time_dim:
            total_metric = sum(row.get(metric, 0) for row in result)
            avg_per_period = total_metric / len(result) if result else 0
            first_val = result[0].get(metric, 0)
            last_val = result[-1].get(metric, 0)
            growth_pct = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0

            if len(result) >= 2:
                if growth_pct > 5:
                    trend_dir = "an upward"
                elif growth_pct < -5:
                    trend_dir = "a downward"
                else:
                    trend_dir = "a relatively stable"
            else:
                trend_dir = "a single-period"

            first_period = result[0].get(category)
            last_period = result[-1].get(category)

            msg = (
                f"Monthly {metric} tracked across {len(result)} periods from {first_period} to {last_period}, "
                f"exhibiting {trend_dir} trajectory ({growth_pct:+.1f}% from start to end). "
                f"Peak {metric} occurred in {highest.get(category)} at {highest.get(metric):,.2f}, "
                f"and the lowest was in {lowest.get(category)} at {lowest.get(metric):,.2f}. "
                f"Total {metric}: {total_metric:,.2f} (average {avg_per_period:,.2f} per month)."
            )

            findings.append({
                "type": "time_series_trend",
                "metric": metric,
                "dimension": category,
                "highest": highest,
                "lowest": lowest,
                "data_points": result,
                "total": total_metric,
                "average_per_period": avg_per_period,
                "growth_percentage": growth_pct,
                "periods_count": len(result),
                "message": msg,
            })
        else:
            findings.append({
                "type": "group_aggregate",
                "metric": metric,
                "dimension": category,
                "highest": highest,
                "lowest": lowest,
                "message": (
                    f"Highest {metric}: "
                    f"{highest.get(category)} = "
                    f"{highest.get(metric)}. "
                    f"Lowest {metric}: "
                    f"{lowest.get(category)} = "
                    f"{lowest.get(metric)}."
                ),
            })

    elif (
        action == "calculate_descriptive_statistics"
        and isinstance(result, dict)
    ):
        for col, stats in result.items():
            mean_val = stats.get("mean")
            count_val = stats.get("count", 0)
            median_val = stats.get("median")
            min_val = stats.get("min")
            max_val = stats.get("max")
            sum_val = stats.get("sum")
            if stats.get("all_null") or mean_val is None:
                findings.append({
                    "type": "descriptive_statistics",
                    "metric": col,
                    "stats": stats,
                    "all_null": True,
                    "mean": None,
                    "median": None,
                    "min": None,
                    "max": None,
                    "count": 0,
                    "message": f"Column '{col}' contains no valid numerical values (all {stats.get('missing_count', count_val)} records are null or missing).",
                })
                continue
            findings.append({
                "type": "descriptive_statistics",
                "metric": col,
                "stats": stats,
                "mean": mean_val,
                "median": median_val,
                "sum": sum_val,
                "min": min_val,
                "max": max_val,
                "count": count_val,
                "std": stats.get("std"),
                "value": mean_val,
                "message": (
                    f"Average {col}: {mean_val:,.2f} "
                    f"(median: {median_val:,.2f}, min: {min_val:,.2f}, max: {max_val:,.2f}, "
                    f"total sum: {sum_val:,.2f} across {count_val:,} records)."
                ),
            })

    elif (
        action == "calculate_correlation"
        and isinstance(result, (int, float))
    ):
        findings.append({
            "type": "correlation",
            "value": float(result),
            "message": f"Pearson correlation: {result:.4f}.",
        })

    elif (
        action == "detect_outliers"
        and isinstance(result, dict)
    ):
        col = result.get("column", "column")
        count = result.get("outlier_count", 0)
        findings.append({
            "type": "outliers",
            "metric": col,
            "count": count,
            "message": f"Detected {count:,} outliers in {col} using IQR method.",
        })

    return findings


def execute_analysis_plan(state: dict) -> dict:
    state.setdefault("tool_calls", [])
    state.setdefault("tool_results", [])
    state.setdefault("findings", [])
    state.setdefault("visualizations", [])
    state.setdefault("evidence", [])
    state.setdefault("errors", [])

    try:
        try:
            df = _load_dataset(state["dataset_id"])
        except ValueError as exc:
            if "Dataset is empty" in str(exc):
                state["findings"].append({
                    "type": "explanation",
                    "message": "The dataset is empty (0 records). No statistical calculations or visualizations can be performed.",
                })
                state["status"] = "analyzed"
                return state
            raise

        if df.empty:
            state["findings"].append({
                "type": "explanation",
                "message": "The dataset is empty (0 records). No statistical calculations or visualizations can be performed.",
            })
            state["status"] = "analyzed"
            return state

        plan_actions = [s.get("action") for s in state.get("analysis_plan", [])]
        if plan_actions == ["profile_dataset"]:
            num_cols = df.select_dtypes(include="number").columns
            if len(num_cols) == 0:
                state["findings"].append({
                    "type": "explanation",
                    "message": (
                        f"The requested numerical analysis cannot be performed because this dataset "
                        f"contains no numerical columns. Available categorical dimensions: {', '.join(df.columns)}."
                    ),
                })

        for step in state.get(
            "analysis_plan",
            [],
        ):
            validate_analysis_limits(state)

            action = step["action"]
            parameters = step.get(
                "parameters",
                {},
            )
            validate_tool_call(action, parameters)

            state["tool_calls"].append({
                "action": action,
                "parameters": parameters,
            })

            try:
                result = _execute_action(
                    df,
                    action,
                    parameters,
                    state.get("session_id"),
                    state.get("dataset_profile"),
                )

                state["tool_results"].append({
                    "action": action,
                    "success": True,
                    "result": result,
                })

                # Record provenance for every
                # successfully executed tool.
                record_tool_evidence(
                    state,
                    action,
                    parameters,
                    result,
                )

                # Extract human-readable findings.
                state["findings"].extend(
                    _extract_findings(
                        action,
                        result,
                    )
                )

                if action.startswith("create_"):
                    state["visualizations"].append(
                        result
                    )

            except Exception as exc:
                state["tool_results"].append({
                    "action": action,
                    "success": False,
                    "error": str(exc),
                })

                raise

        state["status"] = "analyzed"
        return state

    except FileNotFoundError as exc:
        state["errors"].append({
            "type": "fatal",
            "message": str(exc),
        })

        state["status"] = "failed"
        return state

    except Exception as exc:
        state["errors"].append({
            "type": "recoverable",
            "message": str(exc),
        })

        state["status"] = "failed"
        return state
