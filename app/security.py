import os
from pathlib import Path


MAX_DATASET_SIZE_BYTES = 100 * 1024 * 1024
MAX_REQUEST_BODY_SIZE_BYTES = 102 * 1024 * 1024
MAX_MULTIPART_FIELD_SIZE_BYTES = 64 * 1024
MAX_ANALYSIS_ROWS = 1_000_000
MAX_DATASET_COLUMNS = 512
MAX_DATASET_CELLS: int = int(os.getenv("MAX_DATASET_CELLS", "20_000_000"))
MAX_JSON_NESTING_DEPTH = 64
MAX_JSON_TOKENS = 8_000_000
MAX_XLSX_ENTRIES = 2_048
MAX_XLSX_ENTRY_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 100
MAX_REPLANS = 2
# Maximum number of concurrent analysis invocations.  Each call
# loads a full DataFrame into memory; keep this small on single
# instances.  Override with the MAX_CONCURRENT_ANALYSES env var.
import os as _os
MAX_CONCURRENT_ANALYSES: int = int(_os.getenv("MAX_CONCURRENT_ANALYSES", "4"))
del _os
# Maximum byte length of a single scalar value inside a JSON
# dataset (e.g. one string cell).  Values larger than this are
# rejected before pandas materialises them.
MAX_JSON_SCALAR_BYTES: int = 1 * 1024 * 1024  # 1 MiB
MAX_TOOL_CALLS = 20


def validate_dataset_resource(resource) -> None:
    """Validate size from the already-open descriptor when available."""
    if hasattr(resource, "fileno"):
        try:
            size = os.fstat(resource.fileno()).st_size
        except OSError:
            raise FileNotFoundError("Dataset not found.") from None
    else:
        file_path = Path(resource)
        if not file_path.exists():
            raise FileNotFoundError("Dataset not found.")
        size = file_path.stat().st_size

    if size > MAX_DATASET_SIZE_BYTES:
        raise ValueError(
            f"Dataset exceeds the {MAX_DATASET_SIZE_BYTES // (1024 * 1024)} MB limit."
        )


def validate_analysis_limits(state: dict) -> None:
    tool_calls = len(state.get("tool_calls", []))

    if tool_calls >= MAX_TOOL_CALLS:
        raise RuntimeError(
            f"Maximum tool-call limit of {MAX_TOOL_CALLS} exceeded."
        )

    replan_count = state.get("replan_count", 0)

    if replan_count > MAX_REPLANS:
        raise RuntimeError(
            f"Maximum replan limit of {MAX_REPLANS} exceeded."
        )
