import json
from uuid import uuid4
import pytest
from app.storage import database


def test_workspace_modules_end_to_end(owned_api_test_client):
    auth_a = {"Authorization": "Bearer test-user-a"}
    auth_b = {"Authorization": "Bearer test-user-b"}

    # 1. Upload a dataset for user A
    upload_csv = b"transaction_id,sales,region\nT1,100,North\nT2,200,South\nT3,300,East\n"
    res = owned_api_test_client.post(
        "/api/upload",
        headers=auth_a,
        files={"file": ("test_sales.csv", upload_csv, "text/csv")},
    )
    assert res.status_code == 200
    dataset_id = res.json()["dataset_id"]

    # 2. Test Datasets Module: GET /api/datasets
    ds_res = owned_api_test_client.get("/api/datasets", headers=auth_a)
    assert ds_res.status_code == 200
    datasets = ds_res.json()
    assert any(d["dataset_id"] == dataset_id for d in datasets)

    # User B should NOT see User A's dataset
    ds_b_res = owned_api_test_client.get("/api/datasets", headers=auth_b)
    assert ds_b_res.status_code == 200
    assert not any(d["dataset_id"] == dataset_id for d in ds_b_res.json())

    # 3. Test Dataset Details: GET /api/datasets/item/{dataset_id}
    details_res = owned_api_test_client.get(f"/api/datasets/item/{dataset_id}", headers=auth_a)
    assert details_res.status_code == 200
    details = details_res.json()
    assert details["dataset_id"] == dataset_id
    assert details["row_count"] == 3
    assert details["col_count"] == 3
    assert "sales" in details["column_names"]

    # User B cannot access details
    assert owned_api_test_client.get(f"/api/datasets/item/{dataset_id}", headers=auth_b).status_code == 404

    # 4. Run Analysis for User A to generate Sessions, Reports, and Traces
    analysis_res = owned_api_test_client.post(
        "/api/analyze",
        headers=auth_a,
        json={"user_query": "Profile this dataset", "dataset_id": dataset_id},
    )
    assert analysis_res.status_code == 200
    session_id = analysis_res.json()["session_id"]

    # 5. Test Sessions Module: GET /api/sessions
    sess_res = owned_api_test_client.get("/api/sessions", headers=auth_a)
    assert sess_res.status_code == 200
    sessions = sess_res.json()
    assert any(s["session_id"] == session_id for s in sessions)

    # User B cannot see User A's sessions
    sess_b_res = owned_api_test_client.get("/api/sessions", headers=auth_b)
    assert sess_b_res.status_code == 200
    assert not any(s["session_id"] == session_id for s in sess_b_res.json())

    # 6. Test Reports Module: GET /api/reports
    rep_res = owned_api_test_client.get("/api/reports", headers=auth_a)
    assert rep_res.status_code == 200
    reports = rep_res.json()
    assert any(r["session_id"] == session_id for r in reports)

    # User B cannot see User A's reports
    rep_b_res = owned_api_test_client.get("/api/reports", headers=auth_b)
    assert rep_b_res.status_code == 200
    assert not any(r["session_id"] == session_id for r in rep_b_res.json())

    # 7. Test Traces Module: GET /api/traces
    traces_res = owned_api_test_client.get("/api/traces", headers=auth_a)
    assert traces_res.status_code == 200
    traces = traces_res.json()
    assert any(t["session_id"] == session_id for t in traces)

    # User B cannot see User A's traces
    traces_b_res = owned_api_test_client.get("/api/traces", headers=auth_b)
    assert traces_b_res.status_code == 200
    assert not any(t["session_id"] == session_id for t in traces_b_res.json())

    # 8. Test Evaluations Module: GET /api/evaluations and POST /api/evaluations/run
    eval_res = owned_api_test_client.get("/api/evaluations", headers=auth_a)
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert "pipeline_validations" in eval_data
    assert "benchmark_runs" in eval_data
    assert "available_benchmarks" in eval_data
    assert len(eval_data["available_benchmarks"]) >= 2

    # Run Benchmark: sales_aggregations_10
    run_res = owned_api_test_client.post(
        "/api/evaluations/run",
        headers=auth_a,
        json={"benchmark_id": "sales_aggregations_10"},
    )
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["accuracy_score"] == 100.0
    assert run_data["status"] == "passed"
    assert run_data["assertions_passed"] == run_data["assertions_total"]

    # Run Benchmark: stress_sales_500k
    run_stress_res = owned_api_test_client.post(
        "/api/evaluations/run",
        headers=auth_a,
        json={"benchmark_id": "stress_sales_500k"},
    )
    assert run_stress_res.status_code == 200
    stress_run_data = run_stress_res.json()
    assert stress_run_data["accuracy_score"] == 100.0
    assert stress_run_data["status"] == "passed"

    # Verify run persisted
    eval_after = owned_api_test_client.get("/api/evaluations", headers=auth_a).json()
    assert len(eval_after["benchmark_runs"]) >= 2

    # 9. Test In-place Dataset Replacement: POST /api/datasets/replace/{dataset_id}
    replacement_csv = b"transaction_id,sales,region\nT1,500,North\nT2,600,South\n"
    replace_res = owned_api_test_client.post(
        f"/api/datasets/replace/{dataset_id}",
        headers=auth_a,
        files={"file": ("updated_sales.csv", replacement_csv, "text/csv")},
    )
    assert replace_res.status_code == 200
    assert replace_res.json()["dataset_id"] == dataset_id
    assert replace_res.json()["validation"]["rows"] == 2

    # Details reflect updated data
    details_after_replace = owned_api_test_client.get(f"/api/datasets/item/{dataset_id}", headers=auth_a).json()
    assert details_after_replace["row_count"] == 2

    # 10. Test Dataset Deletion: DELETE /api/datasets/item/{dataset_id}
    del_res = owned_api_test_client.delete(f"/api/datasets/item/{dataset_id}", headers=auth_a)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify dataset is gone
    assert owned_api_test_client.get(f"/api/datasets/item/{dataset_id}", headers=auth_a).status_code == 404

    # Verify session remains intact with nullified owned_dataset_id
    sess_after_del = owned_api_test_client.get("/api/sessions", headers=auth_a).json()
    assert any(s["session_id"] == session_id for s in sess_after_del)
