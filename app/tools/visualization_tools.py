from pathlib import Path

import matplotlib

# Must be set before importing pyplot.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


DEFAULT_OUTPUT_DIR = Path("reports/charts")


def _prepare_output_path(
    filename: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not filename.endswith(".png"):
        filename = f"{filename}.png"

    return output_path / filename


def _save_figure(fig, path: Path) -> str:
    """Save and close a matplotlib figure safely."""
    try:
        fig.savefig(
            path,
            dpi=100,
            bbox_inches="tight",
        )
    finally:
        plt.close(fig)

    return str(path)


def create_line_chart(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    filename: str = "line_chart.png",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> str:
    """Create a line chart and return its file path."""

    _validate_columns(df, [x_column, y_column])

    path = _prepare_output_path(filename, output_dir)

    fig, ax = plt.subplots(figsize=(9, 5))

    ax.plot(df[x_column], df[y_column], marker="o", linewidth=2, color="#0f766e")

    clean_x = str(x_column).replace("_", " ").title()
    clean_y = str(y_column).replace("_", " ").title()
    ax.set_xlabel(clean_x)
    ax.set_ylabel(clean_y)
    ax.set_title(f"{clean_y} Trend over {clean_x}")
    ax.grid(True, linestyle="--", alpha=0.5)

    if not pd.api.types.is_numeric_dtype(df[x_column]) or len(df) <= 30:
        plt.xticks(rotation=45, ha="right")

    fig.tight_layout()

    return _save_figure(fig, path)


def create_bar_chart(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    filename: str = "bar_chart.png",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> str:
    """Create a bar chart and return its file path."""

    _validate_columns(df, [x_column, y_column])

    path = _prepare_output_path(filename, output_dir)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(df[x_column], df[y_column])

    ax.set_xlabel(x_column)
    ax.set_ylabel(y_column)
    ax.set_title(f"{y_column} by {x_column}")

    fig.tight_layout()

    return _save_figure(fig, path)


def create_histogram(
    df: pd.DataFrame,
    column: str,
    filename: str = "histogram.png",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> str:
    """Create a histogram and return its file path."""

    _validate_columns(df, [column])

    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError(
            f"Column must be numerical: {column}"
        )

    path = _prepare_output_path(filename, output_dir)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.hist(df[column].dropna())

    ax.set_xlabel(column)
    ax.set_ylabel("Frequency")
    ax.set_title(f"Distribution of {column}")

    fig.tight_layout()

    return _save_figure(fig, path)


def create_scatter_plot(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    filename: str = "scatter_plot.png",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> str:
    """Create a scatter plot and return its file path."""

    _validate_columns(df, [x_column, y_column])

    for column in [x_column, y_column]:
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise ValueError(
                f"Column must be numerical: {column}"
            )

    path = _prepare_output_path(filename, output_dir)

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.scatter(df[x_column], df[y_column])

    ax.set_xlabel(x_column)
    ax.set_ylabel(y_column)
    ax.set_title(f"{y_column} vs {x_column}")

    fig.tight_layout()

    return _save_figure(fig, path)


def _validate_columns(
    df: pd.DataFrame,
    columns: list[str],
) -> None:
    """Validate that required columns exist."""

    missing = [
        column
        for column in columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Columns not found: {missing}"
        )