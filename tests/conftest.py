from pathlib import Path
from shutil import copyfile
from uuid import uuid4

import pytest

from app import dataset_storage


@pytest.fixture
def uploaded_sales_dataset(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    dataset_id = str(uuid4())
    source = Path(__file__).resolve().parents[1] / "data" / "sample" / "sales.csv"
    copyfile(source, upload_dir / f"{dataset_id}.csv")
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)
    return dataset_id


@pytest.fixture
def api_test_client(tmp_path, monkeypatch):
    """Run the real FastAPI routes with isolated SQLite and file storage."""
    from fastapi.testclient import TestClient
    from app import dataset_storage
    from app.api import routes, upload
    from app.storage import database
    from scripts.migrate_auth import migrate

    db_path = tmp_path / "api-test.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.initialize_database()
    migrate(db_path)

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(dataset_storage, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(routes, "PRIVATE_REPORT_ROOT", tmp_path / "private-reports")

    # Import only after DB_PATH points at the isolated test database because
    # app.api.main initializes the schema when imported.
    from app.api.main import app

    previous_overrides = app.dependency_overrides.copy()
    previous_body_limit = app.state.max_request_body_size_bytes
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.state.max_request_body_size_bytes = previous_body_limit
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture
def owned_api_test_client(api_test_client):
    """HTTP identity fixture; the app's production JWT dependency is replaced only in this fixture."""
    from fastapi import HTTPException, Request
    from app.auth import Principal, require_principal

    app = api_test_client.app

    def test_identity(request: Request) -> Principal:
        token = request.headers.get("authorization")
        identities = {
            "Bearer test-user-a": Principal("https://test-issuer.example/", "user-a"),
            "Bearer test-user-b": Principal("https://test-issuer.example/", "user-b"),
        }
        principal = identities.get(token or "")
        if principal is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return principal

    app.dependency_overrides[require_principal] = test_identity
    return api_test_client
