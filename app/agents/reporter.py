from datetime import datetime, timezone
import re
from app.services.semantic_detection import (
    is_monetary_metric,
    detect_currency_symbol,
)


def _format_currency_or_number(
    value,
    metric_name: str = "",
    dataset_metadata: dict | None = None,
) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    _, symbol = detect_currency_symbol(str(metric_name), dataset_metadata)
    if symbol:
        return f"{symbol}{value:,.2f}"
    if is_monetary_metric(str(metric_name)) or isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def generate_report(state: dict) -> dict:
    user_query = state.get("user_query", "").strip()
    dataset_id = state.get("dataset_id", "")
    profile = state.get("dataset_profile") or {}
    evidence = state.get("evidence", [])
    validation = state.get("validation_results", [])
    findings = state.get("findings", [])
    visualizations = state.get("visualizations", [])
    tool_calls = state.get("tool_calls", [])
    errors = state.get("errors", [])
    status = state.get("status", "analyzed")

    rows_count = profile.get("rows")
    cols_count = profile.get("columns")

    # 1. Report Title
    clean_topic = user_query.rstrip(".?").strip()
    clean_topic = re.sub(
        r"^(show|what is|what are|calculate|find|give me|display)\s+",
        "",
        clean_topic,
        flags=re.IGNORECASE,
    )
    title = f"# Autonomous Data Analyst Report: {clean_topic.title() if clean_topic else 'Executive Summary'}"

    # 2. Executive Summary synthesis
    summary_parts = []
    explanation_finding = next((f for f in findings if f.get("type") == "explanation"), None)
    trend_finding = next((f for f in findings if f.get("type") == "time_series_trend"), None)
    group_finding = next((f for f in findings if f.get("type") == "group_aggregate"), None)
    stats_finding = next((f for f in findings if f.get("type") == "descriptive_statistics"), None)
    corr_finding = next((f for f in findings if f.get("type") == "correlation"), None)
    outlier_finding = next((f for f in findings if f.get("type") == "outliers"), None)

    if explanation_finding:
        summary_parts.append(explanation_finding.get("message", "Analysis completed."))
    elif trend_finding:
        m = trend_finding.get("metric", "revenue")
        dim = trend_finding.get("dimension", "month")
        high_period = trend_finding.get("highest", {}).get(dim, "N/A")
        high_val = trend_finding.get("highest", {}).get(m, 0)
        low_period = trend_finding.get("lowest", {}).get(dim, "N/A")
        low_val = trend_finding.get("lowest", {}).get(m, 0)
        growth = trend_finding.get("growth_percentage", 0)

        summary_parts.append(
            f"This analysis examines temporal trends for {m} grouped by calendar month. "
            f"Across {trend_finding.get('periods_count', 0)} periods, overall {m} totaled "
            f"{_format_currency_or_number(trend_finding.get('total'), m)}, "
            f"with monthly values averaging {_format_currency_or_number(trend_finding.get('average_per_period'), m)}. "
            f"Monthly performance demonstrated an overall growth rate of {growth:+.1f}%. "
            f"Performance peaked in {high_period} at {_format_currency_or_number(high_val, m)}, "
            f"with the lowest recorded in {low_period} at {_format_currency_or_number(low_val, m)}."
        )
    elif group_finding:
        high = group_finding.get("highest", {})
        low = group_finding.get("lowest", {})
        m = group_finding.get("metric", "metric")
        dim = group_finding.get("dimension") or ([k for k in high if k != m][0] if high else "category")
        summary_parts.append(
            f"This analysis evaluates {m} grouped by {dim}. The highest {m} was achieved by {high.get(dim)} "
            f"({_format_currency_or_number(high.get(m), m)}), while {low.get(dim)} recorded the lowest "
            f"({_format_currency_or_number(low.get(m), m)})."
        )
    elif stats_finding:
        m = stats_finding.get("metric", "metric")
        count = stats_finding.get("count", rows_count or 0)
        summary_parts.append(
            f"Descriptive statistical evaluation of {m} across {count:,} records reveals an average of "
            f"{_format_currency_or_number(stats_finding.get('mean'), m)} (median: {_format_currency_or_number(stats_finding.get('median'), m)}), "
            f"spanning from a minimum of {_format_currency_or_number(stats_finding.get('min'), m)} to a maximum of "
            f"{_format_currency_or_number(stats_finding.get('max'), m)}, totaling {_format_currency_or_number(stats_finding.get('sum'), m)}."
        )
    elif corr_finding:
        summary_parts.append(
            f"Correlation analysis reveals a Pearson correlation coefficient of {corr_finding.get('value', 0):.4f} between the analyzed variables."
        )
    elif outlier_finding:
        summary_parts.append(
            f"Outlier detection using the Interquartile Range (IQR) method identified {outlier_finding.get('count', 0):,} anomalies in {outlier_finding.get('metric')}."
        )
    elif errors:
        summary_parts.append(
            f"The analytical workflow encountered constraints: {errors[0].get('message', 'Validation incomplete')}."
        )
    else:
        summary_parts.append("Analysis completed. Detailed findings and validation records are provided below.")

    executive_summary = " ".join(summary_parts)

    # Build report sections
    lines = [
        title,
        "",
        f"**Analytical Question:** {user_query}",
        f"**Dataset Overview:** {f'{rows_count:,} records across {cols_count} dimensions and metrics' if rows_count else 'Standard analyzed dataset'}",
        "",
        "## 1. Executive Summary",
        executive_summary,
        "",
        "## 2. Key Numerical Findings",
    ]

    # Tables based on findings
    if trend_finding and trend_finding.get("data_points"):
        m = trend_finding.get("metric", "revenue")
        dim = trend_finding.get("dimension", "month")
        points = trend_finding.get("data_points", [])
        lines.extend([
            f"| {dim.title()} | Total {m.title()} | Share of Total |",
            "| :--- | :--- | :--- |",
        ])
        total_val = trend_finding.get("total") or 1.0
        for pt in points[:24]:
            p_val = pt.get(m, 0)
            share = (p_val / total_val * 100) if total_val else 0
            lines.append(f"| {pt.get(dim)} | {_format_currency_or_number(p_val, m)} | {share:.1f}% |")
        lines.append("")
    elif stats_finding:
        m = stats_finding.get("metric", "metric")
        lines.extend([
            f"| Statistical Metric | Calculated Value | Scope / Description |",
            "| :--- | :--- | :--- |",
            f"| Mean (Average) | {_format_currency_or_number(stats_finding.get('mean'), m)} | Central tendency across all records |",
            f"| Median | {_format_currency_or_number(stats_finding.get('median'), m)} | 50th percentile (robust to outliers) |",
            f"| Minimum | {_format_currency_or_number(stats_finding.get('min'), m)} | Lowest recorded observation |",
            f"| Maximum | {_format_currency_or_number(stats_finding.get('max'), m)} | Highest recorded observation |",
            f"| Standard Deviation | {_format_currency_or_number(stats_finding.get('std'), m)} | Measure of data dispersion |",
            f"| Total Sum | {_format_currency_or_number(stats_finding.get('sum'), m)} | Aggregate cumulative total |",
            f"| Observations Count | {stats_finding.get('count', rows_count or 0):,} | Total validated records analyzed |",
            "",
        ])
    elif group_finding:
        m = group_finding.get("metric", "metric")
        high = group_finding.get("highest", {})
        low = group_finding.get("lowest", {})
        dim = group_finding.get("dimension")
        high_group = (high.get(dim) if dim else None) or next((v for k, v in high.items() if k != m), "N/A")
        low_group = (low.get(dim) if dim else None) or next((v for k, v in low.items() if k != m), "N/A")
        dim_label = dim.title() if dim else "Group / Dimension"
        lines.extend([
            f"| Performance Rank | {dim_label} | Aggregated {m.title()} |",
            "| :--- | :--- | :--- |",
            f"| Highest Value | {high_group} | {_format_currency_or_number(high.get(m), m)} |",
            f"| Lowest Value | {low_group} | {_format_currency_or_number(low.get(m), m)} |",
            "",
        ])
    else:
        lines.extend([
            "No tabular records were produced for this operation.",
            "",
        ])

    # 3. Visualizations
    lines.extend([
        "## 3. Visualizations & Charts",
    ])
    if visualizations:
        for idx, viz in enumerate(visualizations, start=1):
            viz_name = viz.split("/")[-1].split("\\")[-1]
            lines.append(f"- **Figure {idx}:** `{viz_name}` illustrating {'monthly temporal trajectory' if 'line' in viz_name else 'distribution'} over the analyzed dimensions.")
    else:
        lines.append("- *No standalone visualization was required or produced for this analysis.*")
    lines.append("")

    # 4. Important Observations
    lines.extend([
        "## 4. Observations & Business Insights",
    ])
    if trend_finding:
        m = trend_finding.get("metric", "revenue")
        high_period = trend_finding.get("highest", {}).get(trend_finding.get("dimension", "month"))
        high_val = trend_finding.get("highest", {}).get(m, 0)
        low_period = trend_finding.get("lowest", {}).get(trend_finding.get("dimension", "month"))
        low_val = trend_finding.get("lowest", {}).get(m, 0)
        growth = trend_finding.get("growth_percentage", 0)
        ratio = (high_val / low_val) if low_val > 0 else 1.0

        lines.extend([
            f"- **Peak Period Identification:** The strongest performing month was **{high_period}** with {_format_currency_or_number(high_val, m)}.",
            f"- **Low Period Identification:** The lowest performing month was **{low_period}** with {_format_currency_or_number(low_val, m)}.",
            f"- **Performance Ratio:** The peak month generated **{ratio:.1f}x** the {m} of the lowest month.",
            f"- **Trajectory Assessment:** Across the observed timeline, the {m} metric showed a **{growth:+.1f}%** overall change from the initial period to the final period.",
        ])
    elif stats_finding:
        m = stats_finding.get("metric", "metric")
        mean = stats_finding.get("mean", 0)
        median = stats_finding.get("median", 0)
        skew = "right-skewed (mean > median)" if mean > median * 1.05 else ("left-skewed (mean < median)" if mean < median * 0.95 else "approximately symmetric")
        lines.extend([
            f"- **Central Tendency:** The distribution is **{skew}**, with an average of {_format_currency_or_number(mean, m)} compared to a median of {_format_currency_or_number(median, m)}.",
            f"- **Range & Outliers:** Maximum recorded observation reaches {_format_currency_or_number(stats_finding.get('max'), m)}, reflecting dispersion beyond the central body.",
        ])
    else:
        lines.append("- Empirical metrics strictly reflect deterministic aggregations executed over the input records.")
    lines.append("")

    # 5. Methodology & Calculation Assumptions
    executed_actions = [tc.get("action") for tc in tool_calls]
    methodology_bullets = []

    analyzed_metric = (
        (trend_finding and trend_finding.get("metric"))
        or (group_finding and group_finding.get("metric"))
        or (stats_finding and stats_finding.get("metric"))
        or ""
    )
    if analyzed_metric in ("revenue", "profit", "sales"):
        methodology_bullets.append(
            "- **Metric Formulation:** Derived financial metrics, if calculated, followed documented transaction accounting definitions: `Revenue = Quantity * UnitSellingPrice * (1 - DiscountPercentage / 100)` and `Profit = Revenue - TotalCost - ShippingCost`. Item discounts were deducted directly from transaction totals."
        )
    else:
        methodology_bullets.append(
            f"- **Metric Formulation:** Analytical operations were computed directly over source observations for metric `{analyzed_metric or 'target variable'}` without unverified semantic conversions."
        )

    # Currency disclosures
    curr_code, curr_sym = detect_currency_symbol(analyzed_metric, profile)
    if curr_sym:
        methodology_bullets.append(
            f"- **Currency Metadata:** Monetary metrics are explicitly denominated in {curr_code} ({curr_sym})."
        )
    elif is_monetary_metric(analyzed_metric):
        methodology_bullets.append(
            "- **Currency Metadata:** No explicit currency symbol was declared in headers or dataset metadata; monetary metrics are formatted neutrally as numbers without assuming USD."
        )

    # Discount & transaction status disclosures
    disc_meta = profile.get("discount_metadata") or state.get("discount_metadata") or {}
    if disc_meta.get("missing_records_count"):
        methodology_bullets.append(
            f"- **Discount Accounting:** {disc_meta['missing_records_count']} observations had missing discounts. "
            "Gross revenue was preserved across all observations, and net revenue was computed strictly on valid observations without assuming zero discounts."
        )
    if disc_meta.get("ambiguity_warning"):
        methodology_bullets.append(
            f"- **Discount Scale Ambiguity:** {disc_meta['ambiguity_warning']}"
        )

    stat_meta = profile.get("status_metadata") or state.get("status_metadata") or {}
    if stat_meta.get("cancelled_count"):
        methodology_bullets.append(
            f"- **Transaction Status:** {stat_meta['cancelled_count']} cancelled or void transactions were detected and distinguished from completed orders."
        )

    if "group_and_aggregate" in executed_actions or trend_finding or group_finding:
        methodology_bullets.append(
            "- **Aggregation Technique:** Categorical and temporal segments were grouped deterministically and aggregated using vectorized operations (sum, mean, median, min, max) without sampling bias."
        )
    if "calculate_correlation" in executed_actions or corr_finding:
        methodology_bullets.append(
            "- **Correlation Technique:** Pairwise relationship measured using standard Pearson correlation coefficient over all concurrent valid observations."
        )
    if "detect_outliers" in executed_actions or outlier_finding:
        methodology_bullets.append(
            "- **Anomaly Detection:** Outliers identified via the non-parametric Interquartile Range (IQR) method: observations beyond [Q1 - 1.5*IQR, Q3 + 1.5*IQR]."
        )
    methodology_bullets.append(
        "- **Data Integrity:** All computations were performed deterministically via vectorized Python/pandas execution; no synthetic or model-hallucinated figures were generated."
    )

    lines.extend([
        "## 5. Methodology & Calculation Assumptions",
        *methodology_bullets,
        "",
        "## 6. Limitations & Caveats",
        f"- The findings in this report are bounded strictly to the {f'{rows_count:,}' if rows_count else 'records in the'} uploaded dataset and its specific observation window.",
        "- **Data Quality:** Findings depend directly on accurate recording, formatting, and completeness in the source dataset.",
        "- **Unobserved Variables:** External domain phenomena, environmental conditions, or macroeconomic factors not recorded in dataset columns are not modeled.",
        "",
        "## 7. Conclusion",
        f"The analysis provides a verifiable, deterministic breakdown of {user_query}. Stakeholders can rely on the documented metrics and accompanying charts for operational and strategic evaluation.",
        "",
        "---",
        "",
        "<details>",
        "<summary><b>Technical Details & Execution Provenance</b> (Click to expand)</summary>",
        "",
        "### System Identifiers",
        f"- **Session ID:** `{state.get('session_id', 'N/A')}`",
        f"- **Dataset ID:** `{dataset_id}`",
        f"- **Generated At:** `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "### Executed Tool Calls",
    ])

    for idx, tc in enumerate(tool_calls, start=1):
        lines.append(f"{idx}. **{tc.get('action')}** — Parameters: `{tc.get('parameters', {})}`")

    lines.extend([
        "",
        "### Analytical Validation Checks",
    ])
    for check in validation:
        st = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- **{check.get('check')}**: {st} — {check.get('message')}")

    lines.extend([
        "",
        "### Execution Provenance",
        f"- Total Evidence Records: {len(evidence)}",
        f"- Replan Count: {state.get('replan_count', 0)}",
        f"- Execution Status: {status}",
        "",
        "</details>",
    ])

    state["final_report"] = "\n".join(lines)
    return state
