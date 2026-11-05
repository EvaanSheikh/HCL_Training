from types import SimpleNamespace
from uuid import uuid4

from app.api import routes


def test_health(api_test_client):
    response = api_test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_session_requires_authentication(api_test_client):
    response = api_test_client.get("/api/analysis/non-existent-session")
    assert response.status_code == 401


def test_invalid_analyze_request_is_validated_after_authentication(owned_api_test_client):
    response = owned_api_test_client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer test-user-a"},
        json={"user_query": "", "dataset_id": "invalid.csv"},
    )
    assert response.status_code == 422


def test_unknown_dataset_id_returns_generic_not_found(owned_api_test_client):
    response = owned_api_test_client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer test-user-a"},
        json={"user_query": "Profile this dataset", "dataset_id": str(uuid4())},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found."


def test_asgi_body_limit_rejects_before_route_parsing(api_test_client):
    api_test_client.app.state.max_request_body_size_bytes = 64
    declared = api_test_client.post(
        "/api/analyze",
        content=b"x" * 65,
        headers={"Content-Type": "application/json"},
    )
    assert declared.status_code == 413
    assert "configured limit" in declared.json()["detail"]


def test_asgi_body_limit_counts_streamed_bytes_without_content_length(api_test_client):
    api_test_client.app.state.max_request_body_size_bytes = 64
    streamed = api_test_client.post(
        "/api/analyze",
        content=iter([b"x" * 40, b"y" * 40]),
        headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
    )
    assert streamed.status_code == 413, streamed.text
    assert "configured limit" in streamed.json()["detail"]


def test_oversized_multipart_file_is_rejected_before_spooling_or_persistence(owned_api_test_client, monkeypatch):
    from app.api import upload
    from app.storage import database

    monkeypatch.setattr(upload, "MAX_FILE_SIZE", 4)
    response = owned_api_test_client.post(
        "/api/upload",
        headers={"Authorization": "Bearer test-user-a"},
        files={"file": ("too-large.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "File exceeds the 100 MB size limit."}
    assert list(upload.UPLOAD_DIR.iterdir()) == []
    with database.get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0


def test_upload_rejects_multiple_multipart_files(owned_api_test_client, monkeypatch):
    from app.api import upload

    response = owned_api_test_client.post(
        "/api/upload",
        headers={"Authorization": "Bearer test-user-a"},
        files=[
            ("file", ("one.csv", b"a,b\n1,2\n", "text/csv")),
            ("file", ("two.csv", b"a,b\n3,4\n", "text/csv")),
        ],
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid multipart upload."}
    assert list(upload.UPLOAD_DIR.iterdir()) == []


def test_upload_analysis_and_session_authorization_over_http(owned_api_test_client, monkeypatch):
    from app.api import routes as route_module

    monkeypatch.setattr(
        route_module,
        "analysis_graph",
        SimpleNamespace(invoke=lambda state: {
            **state,
            "status": "analyzed",
            "analysis_plan": [],
            "tool_calls": [],
            "tool_results": [],
            "findings": [],
            "visualizations": [],
            "evidence": [],
            "validation_results": [],
            "errors": [],
            "final_report": "test report",
        }),
    )
    auth_a = {"Authorization": "Bearer test-user-a"}
    auth_b = {"Authorization": "Bearer test-user-b"}

    uploaded = owned_api_test_client.post(
        "/api/upload",
        headers=auth_a,
        files={"file": ("sales.csv", b"name,value\nalpha,1\nbeta,2\n", "text/csv")},
    )
    assert uploaded.status_code == 200
    dataset_id = uploaded.json()["dataset_id"]

    analysis = owned_api_test_client.post(
        "/api/analyze", headers=auth_a,
        json={"user_query": "Profile this dataset", "dataset_id": dataset_id},
    )
    assert analysis.status_code == 200
    session_id = analysis.json()["session_id"]
    assert owned_api_test_client.get(f"/api/analysis/{session_id}", headers=auth_a).status_code == 200

    cross_dataset = owned_api_test_client.post(
        "/api/analyze", headers=auth_b,
        json={"user_query": "Profile this dataset", "dataset_id": dataset_id},
    )
    cross_session = owned_api_test_client.get(f"/api/analysis/{session_id}", headers=auth_b)
    assert cross_dataset.status_code == 404
    assert cross_session.status_code == 404
    assert cross_session.json() == owned_api_test_client.get(
        "/api/analysis/00000000-0000-4000-8000-000000000000", headers=auth_b
    ).json()

    # There is no dataset overwrite/update or standalone dataset retrieval API.
    assert owned_api_test_client.post(f"/api/datasets/{dataset_id}", headers=auth_a).status_code == 404
    assert owned_api_test_client.get(f"/api/datasets/{dataset_id}", headers=auth_a).status_code == 404
    assert owned_api_test_client.post(f"/api/analysis/{session_id}", headers=auth_a).status_code == 405

    second_upload = owned_api_test_client.post(
        "/api/upload", headers=auth_b,
        files={"file": ("sales.csv", b"name,value\nother,99\n", "text/csv")},
    )
    assert second_upload.status_code == 200
    assert second_upload.json()["dataset_id"] != dataset_id
    assert owned_api_test_client.post(
        "/api/analyze", headers=auth_a,
        json={"user_query": "Profile this dataset", "dataset_id": dataset_id},
    ).status_code == 200


def test_chart_owner_legacy_and_no_public_static_route(owned_api_test_client, tmp_path, monkeypatch):
    from app.api import routes as route_module
    from app.auth import Principal, get_user_id
    from app.storage import database

    owner_id = database.get_or_create_user("https://test-issuer.example/", "user-a")
    other_id = database.get_or_create_user("https://test-issuer.example/", "user-b")
    dataset_id = "dataset-chart"
    database.register_dataset(dataset_id, owner_id, ".csv")
    with database.get_connection() as connection:
        connection.execute(
            "INSERT INTO analysis_sessions(session_id,user_query,dataset_id,status,created_at,updated_at,owner_user_id,owned_dataset_id) VALUES(?,?,?,?,?,?,?,?)",
            ("session-chart", "q", dataset_id, "done", "now", "now", owner_id, dataset_id),
        )
        connection.execute(
            "INSERT INTO analysis_sessions(session_id,user_query,dataset_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("legacy-chart-session", "q", "old-dataset", "done", "now", "now"),
        )
        connection.execute(
            "INSERT INTO report_assets(asset_id,session_id,relative_path,media_type) VALUES(?,?,?,?)",
            ("asset-chart", "session-chart", "session-chart/chart.png", "image/png"),
        )
        connection.execute(
            "INSERT INTO report_assets(asset_id,session_id,relative_path,media_type) VALUES(?,?,?,?)",
            ("legacy-asset", "legacy-chart-session", "legacy/chart.png", "image/png"),
        )

    private_root = tmp_path / "private-reports"
    monkeypatch.setattr(route_module, "PRIVATE_REPORT_ROOT", private_root)
    chart_file = private_root / "session-chart" / "chart.png"
    chart_file.parent.mkdir(parents=True)
    chart_file.write_bytes(b"png-test-content")
    monkeypatch.setattr(
        route_module, "get_user_id",
        lambda principal: owner_id if principal.subject == "user-a" else other_id,
    )
    # Exercise the HTTP route; production auth stays replaced only by the test identity fixture.
    owner_response = owned_api_test_client.get(
        "/api/analysis/session-chart/charts/asset-chart",
        headers={"Authorization": "Bearer test-user-a"},
    )
    foreign_response = owned_api_test_client.get(
        "/api/analysis/session-chart/charts/asset-chart",
        headers={"Authorization": "Bearer test-user-b"},
    )
    legacy_response = owned_api_test_client.get(
        "/api/analysis/legacy-chart-session/charts/legacy-asset",
        headers={"Authorization": "Bearer test-user-a"},
    )
    assert owner_response.status_code == 200
    assert owner_response.content == b"png-test-content"
    assert owner_response.headers["cache-control"] == "private, no-store"
    assert foreign_response.status_code == legacy_response.status_code == 404
    assert owned_api_test_client.get("/reports/charts/chart.png").status_code == 404


def test_get_allowed_origins_normalization():
    from app.api.main import get_allowed_origins

    # Empty candidate returns default local origins
    default_origins = get_allowed_origins("")
    assert "http://localhost:3000" in default_origins
    assert "http://127.0.0.1:3000" in default_origins

    # Trailing slash and paths are stripped to scheme://netloc
    custom = get_allowed_origins("https://production.example.com/subpath/")
    assert "https://production.example.com" in custom
    assert "http://localhost:3000" in custom

    # Custom port is preserved
    custom_port = get_allowed_origins("http://dashboard.local:4000/app")
    assert "http://dashboard.local:4000" in custom_port

    # Wildcards and invalid schemes are strictly rejected
    assert get_allowed_origins("*") == default_origins
    assert get_allowed_origins("http://*") == default_origins
    assert get_allowed_origins("javascript:alert(1)") == default_origins
    assert get_allowed_origins("ftp://files.example.com") == default_origins


def test_cors_preflight_and_get_allowed_origins(api_test_client):
    # Preflight OPTIONS request from allowed origin
    preflight = api_test_client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "GET" in preflight.headers.get("access-control-allow-methods", "")

    # GET request with allowed origin
    get_res = api_test_client.get(
        "/api/health",
        headers={"Origin": "http://127.0.0.1:3000"},
    )
    assert get_res.status_code == 200
    assert get_res.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


def test_cors_rejected_origin(api_test_client):
    # Preflight OPTIONS request from untrusted origin
    preflight = api_test_client.options(
        "/api/health",
        headers={
            "Origin": "https://malicious.attacker.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Untrusted origin must not receive Access-Control-Allow-Origin
    assert preflight.headers.get("access-control-allow-origin") is None

    # GET request from untrusted origin
    get_res = api_test_client.get(
        "/api/health",
        headers={"Origin": "https://malicious.attacker.com"},
    )
    assert get_res.headers.get("access-control-allow-origin") is None
