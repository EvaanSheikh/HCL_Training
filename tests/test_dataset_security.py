from uuid import UUID, uuid4

import pandas as pd
import pytest


class _MemoryUpload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.content = content

    async def read(self, size: int) -> bytes:
        chunk, self.content = self.content[:size], self.content[size:]
        return chunk

    async def close(self) -> None:
        return None


def _run_immediate(coroutine):
    """Run upload handler with an in-memory async file and no event loop."""
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("Upload handler unexpectedly yielded to an event loop.")

from app import dataset_storage
from app.dataset_storage import resolve_dataset_path


def test_resolves_uploaded_dataset_by_opaque_id(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", tmp_path)
    dataset_id = str(uuid4())
    uploaded_file = tmp_path / f"{dataset_id}.csv"
    uploaded_file.write_text("name,value\nalpha,1\n", encoding="utf-8")

    assert resolve_dataset_path(dataset_id) == uploaded_file.resolve()


def test_dataset_id_loader_holds_the_opened_file_descriptor(tmp_path, monkeypatch):
    from app.dataset_storage import open_dataset_by_id

    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", tmp_path)
    dataset_id = str(uuid4())
    dataset_path = tmp_path / f"{dataset_id}.csv"
    dataset_path.write_bytes(b"value\noriginal\n")
    replacement = tmp_path / "replacement.csv"
    replacement.write_bytes(b"value\nreplacement\n")

    try:
        with open_dataset_by_id(dataset_id) as (opened, extension):
            assert extension == ".csv"
            dataset_path.unlink()
            replacement.rename(dataset_path)
            assert opened.read() == b"value\noriginal\n"
    except OSError as error:
        pytest.skip(f"This filesystem does not permit replacing an open file: {error}")


@pytest.mark.parametrize(
    "dataset_id",
    [
        "../../.env",
        "C:\\Windows\\win.ini",
        "/etc/passwd",
        "not-a-uuid.csv",
        "",
    ],
)
def test_rejects_paths_and_non_uuid_ids(tmp_path, monkeypatch, dataset_id):
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="Dataset not found"):
        resolve_dataset_path(dataset_id)


def test_unknown_uuid_is_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="Dataset not found"):
        resolve_dataset_path(str(uuid4()))


def test_rejects_uuid_with_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", tmp_path)
    dataset_id = str(uuid4())
    (tmp_path / f"{dataset_id}.xls").write_bytes(b"not allowed")

    with pytest.raises(FileNotFoundError, match="Dataset not found"):
        resolve_dataset_path(dataset_id)


def test_rejects_symlink_outside_upload_directory(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    outside_file = tmp_path / "outside.csv"
    outside_file.write_text("secret,value\nprivate,1\n", encoding="utf-8")
    dataset_id = str(uuid4())
    link = upload_dir / f"{dataset_id}.csv"
    try:
        link.symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not permitted on this platform.")

    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)
    with pytest.raises(FileNotFoundError, match="Dataset not found"):
        resolve_dataset_path(dataset_id)


@pytest.mark.parametrize("extension", [".csv", ".xlsx", ".json"])
def test_loads_every_supported_format(tmp_path, extension):
    from app.tools.data_tools import load_dataset

    path = tmp_path / f"dataset{extension}"
    frame = pd.DataFrame({"name": ["alpha", "beta"], "value": [1, 2]})
    if extension == ".csv":
        frame.to_csv(path, index=False)
    elif extension == ".xlsx":
        frame.to_excel(path, index=False)
    else:
        frame.to_json(path, orient="records")

    loaded = load_dataset(str(path))
    assert loaded.to_dict(orient="records") == frame.to_dict(orient="records")


@pytest.mark.parametrize("extension", [".csv", ".xlsx", ".json"])
def test_loader_enforces_analysis_row_limit(tmp_path, extension):
    from app.tools.data_tools import load_dataset

    path = tmp_path / f"dataset{extension}"
    frame = pd.DataFrame({"value": [1, 2, 3]})
    if extension == ".csv":
        frame.to_csv(path, index=False)
    elif extension == ".xlsx":
        frame.to_excel(path, index=False)
    else:
        frame.to_json(path, orient="records")

    with pytest.raises(ValueError, match="row analysis limit"):
        load_dataset(str(path), max_rows=2)


@pytest.mark.parametrize("orientation", ["records", "columns", "values", "index", "split"])
def test_json_orientations_preserve_pandas_default_behavior(tmp_path, orientation):
    from app.tools.data_tools import load_dataset

    frame = pd.DataFrame({"amount": [10, 20], "label": ["a", "b"]})
    path = tmp_path / "dataset.json"
    path.write_text(frame.to_json(orient=orientation), encoding="utf-8")
    expected = pd.read_json(path)

    pd.testing.assert_frame_equal(load_dataset(str(path)), expected)


@pytest.mark.parametrize("orientation", ["records", "columns", "values", "index", "split"])
def test_json_at_row_limit_is_allowed(tmp_path, orientation):
    from app.tools.data_tools import load_dataset

    path = tmp_path / "dataset.json"
    frame = pd.DataFrame({"value": [1, 2], "other": [3, 4]})
    path.write_text(frame.to_json(orient=orientation), encoding="utf-8")

    assert len(load_dataset(str(path), max_rows=2)) == 2


@pytest.mark.parametrize("orientation", ["records", "columns", "values", "index", "split"])
def test_json_one_row_over_limit_is_rejected_during_preflight(tmp_path, orientation):
    from app.tools.data_tools import load_dataset

    frame = pd.DataFrame({"amount": [10, 20, 30], "label": ["a", "b", "c"]})
    path = tmp_path / "dataset.json"
    path.write_text(frame.to_json(orient=orientation), encoding="utf-8")

    with pytest.raises(ValueError, match="row analysis limit"):
        load_dataset(str(path), max_rows=2)


@pytest.mark.parametrize("content", ["", "[]", "{}"])
def test_empty_json_is_rejected(tmp_path, content):
    from app.tools.data_tools import load_dataset

    path = tmp_path / "empty.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError):
        load_dataset(str(path))


def test_malformed_json_is_rejected_safely(tmp_path):
    from app.tools.data_tools import load_dataset

    path = tmp_path / "bad.json"
    path.write_text('{"value":[1,', encoding="utf-8")

    with pytest.raises(ValueError, match="malformed or unsupported") as error:
        load_dataset(str(path))
    assert str(tmp_path) not in str(error.value)


def test_json_nesting_limit_is_enforced_before_pandas_parse(tmp_path, monkeypatch):
    from app.tools import data_tools
    from app.security import MAX_JSON_NESTING_DEPTH

    path = tmp_path / "nested.json"
    path.write_text("[" * (MAX_JSON_NESTING_DEPTH + 1) + "0" + "]" * (MAX_JSON_NESTING_DEPTH + 1), encoding="utf-8")
    monkeypatch.setattr(data_tools.pd, "read_json", lambda *_args, **_kwargs: pytest.fail("pandas parser must not run"))

    with pytest.raises(ValueError, match="nesting"):
        data_tools.load_dataset(str(path))


def test_json_row_limit_stops_streaming_preflight_early(tmp_path, monkeypatch):
    from app.tools import data_tools

    path = tmp_path / "many.json"
    path.write_text("[" + ",".join('{"value":1}' for _ in range(100)) + "]", encoding="utf-8")
    original_parse = data_tools.ijson.parse

    def guarded_parse(source):
        for index, event in enumerate(original_parse(source)):
            if index > 8:
                pytest.fail("JSON preflight continued after exceeding the row limit")
            yield event

    monkeypatch.setattr(data_tools.ijson, "parse", guarded_parse)
    with pytest.raises(ValueError, match="row analysis limit"):
        data_tools.load_dataset(str(path), max_rows=1)


def test_json_file_size_limit_is_checked_before_parsing(tmp_path, monkeypatch):
    from app import security
    from app.tools import data_tools

    path = tmp_path / "large.json"
    path.write_text('[{"value":"long"}]', encoding="utf-8")
    monkeypatch.setattr(security, "MAX_DATASET_SIZE_BYTES", 4)
    monkeypatch.setattr(data_tools.pd, "read_json", lambda *_args, **_kwargs: pytest.fail("pandas parser must not run"))

    with pytest.raises(ValueError, match="MB limit"):
        data_tools.load_dataset(str(path))


def test_json_column_limit_is_enforced_during_preflight(tmp_path, monkeypatch):
    from app.tools import data_tools

    path = tmp_path / "wide.json"
    fields = ",".join(f'"column-{index}":0' for index in range(data_tools.MAX_DATASET_COLUMNS + 1))
    path.write_text("[{" + fields + "}]", encoding="utf-8")
    monkeypatch.setattr(data_tools.pd, "read_json", lambda *_args, **_kwargs: pytest.fail("pandas must not parse a too-wide JSON row"))
    with pytest.raises(ValueError, match="column limit"):
        data_tools.load_dataset(str(path))


def test_json_token_limit_is_enforced_during_preflight(tmp_path, monkeypatch):
    from app.tools import data_tools

    path = tmp_path / "tokens.json"
    path.write_text('[{"a":1},{"a":2}]', encoding="utf-8")
    monkeypatch.setattr(data_tools, "MAX_JSON_TOKENS", 4)
    monkeypatch.setattr(data_tools.pd, "read_json", lambda *_args, **_kwargs: pytest.fail("pandas must not parse after the token cap"))
    with pytest.raises(ValueError, match="token limit"):
        data_tools.load_dataset(str(path))


def test_json_cell_budget_allows_exact_boundary_and_rejects_one_over(tmp_path, monkeypatch):
    from app.tools import data_tools

    monkeypatch.setattr(data_tools, "MAX_DATASET_CELLS", 4)
    path = tmp_path / "cells.json"
    path.write_text('[{"a":1,"b":2},{"a":3,"b":4}]', encoding="utf-8")
    assert len(data_tools.load_dataset(str(path))) == 2
    path.write_text('[{"a":1,"b":2,"c":3},{"a":4,"b":5,"c":6}]', encoding="utf-8")
    with pytest.raises(ValueError, match="cell limit"):
        data_tools.load_dataset(str(path))


def test_csv_column_limit_is_enforced_before_pandas(tmp_path, monkeypatch):
    from app.tools import data_tools

    path = tmp_path / "wide.csv"
    path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    monkeypatch.setattr(data_tools, "MAX_DATASET_COLUMNS", 2)
    monkeypatch.setattr(data_tools.pd, "read_csv", lambda *_args, **_kwargs: pytest.fail("pandas must not parse a too-wide CSV"))
    with pytest.raises(ValueError, match="column limit"):
        data_tools.load_dataset(str(path))


def _write_synthetic_xlsx(path, worksheet_xml=b"<worksheet><sheetData/></worksheet>", extra_entries=()):
    import zipfile

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
        for name, content in extra_entries:
            archive.writestr(name, content)


def test_xlsx_rejects_excessive_worksheet_dimensions_before_pandas(tmp_path, monkeypatch):
    from app.tools import data_tools

    path = tmp_path / "dimensions.xlsx"
    _write_synthetic_xlsx(path, b'<worksheet><dimension ref="A1:XFD1048576"/><sheetData/></worksheet>')
    monkeypatch.setattr(data_tools.pd, "read_excel", lambda *_args, **_kwargs: pytest.fail("pandas must not parse excessive dimensions"))
    with pytest.raises(ValueError, match="could not be parsed as XLSX"):
        data_tools.load_dataset(str(path))


def test_xlsx_rejects_compression_ratio_and_entry_count(tmp_path, monkeypatch):
    from app.tools import data_tools

    path = tmp_path / "archive.xlsx"
    _write_synthetic_xlsx(path, extra_entries=(("xl/sharedStrings.xml", b"a" * 20_000),))
    monkeypatch.setattr(data_tools, "MAX_XLSX_COMPRESSION_RATIO", 2)
    with path.open("rb") as source, pytest.raises(ValueError, match="invalid or exceeds configured limits"):
        data_tools._validate_xlsx_archive(source)

    monkeypatch.setattr(data_tools, "MAX_XLSX_COMPRESSION_RATIO", 100)
    path = tmp_path / "entry-count.xlsx"
    _write_synthetic_xlsx(path, extra_entries=(("xl/one.xml", b"small"),))
    monkeypatch.setattr(data_tools, "MAX_XLSX_ENTRIES", 2)
    with path.open("rb") as source, pytest.raises(ValueError, match="invalid or exceeds configured limits"):
        data_tools._validate_xlsx_archive(source)


def test_xlsx_rejects_total_uncompressed_size_boundary(tmp_path, monkeypatch):
    from app.tools import data_tools

    path = tmp_path / "expanded.xlsx"
    _write_synthetic_xlsx(path, extra_entries=(("xl/custom.xml", b"0123456789"),))
    monkeypatch.setattr(data_tools, "MAX_XLSX_UNCOMPRESSED_BYTES", 8)
    with path.open("rb") as source, pytest.raises(ValueError, match="invalid or exceeds configured limits"):
        data_tools._validate_xlsx_archive(source)


def test_table_oriented_json_not_supported_by_existing_default_is_rejected(tmp_path):
    from app.tools.data_tools import load_dataset

    frame = pd.DataFrame({"value": [1, 2]})
    path = tmp_path / "table.json"
    path.write_text(frame.to_json(orient="table"), encoding="utf-8")

    with pytest.raises(ValueError, match="malformed or unsupported"):
        load_dataset(str(path))


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("data.csv", b"name,value\nalpha,1\nbeta,2\n"),
        ("data.json", b'[{"name":"alpha","value":1},{"name":"beta","value":2}]'),
    ],
)
def test_upload_identifier_flows_through_analysis(tmp_path, monkeypatch, filename, content):
    from app import dataset_storage
    from app.api import routes, upload
    from app.graph import workflow

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(upload, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(routes, "save_analysis_session_owned", lambda state, owner_id: None)
    monkeypatch.setattr(routes, "get_user_id", lambda principal: "test-owner")
    monkeypatch.setattr(routes, "owns_dataset", lambda dataset_id, owner_id: True)
    monkeypatch.setattr(routes, "get_owned_report_assets", lambda session_id, owner_id: [])
    monkeypatch.setattr(upload, "get_user_id", lambda principal: "test-owner")
    monkeypatch.setattr(upload, "register_dataset", lambda dataset_id, owner_id, extension: None)
    monkeypatch.setattr(
        workflow,
        "generate_analysis_plan",
        lambda query, profile: [{"step": 1, "action": "profile_dataset"}],
    )

    file = _MemoryUpload(filename, content)
    from app.auth import Principal
    principal = Principal("https://issuer.example/", "subject")
    uploaded = _run_immediate(upload._save_uploaded_file(file, principal))
    dataset_id = uploaded["dataset_id"]
    assert dataset_id == str(UUID(dataset_id))
    assert str(uploads) not in dataset_id
    assert workflow._profile_dataset(dataset_id)["rows"] == 2

    analyzed = routes.analyze(routes.AnalyzeRequest(
        user_query="Profile this dataset",
        dataset_id=dataset_id,
    ), principal)
    assert analyzed.dataset_id == dataset_id
    assert analyzed.status == "analyzed"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("bad.csv", b'"unterminated'),
        ("bad.json", b'{"value":['),
        ("empty.json", b"[]"),
    ],
)
def test_upload_rejects_malformed_dataset_without_leaking_path(
    tmp_path, monkeypatch, filename, content
):
    from fastapi import HTTPException

    from app.api import upload

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(upload, "UPLOAD_DIR", uploads)
    with pytest.raises(HTTPException) as error:
        _run_immediate(upload._save_uploaded_file(_MemoryUpload(filename, content), None))

    assert error.value.status_code == 400
    assert str(tmp_path) not in error.value.detail
    assert list(uploads.iterdir()) == []


def test_upload_enforces_maximum_size_and_removes_partial_file(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from app.api import upload

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(upload, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(upload, "MAX_FILE_SIZE", 3)
    with pytest.raises(HTTPException) as error:
        _run_immediate(upload._save_uploaded_file(_MemoryUpload("large.csv", b"a,b\n1,2\n"), None))

    assert error.value.status_code == 413
    assert list(uploads.iterdir()) == []
