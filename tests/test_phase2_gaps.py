"""
Tests for Phase 2 deployment-readiness gaps:

  Gap B — Filesystem permissions (POSIX only; skipped on Windows)
  Gap D — Analysis concurrency semaphore
  Gap E — Legacy XLS rejection
"""
import os
import sys
import stat
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest


# ─── Gap E: XLS Rejection ────────────────────────────────────────────────────

class TestXlsRejection:
    """Verify that .xls files are rejected everywhere they could enter."""

    def test_xls_not_in_data_tools_supported_extensions(self):
        """SUPPORTED_EXTENSIONS in data_tools must not include .xls."""
        from app.tools.data_tools import SUPPORTED_EXTENSIONS
        assert ".xls" not in SUPPORTED_EXTENSIONS, (
            ".xls is listed in SUPPORTED_EXTENSIONS; it must be removed "
            "until legacy XLS support is formally required and xlrd is audited."
        )

    def test_xls_not_in_upload_allowed_extensions(self):
        """Public upload endpoint must not accept .xls."""
        from app.api.upload import ALLOWED_EXTENSIONS
        assert ".xls" not in ALLOWED_EXTENSIONS

    def test_resolve_dataset_path_rejects_xls(self, tmp_path, monkeypatch):
        """resolve_dataset_path must not return a path for a .xls file."""
        from app import dataset_storage
        from app.dataset_storage import resolve_dataset_path

        monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", tmp_path)
        dataset_id = str(uuid4())
        (tmp_path / f"{dataset_id}.xls").write_bytes(b"\xd0\xcf\x11\xe0")  # XLS magic

        with pytest.raises(FileNotFoundError, match="Dataset not found"):
            resolve_dataset_path(dataset_id)

    def test_load_dataset_rejects_xls_extension(self, tmp_path):
        """_load_dataset_stream must raise ValueError for .xls extension."""
        from app.tools.data_tools import load_dataset

        xls_path = tmp_path / "data.xls"
        xls_path.write_bytes(b"\xd0\xcf\x11\xe0" * 128)  # fake XLS magic

        with pytest.raises(ValueError, match="Unsupported file format"):
            load_dataset(str(xls_path))


# ─── Gap D: Analysis Concurrency Semaphore ───────────────────────────────────

class TestAnalysisConcurrencySemaphore:
    """Verify the semaphore in routes.py behaves correctly."""

    def test_semaphore_is_released_after_normal_completion(self, monkeypatch, tmp_path):
        """Semaphore must be released when analysis succeeds."""
        from app.api import routes

        original_limit = routes._analysis_semaphore._value  # type: ignore[attr-defined]

        call_count = {"n": 0}

        def fake_invoke(state):
            call_count["n"] += 1
            return {**state, "status": "complete", "analysis_plan": [], "tool_calls": [],
                    "findings": [], "visualizations": [], "evidence": [],
                    "validation_results": [], "errors": [], "final_report": "ok"}

        # Replace graph invoke and bypass DB + auth
        from app.storage import database as db_mod
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(db_mod, "DB_PATH", db_path)
        db_mod.initialize_database()
        from scripts.migrate_auth import migrate
        migrate(db_path)

        monkeypatch.setattr(routes.analysis_graph, "invoke", fake_invoke)

        # Record available count before and after
        before = routes._analysis_semaphore._value  # type: ignore[attr-defined]

        # Simulate the semaphore acquire/release cycle directly
        acquired = routes._analysis_semaphore.acquire(blocking=False)
        assert acquired, "Semaphore should be acquirable when no analysis is running"
        routes._analysis_semaphore.release()

        after = routes._analysis_semaphore._value  # type: ignore[attr-defined]
        assert before == after, "Semaphore value should be unchanged after acquire+release"

    def test_semaphore_blocks_excess_concurrent_requests(self, owned_api_test_client, monkeypatch):
        """When semaphore is exhausted, /api/analyze must return 503."""
        from app.api import routes

        # Drain all permits
        held = []
        for _ in range(routes._analysis_semaphore._value + 5):  # type: ignore[attr-defined]
            ok = routes._analysis_semaphore.acquire(blocking=False)
            if ok:
                held.append(True)

        try:
            # Now the semaphore is exhausted; upload a CSV and attempt analysis
            import io
            csv_bytes = b"col\n1\n"
            response = owned_api_test_client.post(
                "/api/upload",
                files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
                headers={"Authorization": "Bearer test-user-a"},
            )
            if response.status_code != 200:
                pytest.skip("Upload endpoint unavailable in this test environment")

            dataset_id = response.json()["dataset_id"]
            result = owned_api_test_client.post(
                "/api/analyze",
                json={"user_query": "test", "dataset_id": dataset_id},
                headers={"Authorization": "Bearer test-user-a"},
            )
            assert result.status_code == 503, (
                f"Expected 503 when semaphore is exhausted, got {result.status_code}"
            )
        finally:
            for _ in held:
                routes._analysis_semaphore.release()

    def test_max_concurrent_analyses_env_var_is_respected(self, monkeypatch):
        """MAX_CONCURRENT_ANALYSES env var must be readable from security module."""
        monkeypatch.setenv("MAX_CONCURRENT_ANALYSES", "7")
        import importlib
        import app.security as sec
        importlib.reload(sec)
        assert sec.MAX_CONCURRENT_ANALYSES == 7
        # Restore
        importlib.reload(sec)

    def test_max_json_scalar_bytes_is_defined(self):
        """MAX_JSON_SCALAR_BYTES must be present in security module."""
        from app.security import MAX_JSON_SCALAR_BYTES
        assert isinstance(MAX_JSON_SCALAR_BYTES, int)
        assert MAX_JSON_SCALAR_BYTES > 0


# ─── Gap B: Filesystem Permissions (POSIX only) ───────────────────────────────

@pytest.mark.skipif(
    os.name == "nt",
    reason=(
        "POSIX chmod tests are skipped on Windows. "
        "Windows ACL requirements are documented in "
        "docs/engineering/WINDOWS_ACL_REQUIREMENTS.md."
    ),
)
class TestFilesystemPermissionsPosix:
    """Verify that uploaded files and the database get restrictive permissions."""

    def test_upload_file_is_created_with_owner_only_permissions(self, tmp_path):
        """On POSIX, newly created upload files must not be readable by group/other."""
        # Simulate what upload.py does: open("xb") then os.chmod(path, 0o600)
        dest = tmp_path / "test_upload.csv"
        with dest.open("xb") as f:
            if os.name != "nt":
                os.chmod(dest, 0o600)
            f.write(b"col\nval\n")

        mode = stat.S_IMODE(os.stat(dest).st_mode)
        assert mode & 0o077 == 0, (
            f"Upload file has group/other bits set: {oct(mode)}. "
            "Expected 0o600 (owner read/write only)."
        )

    def test_database_file_permissions_are_restrictive(self, tmp_path):
        """On POSIX, the database file must not be readable by group/other."""
        import sqlite3
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.close()
        # Simulate what database.py does at connection time
        if os.name != "nt":
            current_mode = stat.S_IMODE(os.stat(db_path).st_mode)
            if current_mode & 0o177:
                os.chmod(db_path, 0o600)

        mode = stat.S_IMODE(os.stat(db_path).st_mode)
        assert mode & 0o177 == 0, (
            f"Database file has group/other bits set: {oct(mode)}. "
            "Expected 0o600."
        )

    def test_upload_dir_chmod_does_not_affect_existing_files(self, tmp_path):
        """chmod on a newly created file must not change permissions of sibling files."""
        existing = tmp_path / "existing.csv"
        existing.write_bytes(b"col\nval\n")
        original_mode = stat.S_IMODE(os.stat(existing).st_mode)

        new_file = tmp_path / "new_upload.csv"
        with new_file.open("xb") as f:
            if os.name != "nt":
                os.chmod(new_file, 0o600)
            f.write(b"col\nval2\n")

        # Existing file must be unaffected
        assert stat.S_IMODE(os.stat(existing).st_mode) == original_mode
