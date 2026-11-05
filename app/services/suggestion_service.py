import os
import json
import logging
from typing import Any

from app.services.semantic_detection import (
    profile_schema_semantics,
    find_best_date_column,
    is_temporal_column,
)

logger = logging.getLogger(__name__)


def generate_suggested_questions(
    dataset_id: str,
    dataset_profile: dict[str, Any],
    max_suggestions: int = 4,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Generate relevant, valid analytical questions derived directly from the active dataset's schema.
    Uses deterministic schema templates as a fast, robust baseline, with optional LLM enhancement
    when configured and reachable.
    """
    column_names = dataset_profile.get("column_names", [])
    dtypes = dataset_profile.get("dtypes") or dataset_profile.get("data_types") or {}
    numerical_columns = dataset_profile.get("numerical_columns") or [
        col for col, dt in dtypes.items()
        if any(t in str(dt).lower() for t in ["int", "float", "double", "number", "numeric"])
    ]

    semantics = profile_schema_semantics(
        column_names=column_names,
        dtypes=dtypes,
        numeric_columns=numerical_columns,
    )

    temporal_cols = semantics["temporal_columns"]
    numeric_metrics = semantics["eligible_numeric_metrics"]
    categorical_dims = semantics["eligible_categorical_dimensions"]

    # If numeric_metrics is empty, check if any column has numeric dtypes even if initially classed as ID
    if not numeric_metrics and numerical_columns:
        numeric_metrics = [c for c in numerical_columns if c in column_names]

    # If categorical_dims is empty, check non-numeric, non-temporal columns
    if not categorical_dims:
        categorical_dims = [
            c for c in column_names
            if c not in numeric_metrics and c not in temporal_cols
        ]

    # Generate deterministic suggestions based on schema capabilities
    deterministic_candidates = _generate_deterministic_candidates(
        temporal_cols=temporal_cols,
        numeric_metrics=numeric_metrics,
        categorical_dims=categorical_dims,
    )

    # Optional LLM-driven suggestions
    llm_candidates = []
    from app.agents.llm_planner import _is_placeholder_key
    has_live_llm = (
        not _is_placeholder_key(os.getenv("OPENROUTER_API_KEY"))
        or not _is_placeholder_key(os.getenv("GEMINI_API_KEY"))
        or not _is_placeholder_key(os.getenv("GOOGLE_API_KEY"))
    )
    if has_live_llm:
        try:
            llm_candidates = _generate_llm_candidates(dataset_profile, column_names)
        except Exception as exc:
            logger.warning("LLM question suggestion failed: %s", exc)

    # Validate candidates
    combined = llm_candidates + deterministic_candidates
    valid_candidates = []
    seen_questions = set()

    for item in combined:
        q_text = item["question"].strip()
        if q_text.lower() in seen_questions:
            continue
        target_cols = item.get("target_columns", [])
        if target_cols and not all(c in column_names for c in target_cols):
            continue

        seen_questions.add(q_text.lower())
        valid_candidates.append(item)

    total = len(valid_candidates)
    if total == 0:
        if column_names:
            first_col = column_names[0]
            valid_candidates.append({
                "question": f"Show summary statistics for {first_col}.",
                "category": "descriptive_statistics",
                "target_columns": [first_col],
            })
        else:
            valid_candidates.append({
                "question": "What is the structure of this dataset?",
                "category": "profile",
                "target_columns": [],
            })
        total = len(valid_candidates)

    # Rotate candidates deterministically using offset
    if total <= max_suggestions:
        selected = valid_candidates
    else:
        start_idx = offset % total
        rotated = valid_candidates[start_idx:] + valid_candidates[:start_idx]
        selected = rotated[:max_suggestions]

    final_suggestions = [
        {
            "id": str(i + 1),
            "question": item["question"].strip(),
            "category": item.get("category", "general"),
            "target_columns": item.get("target_columns", []),
        }
        for i, item in enumerate(selected)
    ]

    return {
        "dataset_id": dataset_id,
        "offset": offset,
        "total_candidates": total,
        "suggestions": final_suggestions,
    }


def _generate_deterministic_candidates(
    temporal_cols: list[str],
    numeric_metrics: list[str],
    categorical_dims: list[str],
) -> list[dict[str, Any]]:
    candidates = []

    # 1. Group comparison: Categorical dimension + Numeric metric
    if categorical_dims and numeric_metrics:
        for dim in categorical_dims[:3]:
            for metric in numeric_metrics[:3]:
                candidates.append({
                    "question": f"Which {dim} has the highest {metric}?",
                    "category": "group_comparison",
                    "target_columns": [dim, metric],
                })
                candidates.append({
                    "question": f"Compare average {metric} by {dim}.",
                    "category": "group_comparison",
                    "target_columns": [dim, metric],
                })

    # 2. Time-series trend: Temporal column + Numeric metric
    if temporal_cols and numeric_metrics:
        for date_col in temporal_cols[:2]:
            for metric in numeric_metrics[:3]:
                candidates.append({
                    "question": f"Show monthly {metric} trends.",
                    "category": "time_series",
                    "target_columns": [date_col, metric],
                })
                candidates.append({
                    "question": f"What is the average {metric} over time?",
                    "category": "time_series",
                    "target_columns": [date_col, metric],
                })

    # 3. Correlation: Multiple numeric metric pairs
    if len(numeric_metrics) >= 2:
        for i in range(min(len(numeric_metrics), 4)):
            for j in range(i + 1, min(len(numeric_metrics), 4)):
                col_a = numeric_metrics[i]
                col_b = numeric_metrics[j]
                candidates.append({
                    "question": f"What is the correlation between {col_a} and {col_b}?",
                    "category": "correlation",
                    "target_columns": [col_a, col_b],
                })

    # 4. Outlier detection across numeric metrics
    if numeric_metrics:
        for metric in numeric_metrics[:3]:
            candidates.append({
                "question": f"Detect outliers in {metric}.",
                "category": "outlier_detection",
                "target_columns": [metric],
            })

    # 5. Descriptive statistics across numeric metrics
    if numeric_metrics:
        for metric in numeric_metrics[:3]:
            candidates.append({
                "question": f"Calculate descriptive statistics for {metric}.",
                "category": "descriptive_statistics",
                "target_columns": [metric],
            })

    # 6. Categorical summaries (especially useful when dataset has no numeric columns)
    if categorical_dims:
        for dim in categorical_dims[:3]:
            candidates.append({
                "question": f"What is the frequency distribution of {dim}?",
                "category": "group_comparison",
                "target_columns": [dim],
            })
            candidates.append({
                "question": f"Which {dim} appears most frequently?",
                "category": "group_comparison",
                "target_columns": [dim],
            })

    return candidates


def _generate_llm_candidates(dataset_profile: dict[str, Any], column_names: list[str]) -> list[dict[str, Any]]:
    """Query configured LLM to produce candidate questions grounded in the schema."""
    from app.agents.llm_planner import _call_openrouter, _call_gemini, _clean_json_response

    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
    summary_profile = {
        "rows": dataset_profile.get("rows"),
        "columns": dataset_profile.get("columns"),
        "column_names": column_names,
        "dtypes": dataset_profile.get("dtypes") or dataset_profile.get("data_types") or {},
    }

    prompt = (
        "You are an expert data analyst. Based strictly on the following dataset schema, suggest 4 distinct, "
        "concise natural-language questions a user might ask. Only refer to columns that explicitly exist in the schema. "
        "Cover diverse categories: group comparison, temporal trends (only if a date/time column exists), "
        "correlation (only if >=2 numeric columns exist), and descriptive statistics.\n\n"
        f"Dataset Schema:\n{json.dumps(summary_profile, indent=2)}\n\n"
        "Return ONLY a JSON array of objects with keys 'question' and 'target_columns'. Example:\n"
        '[{"question": "Which subject has the highest average marks?", "target_columns": ["subject", "marks"]}]'
    )

    content = None
    if provider == "openrouter":
        content = _call_openrouter(prompt, summary_profile)
    else:
        content = _call_gemini(prompt, summary_profile)

    if not content:
        return []

    cleaned = _clean_json_response(content)
    parsed = json.loads(cleaned)
    if isinstance(parsed, dict) and "questions" in parsed:
        parsed = parsed["questions"]
    if not isinstance(parsed, list):
        return []

    validated = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        q = item.get("question", "")
        cols = item.get("target_columns", [])
        if q and isinstance(cols, list) and all(c in column_names for c in cols):
            validated.append({
                "question": q,
                "category": "llm_suggested",
                "target_columns": cols,
            })
    return validated
