import csv
import io
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd
import ijson
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries

from app.security import (
    MAX_ANALYSIS_ROWS,
    MAX_DATASET_CELLS,
    MAX_DATASET_COLUMNS,
    MAX_DATASET_SIZE_BYTES,
    MAX_JSON_TOKENS,
    MAX_JSON_NESTING_DEPTH,
    MAX_XLSX_COMPRESSION_RATIO,
    MAX_XLSX_ENTRIES,
    MAX_XLSX_ENTRY_UNCOMPRESSED_BYTES,
    MAX_XLSX_UNCOMPRESSED_BYTES,
    validate_dataset_resource,
)
from app.dataset_storage import open_dataset_by_id, open_dataset_path


SUPPORTED_EXTENSIONS = {
    ".csv",
    ".xlsx",
    # NOTE: .xls (legacy Excel 97-2003) is intentionally absent.
    # The public upload endpoint (app/api/upload.py) only accepts
    # .csv, .xlsx and .json.  Including .xls here creates an internal
    # call path that could process legacy-format files if bypassed.
    # Restore .xls only once xlrd is security-audited and XLS support
    # is formally required.
    ".json",
}


def _preflight_csv(source, max_rows: int | None) -> None:
    """Count row/column/cell dimensions with the CSV parser before pandas."""
    source.seek(0)
    text = io.TextIOWrapper(source, encoding="utf-8-sig", newline="")
    columns = 0
    rows = 0
    seen_header = False
    try:
        csv.field_size_limit(MAX_DATASET_SIZE_BYTES)
        for row in csv.reader(text):
            if not row:
                continue
            if not seen_header:
                columns = len(row)
                seen_header = True
            else:
                rows += 1
                columns = max(columns, len(row))
                if max_rows is not None and rows > max_rows:
                    raise ValueError(f"Dataset exceeds the {max_rows:,}-row analysis limit.")
            if columns > MAX_DATASET_COLUMNS:
                raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
            if rows * columns > MAX_DATASET_CELLS:
                raise ValueError(f"Dataset exceeds the {MAX_DATASET_CELLS:,}-cell limit.")
    except (csv.Error, UnicodeError):
        raise ValueError("Dataset could not be parsed as CSV.") from None
    finally:
        try:
            text.detach()
        except ValueError:
            pass
        source.seek(0)


def _preflight_json(source, max_rows: int | None) -> None:
    """Stream JSON tokens to enforce nesting and row-dimension limits.

    pandas remains the converter so the app retains its existing JSON
    orientation and dtype behavior. This pass rejects over-limit files before
    pandas materializes them.
    """
    stack: list[dict[str, object]] = []
    root_kind: str | None = None
    root_fields = 0
    pending_root_key: str | None = None
    root_array_rows = 0
    root_array_max_columns = 0
    split_data_max_columns = 0
    tokens = 0
    object_dimensions: dict[str, int] = {}

    def enforce_row_limit(row_count: int) -> None:
        if max_rows is not None and row_count > max_rows:
            raise ValueError(f"Dataset exceeds the {max_rows:,}-row analysis limit.")

    source.seek(0)
    parser = iter(ijson.parse(source))
    while True:
        try:
            _, event, value = next(parser)
        except StopIteration:
            break
        except Exception:
            raise ValueError("JSON dataset is malformed or unsupported.") from None
        tokens += 1
        if tokens > MAX_JSON_TOKENS:
            raise ValueError(f"JSON dataset exceeds the {MAX_JSON_TOKENS:,}-token limit.")

        if event in {"start_map", "start_array"}:
            kind = "map" if event == "start_map" else "array"
            if not stack:
                root_kind = kind
            elif len(stack) == 1 and root_kind == "array":
                root_array_rows += 1
                enforce_row_limit(root_array_rows)
            elif len(stack) == 1 and root_kind == "map":
                field = pending_root_key
                if field is not None:
                    stack.append({"kind": kind, "field": field, "count": 0, "members": 0})
                    if len(stack) > MAX_JSON_NESTING_DEPTH:
                        raise ValueError(
                            f"JSON nesting exceeds the {MAX_JSON_NESTING_DEPTH}-level limit."
                        )
                    pending_root_key = None
                    continue
            elif len(stack) == 2 and root_kind == "map" and stack[1]["kind"] == "array":
                stack[1]["count"] = int(stack[1]["count"]) + 1
                if stack[1]["field"] == "columns":
                    if stack[1]["count"] > MAX_DATASET_COLUMNS:
                        raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
                else:
                    enforce_row_limit(int(stack[1]["count"]))

            stack.append({"kind": kind, "field": None, "count": 0, "members": 0})
            if len(stack) > MAX_JSON_NESTING_DEPTH:
                raise ValueError(
                    f"JSON nesting exceeds the {MAX_JSON_NESTING_DEPTH}-level limit."
                )
            continue

        if event == "map_key":
            if len(stack) == 1 and root_kind == "map":
                pending_root_key = str(value)
                root_fields += 1
                if root_fields > MAX_DATASET_COLUMNS:
                    raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
            elif len(stack) == 2 and root_kind == "map" and stack[1]["kind"] == "map":
                field = str(stack[1]["field"])
                object_dimensions[field] = object_dimensions.get(field, 0) + 1
                enforce_row_limit(object_dimensions[field])
            elif len(stack) == 2 and root_kind == "array" and stack[1]["kind"] == "map":
                stack[1]["members"] = int(stack[1]["members"]) + 1
                root_array_max_columns = max(root_array_max_columns, int(stack[1]["members"]))
                if root_array_max_columns > MAX_DATASET_COLUMNS:
                    raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
                    if root_array_rows * root_array_max_columns > MAX_DATASET_CELLS:
                        raise ValueError(f"Dataset exceeds the {MAX_DATASET_CELLS:,}-cell limit.")
            elif len(stack) == 3 and root_kind == "map" and stack[1]["field"] == "data" and stack[2]["kind"] == "array":
                stack[2]["count"] = int(stack[2]["count"]) + 1
                split_data_max_columns = max(split_data_max_columns, int(stack[2]["count"]))
                if split_data_max_columns > MAX_DATASET_COLUMNS:
                    raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
            elif len(stack) == 3 and root_kind == "map" and stack[1]["field"] == "data" and stack[2]["kind"] == "map":
                stack[2]["members"] = int(stack[2]["members"]) + 1
                split_data_max_columns = max(split_data_max_columns, int(stack[2]["members"]))
                if split_data_max_columns > MAX_DATASET_COLUMNS:
                    raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
            continue

        if event in {"end_map", "end_array"}:
            if len(stack) == 2 and root_kind == "map" and stack[0]["kind"] == "map":
                field = str(stack[1]["field"])
                count = int(stack[1]["count"])
                if count:
                    object_dimensions[field] = max(object_dimensions.get(field, 0), count)
            if stack:
                stack.pop()
            continue

        # Scalar array items are rows for top-level arrays and dimensions
        # for arrays directly under a top-level object property.
        if len(stack) == 1 and root_kind == "array":
            root_array_rows += 1
            enforce_row_limit(root_array_rows)
        elif len(stack) == 2 and root_kind == "array" and stack[1]["kind"] == "array":
            stack[1]["count"] = int(stack[1]["count"]) + 1
            root_array_max_columns = max(root_array_max_columns, int(stack[1]["count"]))
            if root_array_max_columns > MAX_DATASET_COLUMNS:
                raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
                if root_array_rows * root_array_max_columns > MAX_DATASET_CELLS:
                    raise ValueError(f"Dataset exceeds the {MAX_DATASET_CELLS:,}-cell limit.")
        elif len(stack) == 2 and root_kind == "map" and stack[1]["kind"] == "array":
            stack[1]["count"] = int(stack[1]["count"]) + 1
            if stack[1]["field"] == "columns":
                if stack[1]["count"] > MAX_DATASET_COLUMNS:
                    raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
            else:
                enforce_row_limit(int(stack[1]["count"]))
            if stack[1]["field"] != "columns" and root_fields * int(stack[1]["count"]) > MAX_DATASET_CELLS:
                raise ValueError(f"Dataset exceeds the {MAX_DATASET_CELLS:,}-cell limit.")
        elif len(stack) == 3 and root_kind == "map" and stack[1]["field"] == "data" and stack[2]["kind"] == "array":
            stack[2]["count"] = int(stack[2]["count"]) + 1
            split_data_max_columns = max(split_data_max_columns, int(stack[2]["count"]))
            if split_data_max_columns > MAX_DATASET_COLUMNS:
                raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")

    if root_kind is None:
        raise ValueError("JSON dataset is empty or malformed.")

    if root_kind == "array":
        row_count = root_array_rows
        column_count = root_array_max_columns or 1
    elif "data" in object_dimensions:
        # pandas' split/table shaped objects use this key for their row array.
        row_count = object_dimensions["data"]
    else:
        # A default-orient object can represent either columns or an index.
        # Bound both dimensions; the structure is ambiguous until EOF.
        row_count = max([root_fields, *object_dimensions.values()], default=0)
    enforce_row_limit(row_count)
    if root_kind != "array":
        if "data" in object_dimensions:
            column_count = max(object_dimensions.get("columns", 0), split_data_max_columns, 1)
        else:
            column_count = max(root_fields, 1)
    if column_count > MAX_DATASET_COLUMNS:
        raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
    if row_count * column_count > MAX_DATASET_CELLS:
        raise ValueError(f"Dataset exceeds the {MAX_DATASET_CELLS:,}-cell limit.")


def _validate_xlsx_archive(source) -> None:
    """Reject expansion-heavy or structurally excessive workbooks pre-parser."""
    source.seek(0, 2)
    file_size = source.tell()
    if file_size < 22:
        raise ValueError("XLSX archive is invalid or exceeds configured limits.")
    source.seek(max(0, file_size - 65_557))
    tail = source.read(65_557)
    end_index = tail.rfind(b"PK\x05\x06")
    if end_index < 0 or end_index + 22 > len(tail):
        raise ValueError("XLSX archive is invalid or exceeds configured limits.")
    try:
        fields = struct.unpack_from("<4s4H2LH", tail, end_index)
        entries, central_size, central_offset, comment_size = fields[4:8]
    except struct.error:
        raise ValueError("XLSX archive is invalid or exceeds configured limits.") from None
    eocd_offset = file_size - len(tail) + end_index
    if (end_index + 22 + comment_size != len(tail)
            or entries == 0xFFFF or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF
            or entries > MAX_XLSX_ENTRIES or central_size > 8 * 1024 * 1024
            or central_offset + central_size > eocd_offset):
        raise ValueError("XLSX archive is invalid or exceeds configured limits.")

    total_uncompressed = 0
    total_cells = 0
    source.seek(0)
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) != entries or len(infos) > MAX_XLSX_ENTRIES:
                raise ValueError("XLSX archive is invalid or exceeds configured limits.")
            for info in infos:
                name = info.filename.replace("\\", "/")
                if (name.startswith("/") or ".." in name.split("/")
                        or info.flag_bits & 0x1
                        or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                        or info.file_size > MAX_XLSX_ENTRY_UNCOMPRESSED_BYTES):
                    raise ValueError("XLSX archive is invalid or exceeds configured limits.")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise ValueError("XLSX archive is invalid or exceeds configured limits.")
                if info.file_size and (info.compress_size == 0
                        or info.file_size / max(info.compress_size, 1) > MAX_XLSX_COMPRESSION_RATIO):
                    raise ValueError("XLSX archive is invalid or exceeds configured limits.")
                if name.startswith("xl/sharedStrings") and info.file_size > 16 * 1024 * 1024:
                    raise ValueError("XLSX archive is invalid or exceeds configured limits.")
                if not re.fullmatch(r"xl/worksheets/[^/]+\.xml", name):
                    continue
                worksheet_rows = 0
                with archive.open(info) as worksheet_xml:
                    for event, element in ElementTree.iterparse(worksheet_xml, events=("start", "end")):
                        tag = element.tag.rsplit("}", 1)[-1]
                        if event == "start" and tag == "row":
                            worksheet_rows += 1
                            if worksheet_rows > MAX_ANALYSIS_ROWS + 1:
                                raise ValueError("XLSX worksheet exceeds configured limits.")
                            row_ref = element.attrib.get("r")
                            if row_ref and int(row_ref) > MAX_ANALYSIS_ROWS + 1:
                                raise ValueError("XLSX worksheet exceeds configured limits.")
                        if event == "start" and tag == "dimension":
                            reference = element.attrib.get("ref")
                            if reference:
                                _, _, max_column, max_row = range_boundaries(reference)
                                max_column = max_column or 1
                                max_row = max_row or 1
                                if (max_column > MAX_DATASET_COLUMNS
                                        or max_row > MAX_ANALYSIS_ROWS + 1
                                        or max_column * max(0, max_row - 1) > MAX_DATASET_CELLS):
                                    raise ValueError("XLSX worksheet exceeds configured limits.")
                        if event == "end" and tag == "c":
                            total_cells += 1
                            if total_cells > MAX_DATASET_CELLS:
                                raise ValueError("XLSX worksheet exceeds configured limits.")
                            coordinate = element.attrib.get("r")
                            if coordinate:
                                row, column = coordinate_to_tuple(coordinate)
                                if row > MAX_ANALYSIS_ROWS + 1 or column > MAX_DATASET_COLUMNS:
                                    raise ValueError("XLSX worksheet exceeds configured limits.")
                            element.clear()
    except ValueError:
        raise
    except Exception:
        raise ValueError("XLSX archive is invalid or exceeds configured limits.") from None
    finally:
        source.seek(0)


def _load_dataset_stream(source, extension: str, max_rows: int | None) -> pd.DataFrame:
    validate_dataset_resource(source)
    row_limit = MAX_ANALYSIS_ROWS if max_rows is None else min(MAX_ANALYSIS_ROWS, max_rows)
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {extension}")

    if extension == ".csv":
        _preflight_csv(source, row_limit)
        source.seek(0)
        try:
            df = pd.read_csv(source, nrows=row_limit + 1)
        except Exception:
            raise ValueError("Dataset could not be parsed as CSV.") from None
    elif extension == ".xlsx":
        if True:  # single format; branch kept for structure
            from openpyxl import load_workbook

            try:
                _validate_xlsx_archive(source)
                source.seek(0)
                workbook = load_workbook(source, read_only=True, data_only=True)
            except Exception:
                raise ValueError("Dataset could not be parsed as XLSX.") from None
            try:
                worksheet = workbook.active
                row_count = 0
                for _ in worksheet.iter_rows(values_only=True):
                    row_count += 1
                    if row_count > row_limit + 1:
                        break
            finally:
                workbook.close()
            if max(0, row_count - 1) > row_limit:
                raise ValueError(f"Dataset exceeds the {row_limit:,}-row analysis limit.")
        try:
            source.seek(0)
            df = pd.read_excel(source)
        except Exception:
            raise ValueError(f"Dataset could not be parsed as {extension[1:].upper()}.") from None
    elif extension == ".json":
        _preflight_json(source, row_limit)
        try:
            source.seek(0)
            df = pd.read_json(source)
        except Exception:
            raise ValueError("JSON dataset is malformed or unsupported.") from None
    else:
        raise ValueError(f"Unsupported file format: {extension}")

    if df.empty or len(df.columns) == 0:
        raise ValueError("Dataset is empty.")
    if len(df) > row_limit:
        raise ValueError(f"Dataset exceeds the {row_limit:,}-row analysis limit.")
    if len(df.columns) > MAX_DATASET_COLUMNS:
        raise ValueError(f"Dataset exceeds the {MAX_DATASET_COLUMNS}-column limit.")
    if len(df) * len(df.columns) > MAX_DATASET_CELLS:
        raise ValueError(f"Dataset exceeds the {MAX_DATASET_CELLS:,}-cell limit.")
    return df


def load_dataset(file_path: str | Path, *, max_rows: int | None = MAX_ANALYSIS_ROWS) -> pd.DataFrame:
    """Load a server-selected path through one checked, stable file descriptor."""
    path = Path(file_path)
    with open_dataset_path(path) as source:
        return _load_dataset_stream(source, path.suffix.lower(), max_rows)


def load_dataset_by_id(dataset_id: str, *, max_rows: int | None = MAX_ANALYSIS_ROWS) -> pd.DataFrame:
    """Resolve and open an opaque uploaded dataset ID as one storage operation."""
    with open_dataset_by_id(dataset_id) as (source, extension):
        return _load_dataset_stream(source, extension, max_rows)


def profile_dataset(df: pd.DataFrame) -> dict:
    """
    Generate a structured profile of the dataset.
    """

    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(df.columns),
        "data_types": {
            column: str(dtype)
            for column, dtype in df.dtypes.items()
        },
        "missing_values": {
            column: int(count)
            for column, count in df.isnull().sum().items()
            if count > 0
        },
        "duplicate_rows": int(df.duplicated().sum()),
        "numerical_columns": list(
            df.select_dtypes(include="number").columns
        ),
        "categorical_columns": list(
    df.select_dtypes(
        include=["object", "string", "category"]
    ).columns
),
    }
