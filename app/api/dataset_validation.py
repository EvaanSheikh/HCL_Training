from pathlib import Path

from app.tools.data_tools import load_dataset


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".json"}


def validate_dataset(path: str) -> dict:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError("Dataset not found.")

    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            "Unsupported dataset format. "
            "Allowed formats: CSV, XLSX, JSON."
        )

    try:
        df = load_dataset(str(file_path))
    except Exception as exc:
        raise ValueError("Dataset could not be parsed or exceeds resource limits.") from exc

    if df.empty:
        raise ValueError("Dataset is empty.")

    if len(df.columns) == 0:
        raise ValueError("Dataset contains no columns.")

    return {
        "valid": True,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": df.columns.tolist(),
        "missing_values": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "file_size_bytes": file_path.stat().st_size,
    }
