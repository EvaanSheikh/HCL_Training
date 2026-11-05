import json
import os
import time

import requests


SYSTEM_PROMPT = """
You are the planning component of an Autonomous Data Analyst.

Your job is to convert a user's analytical question into a deterministic
analysis plan.

Rules:
1. Do not calculate numerical results yourself.
2. Do not invent dataset columns.
3. Use only supported actions.
4. Return valid JSON only.
5. Use profile_dataset as the first step.
6. Use group_and_aggregate for grouped numerical analysis.
7. Use visualization actions when useful.
8. Do not include explanations outside the JSON.

Supported actions:
- profile_dataset
- group_and_aggregate
- calculate_descriptive_statistics
- calculate_percentage_change
- calculate_correlation
- detect_outliers
- create_bar_chart
- create_line_chart
- create_histogram
- create_scatter_plot

Time-series and Trend analysis:
- For questions asking for trends, changes over time, or monthly/daily analysis:
  Use group_and_aggregate with group_by="month" and the requested metric, followed by create_line_chart with x_column="month" and y_column=metric.

Domain and derived metrics:
- Strictly use columns that exist in the provided dataset profile.
- If the dataset contains sales transaction columns (Quantity, UnitSellingPrice, DiscountPercentage), revenue and profit derived metrics can be analyzed.
- For all other domains (e.g. weather, education, real estate, demography, science), identify and use the actual numerical metrics and categorical dimensions from the dataset profile.

Return JSON only:

{
  "analysis_plan": [
    {
      "step": 1,
      "action": "profile_dataset"
    }
  ]
}
"""


SUPPORTED_ACTIONS = {
    "profile_dataset",
    "group_and_aggregate",
    "calculate_descriptive_statistics",
    "calculate_percentage_change",
    "calculate_correlation",
    "detect_outliers",
    "create_bar_chart",
    "create_line_chart",
    "create_histogram",
    "create_scatter_plot",
}


COLUMN_ALIASES = {
    "Region": "region",
    "Country": "country",
    "Category": "category",
    "ProductName": "product",
    "OrderDate": "month",
    "order_date": "month",
    "date": "month",
    "month": "month",
}


def _build_prompt(
    user_query: str,
    dataset_profile: dict,
) -> str:
    return f"""
{SYSTEM_PROMPT}

Dataset profile:
{json.dumps(dataset_profile, indent=2, default=str)}

User question:
{user_query}
"""


def _clean_json_response(content: str) -> str:
    content = content.strip()

    if content.startswith("```"):
        content = content.replace("```json", "")
        content = content.replace("```JSON", "")
        content = content.replace("```", "")
        content = content.strip()

    return content


def _validate_plan_structure(plan: object) -> None:
    if not isinstance(plan, list):
        raise ValueError(
            "LLM response does not contain a valid analysis_plan."
        )

    for step in plan:
        if not isinstance(step, dict):
            raise ValueError(
                "Each analysis plan step must be an object."
            )

        action = step.get("action")

        if not action:
            raise ValueError(
                "Analysis plan step is missing an action."
            )

        if action not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"Unsupported analysis action: {action}"
            )


def _is_placeholder_key(key: str | None) -> bool:
    if not key or not key.strip():
        return True
    k = key.strip().lower()
    return k.startswith("replace_") or "your_" in k or "example" in k or k == "placeholder"


def _call_openrouter(
    user_query: str,
    dataset_profile: dict,
) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")

    if _is_placeholder_key(api_key):
        raise RuntimeError(
            "OPENROUTER_API_KEY is not configured."
        )

    model_name = os.getenv(
        "OPENROUTER_MODEL",
        "openrouter/free",
    )

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"Dataset profile:\n"
                    f"{json.dumps(dataset_profile, indent=2, default=str)}\n\n"
                    f"User question:\n"
                    f"{user_query}"
                ),
            },
        ],
        "temperature": 0,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=15,
    )

    if response.status_code == 429:
        raise RuntimeError(
            "OpenRouter API quota/rate limit exceeded."
        )

    if response.status_code >= 500:
        raise RuntimeError(
            f"OpenRouter server error: {response.status_code}"
        )

    if response.status_code >= 400:
        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text

        raise RuntimeError(
            f"OpenRouter API error {response.status_code}: "
            f"{error_data}"
        )

    data = response.json()

    choices = data.get("choices")

    if not choices:
        raise RuntimeError(
            "OpenRouter returned no choices."
        )

    message = choices[0].get("message", {})
    content = message.get("content")

    if not content:
        raise RuntimeError(
            "OpenRouter returned empty content."
        )

    return content


def _call_gemini(
    user_query: str,
    dataset_profile: dict,
) -> str:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError, ServerError

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or _is_placeholder_key(api_key):
        api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key or _is_placeholder_key(api_key):
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY is not configured."
        )

    client = genai.Client(api_key=api_key)

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    )

    prompt = _build_prompt(
        user_query,
        dataset_profile,
    )

    max_retries = 2

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                ),
            )

            if not response or not response.text:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return response.text

        except ClientError as exc:
            if getattr(exc, "code", None) == 429:
                raise RuntimeError(
                    "Gemini API quota exceeded."
                ) from exc

            raise

        except ServerError as exc:
            if (
                getattr(exc, "code", None) == 503
                and attempt < max_retries - 1
            ):
                sleep_time = 2 ** attempt

                print(
                    f"Gemini temporarily unavailable. "
                    f"Retrying in {sleep_time} seconds..."
                )

                time.sleep(sleep_time)
            else:
                raise

    raise RuntimeError(
        "Gemini did not return a response."
    )


def create_llm_planner():
    """
    Return the configured provider.

    OpenRouter is the primary provider.
    """

    provider = os.getenv(
        "LLM_PROVIDER",
        "openrouter",
    ).lower()

    if provider not in {
        "openrouter",
        "gemini",
    }:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: {provider}"
        )

    return provider


def generate_analysis_plan(
    user_query: str,
    dataset_profile: dict,
) -> list:
    """
    Generate and normalize an analysis plan.

    Provider order:
        1. OpenRouter
        2. Gemini
        3. Caller-level deterministic fallback

    The caller should handle the final exception and use its
    deterministic fallback plan.
    """

    provider = create_llm_planner()

    content = None
    errors = []

    if provider == "openrouter":
        try:
            content = _call_openrouter(
                user_query,
                dataset_profile,
            )

        except Exception as exc:
            errors.append(
                f"OpenRouter: {exc}"
            )

            # Gemini is optional. Only try it when configured.
            if not _is_placeholder_key(os.getenv("GEMINI_API_KEY")) or not _is_placeholder_key(os.getenv("GOOGLE_API_KEY")):
                try:
                    content = _call_gemini(
                        user_query,
                        dataset_profile,
                    )

                except Exception as gemini_exc:
                    errors.append(
                        f"Gemini: {gemini_exc}"
                    )

    else:
        try:
            content = _call_gemini(
                user_query,
                dataset_profile,
            )

        except Exception as exc:
            errors.append(
                f"Gemini: {exc}"
            )

    if content is None:
        raise RuntimeError(
            "All configured LLM providers failed. "
            + " | ".join(errors)
        )

    content = _clean_json_response(content)

    try:
        result = json.loads(content)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "LLM returned invalid JSON."
        ) from exc

    plan = result.get("analysis_plan")

    _validate_plan_structure(plan)

    return normalize_analysis_plan(plan)


def normalize_analysis_plan(plan: list) -> list:
    normalized = []

    for step in plan:
        action = step.get("action")

        if not action:
            raise ValueError(
                "Analysis plan step is missing an action."
            )

        if action not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"Unsupported analysis action: {action}"
            )

        # Parameters may be nested or directly on the step.
        parameters = dict(
            step.get("parameters", {})
        )

        if not parameters:
            parameters = {
                key: value
                for key, value in step.items()
                if key not in {
                    "step",
                    "action",
                    "reason",
                }
            }

        # --------------------------------------------------
        # GROUP + AGGREGATE
        # --------------------------------------------------

        if action == "group_and_aggregate":

            group_columns = parameters.get(
                "group_by_columns",
                [],
            )

            if not group_columns:
                single_group = parameters.get(
                    "group_by"
                )

                if single_group:
                    group_columns = [single_group]

            aggregations = parameters.get(
                "aggregations",
                [],
            )

            if not aggregations:
                single_aggregation = parameters.get(
                    "aggregation"
                )

                if isinstance(
                    single_aggregation,
                    dict,
                ):
                    aggregations = [
                        single_aggregation
                    ]

            if not group_columns:
                raise ValueError(
                    "group_and_aggregate requires "
                    "a grouping column."
                )

            if not aggregations:
                raise ValueError(
                    "group_and_aggregate requires "
                    "an aggregation."
                )

            group_by = group_columns[0]
            aggregation = aggregations[0]

            if not isinstance(aggregation, dict):
                raise ValueError(
                    "Aggregation must be an object."
                )

            metric = (
                aggregation.get("metric")
                or aggregation.get("column")
            )

            aggregation_type = (
                aggregation.get("aggregation_type")
                or aggregation.get("operation")
                or aggregation.get("function")
                or aggregation.get("aggregation")
                or "sum"
            )

            if not metric:
                raise ValueError(
                    "Aggregation requires a metric."
                )

            group_by = COLUMN_ALIASES.get(
                group_by,
                group_by,
            )

            metric = COLUMN_ALIASES.get(
                metric,
                metric,
            )

            parameters = {
                "group_by": group_by,
                "metric": metric,
                "aggregation": aggregation_type,
            }

        # --------------------------------------------------
        # DESCRIPTIVE STATISTICS
        # --------------------------------------------------

        elif action == "calculate_descriptive_statistics":

            columns = (
                parameters.get("columns")
                or parameters.get("column")
                or parameters.get("metric")
                or []
            )

            if isinstance(columns, str):
                columns = [columns]

            parameters = {
                "columns": [
                    COLUMN_ALIASES.get(
                        column,
                        column,
                    )
                    for column in columns
                ]
            }

        # --------------------------------------------------
        # CORRELATION
        # --------------------------------------------------

        elif action == "calculate_correlation":

            column_a = (
                parameters.get("column_a")
                or parameters.get("x_column")
                or parameters.get("column1")
            )

            column_b = (
                parameters.get("column_b")
                or parameters.get("y_column")
                or parameters.get("column2")
            )

            parameters = {
                "column_a": COLUMN_ALIASES.get(
                    column_a,
                    column_a,
                ),
                "column_b": COLUMN_ALIASES.get(
                    column_b,
                    column_b,
                ),
            }

        # --------------------------------------------------
        # PERCENTAGE CHANGE
        # --------------------------------------------------

        elif action == "calculate_percentage_change":

            old_value = parameters.get(
                "old_value"
            )

            new_value = parameters.get(
                "new_value"
            )

            parameters = {
                "old_value": old_value,
                "new_value": new_value,
            }

        # --------------------------------------------------
        # OUTLIERS
        # --------------------------------------------------

        elif action == "detect_outliers":

            column = parameters.get(
                "column"
            )

            parameters = {
                "column": COLUMN_ALIASES.get(
                    column,
                    column,
                )
            }

        # --------------------------------------------------
        # BAR CHART
        # --------------------------------------------------

        elif action == "create_bar_chart":

            x_column = (
                parameters.get("x_column")
                or parameters.get("x_axis")
            )

            y_column = (
                parameters.get("y_column")
                or parameters.get("y_axis")
            )

            x_column = COLUMN_ALIASES.get(
                x_column,
                x_column,
            )

            y_column = COLUMN_ALIASES.get(
                y_column,
                y_column,
            )

            if y_column in {
                "TotalRevenue",
                "total_revenue",
                "sum_revenue",
            }:
                y_column = "revenue"

            parameters = {
                "x_column": x_column,
                "y_column": y_column,
            }

            if "title" in step:
                parameters["title"] = step["title"]

            if "x_axis_label" in step:
                parameters["x_axis_label"] = (
                    step["x_axis_label"]
                )

            if "y_axis_label" in step:
                parameters["y_axis_label"] = (
                    step["y_axis_label"]
                )

        # --------------------------------------------------
        # LINE CHART
        # --------------------------------------------------

        elif action == "create_line_chart":

            x_column = (
                parameters.get("x_column")
                or parameters.get("x_axis")
            )

            y_column = (
                parameters.get("y_column")
                or parameters.get("y_axis")
            )

            parameters = {
                "x_column": COLUMN_ALIASES.get(
                    x_column,
                    x_column,
                ),
                "y_column": COLUMN_ALIASES.get(
                    y_column,
                    y_column,
                ),
            }

        # --------------------------------------------------
        # HISTOGRAM
        # --------------------------------------------------

        elif action == "create_histogram":

            column = parameters.get(
                "column"
            )

            parameters = {
                "column": COLUMN_ALIASES.get(
                    column,
                    column,
                )
            }

        # --------------------------------------------------
        # SCATTER PLOT
        # --------------------------------------------------

        elif action == "create_scatter_plot":

            x_column = (
                parameters.get("x_column")
                or parameters.get("x_axis")
            )

            y_column = (
                parameters.get("y_column")
                or parameters.get("y_axis")
            )

            parameters = {
                "x_column": COLUMN_ALIASES.get(
                    x_column,
                    x_column,
                ),
                "y_column": COLUMN_ALIASES.get(
                    y_column,
                    y_column,
                ),
            }

        normalized.append({
            "step": len(normalized) + 1,
            "action": action,
            "parameters": parameters,
        })

    # ------------------------------------------------------
    # ENFORCE DATASET PROFILING
    # ------------------------------------------------------

    if (
        not normalized
        or normalized[0]["action"] != "profile_dataset"
    ):
        normalized.insert(
            0,
            {
                "step": 1,
                "action": "profile_dataset",
                "parameters": {},
            },
        )

    # Re-number steps.
    for index, step in enumerate(
        normalized,
        start=1,
    ):
        step["step"] = index

    return normalized
