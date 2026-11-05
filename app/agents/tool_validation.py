from typing import Any


SUPPORTED_ACTIONS = {
    "profile_dataset",
    "group_and_aggregate",
    "calculate_descriptive_statistics",
    "calculate_correlation",
    "detect_outliers",
    "calculate_percentage_change",
    "create_bar_chart",
    "create_line_chart",
    "create_histogram",
    "create_scatter_plot",
}

REQUIRED_PARAMETERS = {
    "profile_dataset": [],
    "group_and_aggregate": ["group_by", "metric"],
    "calculate_descriptive_statistics": ["columns"],
    "calculate_correlation": ["column_a", "column_b"],
    "detect_outliers": ["column"],
    "calculate_percentage_change": ["old_value", "new_value"],
    "create_bar_chart": ["x_column", "y_column"],
    "create_line_chart": ["x_column", "y_column"],
    "create_histogram": ["column"],
    "create_scatter_plot": ["x_column", "y_column"],
}


def validate_tool_call(action: str, parameters: dict[str, Any]) -> None:
    """Validate an analysis tool call before execution."""

    if action not in SUPPORTED_ACTIONS:
        raise ValueError(
            f"Unsupported analysis action: {action}"
        )

    if not isinstance(parameters, dict):
        raise ValueError(
            f"Tool parameters must be a dictionary for action: {action}"
        )

    required = REQUIRED_PARAMETERS[action]

    missing = [
        parameter
        for parameter in required
        if parameter not in parameters
        or parameters[parameter] in (None, "")
    ]

    if missing:
        raise ValueError(
            f"Missing required parameters for {action}: "
            f"{', '.join(missing)}"
        )
