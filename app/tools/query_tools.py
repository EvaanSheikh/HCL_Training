import pandas as pd


def filter_data(
    df: pd.DataFrame,
    column: str,
    operator: str,
    value,
) -> pd.DataFrame:
    """
    Filter a DataFrame using a supported comparison operator.
    """

    if column not in df.columns:
        raise ValueError(f"Column not found: {column}")

    operations = {
        "==": lambda series: series == value,
        "!=": lambda series: series != value,
        ">": lambda series: series > value,
        ">=": lambda series: series >= value,
        "<": lambda series: series < value,
        "<=": lambda series: series <= value,
    }

    if operator not in operations:
        raise ValueError(
            f"Unsupported operator: {operator}"
        )

    mask = operations[operator](df[column])

    return df.loc[mask].copy()


def sort_data(
    df: pd.DataFrame,
    column: str,
    ascending: bool = True,
) -> pd.DataFrame:
    """
    Sort a DataFrame by a specified column.
    """

    if column not in df.columns:
        raise ValueError(f"Column not found: {column}")

    return df.sort_values(
        by=column,
        ascending=ascending,
    ).copy()


def group_and_aggregate(
    df: pd.DataFrame,
    group_by: str,
    metric: str,
    aggregation: str = "sum",
) -> pd.DataFrame:
    """
    Group data by one column and aggregate a numerical metric.
    """

    if group_by not in df.columns:
        raise ValueError(
            f"Group-by column not found: {group_by}"
        )

    if metric not in df.columns:
        raise ValueError(
            f"Metric column not found: {metric}"
        )

    if aggregation != "count" and not pd.api.types.is_numeric_dtype(df[metric]):
        raise ValueError(
            f"Metric must be numerical for '{aggregation}' aggregation: {metric}"
        )

    allowed_aggregations = {
        "sum",
        "mean",
        "median",
        "min",
        "max",
        "count",
    }

    if aggregation not in allowed_aggregations:
        raise ValueError(
            f"Unsupported aggregation: {aggregation}"
        )

    result = (
        df.groupby(group_by)[metric]
        .agg(aggregation)
        .reset_index(name=metric if metric != group_by else "count")
    )

    return result


def aggregate_multiple(
    df: pd.DataFrame,
    group_by: str,
    metrics: list[str],
    aggregation: str = "sum",
) -> pd.DataFrame:
    """
    Group by one column and aggregate multiple numerical metrics.
    """

    if group_by not in df.columns:
        raise ValueError(
            f"Group-by column not found: {group_by}"
        )

    missing = [
        column
        for column in metrics
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Columns not found: {missing}"
        )

    for column in metrics:
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise ValueError(
                f"Metric must be numerical: {column}"
            )

    allowed_aggregations = {
        "sum",
        "mean",
        "median",
        "min",
        "max",
        "count",
    }

    if aggregation not in allowed_aggregations:
        raise ValueError(
            f"Unsupported aggregation: {aggregation}"
        )

    return (
        df.groupby(group_by)[metrics]
        .agg(aggregation)
        .reset_index()
    )