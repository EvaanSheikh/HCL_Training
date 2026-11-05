from __future__ import annotations

import pandas as pd


def calculate_descriptive_statistics(
    df: pd.DataFrame,
    columns: list[str],
) -> dict:
    """Calculate descriptive statistics for selected numerical columns."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    if df.empty:
        raise ValueError("The dataset is empty.")

    if not columns:
        raise ValueError("At least one column is required.")

    missing_columns = [
        column for column in columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Column(s) not found: {missing_columns}"
        )

    results = {}

    for column in columns:
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise TypeError(
                f"Column '{column}' must be numerical."
            )

        series = df[column].dropna()

        if series.empty:
            results[column] = {
                "count": 0,
                "mean": None,
                "median": None,
                "min": None,
                "max": None,
                "std": None,
                "sum": 0.0,
                "valid_count": 0,
                "missing_count": int(df[column].isna().sum()),
                "all_null": True,
            }
            continue

        results[column] = {
            "count": int(series.count()),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "min": float(series.min()),
            "max": float(series.max()),
            "std": float(series.std()),
            "sum": float(series.sum()),
        }

    return results


def calculate_percentage_change(
    old_value: float,
    new_value: float,
) -> float:
    """Calculate percentage change between two values."""

    if not isinstance(old_value, (int, float)):
        raise TypeError("old_value must be numerical.")

    if not isinstance(new_value, (int, float)):
        raise TypeError("new_value must be numerical.")

    if old_value == 0:
        raise ValueError(
            "Percentage change cannot be calculated from zero."
        )

    return ((new_value - old_value) / old_value) * 100


def calculate_correlation(
    df: pd.DataFrame,
    column_a: str,
    column_b: str,
) -> float:
    """Calculate Pearson correlation between two numerical columns."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    if df.empty:
        raise ValueError("The dataset is empty.")

    missing_columns = [
        column
        for column in [column_a, column_b]
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Column(s) not found: {missing_columns}"
        )

    if not pd.api.types.is_numeric_dtype(df[column_a]):
        raise TypeError(
            f"Column '{column_a}' must be numerical."
        )

    if not pd.api.types.is_numeric_dtype(df[column_b]):
        raise TypeError(
            f"Column '{column_b}' must be numerical."
        )

    valid_data = df[[column_a, column_b]].dropna()

    if len(valid_data) < 2:
        raise ValueError(
            "At least two valid observations are required."
        )

    correlation = valid_data[column_a].corr(
        valid_data[column_b]
    )

    if pd.isna(correlation):
        raise ValueError(
            "Correlation could not be calculated."
        )

    return float(correlation)


def detect_outliers(
    df: pd.DataFrame,
    column: str,
) -> dict:
    """
    Detect outliers using the IQR method.

    Outlier boundaries:
        Lower = Q1 - 1.5 * IQR
        Upper = Q3 + 1.5 * IQR
    """

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    if df.empty:
        raise ValueError("The dataset is empty.")

    if column not in df.columns:
        raise ValueError(
            f"Column '{column}' not found."
        )

    if not pd.api.types.is_numeric_dtype(df[column]):
        raise TypeError(
            f"Column '{column}' must be numerical."
        )

    series = df[column].dropna()

    if series.empty:
        raise ValueError(
            f"Column '{column}' contains no valid values."
        )

    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1

    lower_bound = q1 - (1.5 * iqr)
    upper_bound = q3 + (1.5 * iqr)

    outlier_mask = (
        (series < lower_bound)
        | (series > upper_bound)
    )

    outliers = series[outlier_mask]

    return {
        "column": column,
        "method": "IQR",
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(iqr),
        "lower_bound": float(lower_bound),
        "upper_bound": float(upper_bound),
        "outlier_count": int(outliers.count()),
        "outlier_values": outliers.tolist(),
    }