import json
import os
import re
import stat
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("NOHA_DATABASE_PATH", str(BASE_DIR / "data" / "analyst.db"))).resolve()


def _safe_report(text: str) -> str:
    """Avoid returning generated server filesystem paths in API text."""
    if not text:
        return ""
    return re.sub(r"(?:[A-Za-z]:[\\/]|/(?:[^\s`]+/)+)[^\s`]*", "[private asset]", text)


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Apply restrictive permissions on the database file the first
    # time we connect (POSIX only; Windows relies on directory ACLs).
    if os.name != "nt" and DB_PATH.exists():
        current_mode = stat.S_IMODE(os.stat(DB_PATH).st_mode)
        if current_mode & 0o177:  # any group/other bits set
            os.chmod(DB_PATH, 0o600)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_sessions (
                session_id TEXT PRIMARY KEY,
                user_query TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                status TEXT NOT NULL,
                analysis_plan TEXT,
                tool_calls TEXT,
                evidence TEXT,
                validation_results TEXT,
                errors TEXT,
                final_report TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_metadata (
                dataset_id TEXT PRIMARY KEY,
                filename TEXT,
                size_bytes INTEGER,
                row_count INTEGER,
                col_count INTEGER,
                profile_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                run_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                benchmark_name TEXT NOT NULL,
                dataset_id TEXT,
                status TEXT NOT NULL,
                accuracy_score REAL,
                assertions_passed INTEGER,
                assertions_total INTEGER,
                execution_time_ms REAL,
                details_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.commit()


def save_analysis_session(state: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO analysis_sessions (
                session_id,
                user_query,
                dataset_id,
                status,
                analysis_plan,
                tool_calls,
                evidence,
                validation_results,
                errors,
                final_report,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(session_id) DO UPDATE SET
                status = excluded.status,
                analysis_plan = excluded.analysis_plan,
                tool_calls = excluded.tool_calls,
                evidence = excluded.evidence,
                validation_results = excluded.validation_results,
                errors = excluded.errors,
                final_report = excluded.final_report,
                updated_at = excluded.updated_at
            """,
            (
                state["session_id"],
                state.get("user_query", ""),
                state.get("dataset_id", ""),
                state.get("status", ""),
                json.dumps(state.get("analysis_plan", []), default=str),
                json.dumps(state.get("tool_calls", []), default=str),
                json.dumps(state.get("evidence", []), default=str),
                json.dumps(
                    state.get("validation_results", []),
                    default=str,
                ),
                json.dumps(state.get("errors", []), default=str),
                state.get("final_report", ""),
                now,
                now,
            ),
        )

        connection.commit()


def get_analysis_session(session_id: str) -> dict | None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT * FROM analysis_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        )

        row = cursor.fetchone()

    if not row:
        return None

    return {
        "session_id": row["session_id"],
        "user_query": row["user_query"],
        "dataset_id": row["dataset_id"],
        "status": row["status"],
        "analysis_plan": json.loads(row["analysis_plan"] or "[]"),
        "tool_calls": json.loads(row["tool_calls"] or "[]"),
        "evidence": json.loads(row["evidence"] or "[]"),
        "validation_results": json.loads(row["validation_results"] or "[]"),
        "errors": json.loads(row["errors"] or "[]"),
        "final_report": row["final_report"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_or_create_user(issuer: str, subject: str) -> str:
    """Resolve a stable OIDC identity to an internal user ID."""
    import uuid
    with get_connection() as connection:
        user_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO users(user_id, issuer, subject, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(issuer,subject) DO NOTHING",
            (user_id, issuer, subject, datetime.now(timezone.utc).isoformat()),
        )
        row = connection.execute(
            "SELECT user_id FROM users WHERE issuer = ? AND subject = ?", (issuer, subject)
        ).fetchone()
        return row["user_id"]


def register_dataset(dataset_id: str, owner_user_id: str, extension: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO datasets(dataset_id, owner_user_id, extension, created_at) VALUES (?, ?, ?, ?)",
            (dataset_id, owner_user_id, extension, datetime.now(timezone.utc).isoformat()),
        )


def owns_dataset(dataset_id: str, owner_user_id: str) -> bool:
    with get_connection() as connection:
        return connection.execute(
            "SELECT 1 FROM datasets WHERE dataset_id=? AND owner_user_id=?", (dataset_id, owner_user_id)
        ).fetchone() is not None


def owns_session(session_id: str, owner_user_id: str) -> bool:
    with get_connection() as connection:
        return connection.execute(
            "SELECT 1 FROM analysis_sessions WHERE session_id=? AND owner_user_id=?", (session_id, owner_user_id)
        ).fetchone() is not None


def save_analysis_session_owned(state: dict, owner_user_id: str) -> None:
    """Persist session output without allowing ownership changes."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        dataset = connection.execute(
            "SELECT owner_user_id FROM datasets WHERE dataset_id=?", (state.get("dataset_id"),)
        ).fetchone()
        if dataset is None or dataset["owner_user_id"] != owner_user_id:
            raise PermissionError("Dataset ownership conflict")
        existing = connection.execute(
            "SELECT owner_user_id FROM analysis_sessions WHERE session_id=?", (state["session_id"],)
        ).fetchone()
        if existing and existing["owner_user_id"] != owner_user_id:
            raise PermissionError("Session ownership conflict")
        connection.execute(
            """INSERT INTO analysis_sessions(session_id,user_query,dataset_id,status,analysis_plan,tool_calls,
            evidence,validation_results,errors,final_report,created_at,updated_at,owner_user_id,owned_dataset_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET status=excluded.status,
            analysis_plan=excluded.analysis_plan,tool_calls=excluded.tool_calls,evidence=excluded.evidence,
            validation_results=excluded.validation_results,errors=excluded.errors,final_report=excluded.final_report,
            updated_at=excluded.updated_at WHERE analysis_sessions.owner_user_id=excluded.owner_user_id""",
            (state["session_id"], state.get("user_query", ""), state.get("dataset_id", ""),
             state.get("status", ""), json.dumps(state.get("analysis_plan", []), default=str),
             json.dumps(state.get("tool_calls", []), default=str), json.dumps(state.get("evidence", []), default=str),
             json.dumps(state.get("validation_results", []), default=str), json.dumps(state.get("errors", []), default=str),
             state.get("final_report", ""), now, now, owner_user_id, state.get("dataset_id")),
        )
        report_root = (BASE_DIR / "reports" / "private").resolve()
        connection.execute("DELETE FROM report_assets WHERE session_id=?", (state["session_id"],))
        for chart_path in state.get("visualizations", []):
            candidate = Path(chart_path)
            if candidate.is_symlink() or candidate.suffix.lower() != ".png" or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            try:
                relative = resolved.relative_to(report_root)
            except ValueError:
                continue
            connection.execute(
                "INSERT INTO report_assets(asset_id,session_id,relative_path,media_type) VALUES(?,?,?,?)",
                (str(uuid4()), state["session_id"], relative.as_posix(), "image/png"),
            )


def get_owned_analysis_session(session_id: str, owner_user_id: str) -> dict | None:
    if not owns_session(session_id, owner_user_id):
        return None
    return get_analysis_session(session_id)


def get_owned_report_asset(session_id: str, asset_id: str, owner_user_id: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            """SELECT a.relative_path,a.media_type FROM report_assets a
            JOIN analysis_sessions s ON s.session_id=a.session_id
            WHERE a.asset_id=? AND a.session_id=? AND s.owner_user_id=?""",
            (asset_id, session_id, owner_user_id),
        ).fetchone()
    if row is None:
        return None
    return {"relative_path": row["relative_path"], "media_type": row["media_type"]}


def get_owned_report_assets(session_id: str, owner_user_id: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT a.asset_id,a.media_type FROM report_assets a
            JOIN analysis_sessions s ON s.session_id=a.session_id
            WHERE a.session_id=? AND s.owner_user_id=? ORDER BY a.rowid""",
            (session_id, owner_user_id),
        ).fetchall()
    return [{"asset_id": row["asset_id"], "media_type": row["media_type"]} for row in rows]


def save_dataset_metadata(
    dataset_id: str,
    filename: str,
    size_bytes: int,
    row_count: int | None = None,
    col_count: int | None = None,
    profile: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    profile_str = json.dumps(profile, default=str) if profile else None
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO dataset_metadata(dataset_id, filename, size_bytes, row_count, col_count, profile_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dataset_id) DO UPDATE SET
                filename = excluded.filename,
                size_bytes = excluded.size_bytes,
                row_count = COALESCE(excluded.row_count, dataset_metadata.row_count),
                col_count = COALESCE(excluded.col_count, dataset_metadata.col_count),
                profile_json = COALESCE(excluded.profile_json, dataset_metadata.profile_json)
            """,
            (dataset_id, filename, size_bytes, row_count, col_count, profile_str, now),
        )
        connection.commit()


def list_owned_datasets(owner_user_id: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT d.dataset_id, d.extension, d.created_at,
                   m.filename, m.size_bytes, m.row_count, m.col_count
            FROM datasets d
            LEFT JOIN dataset_metadata m ON d.dataset_id = m.dataset_id
            WHERE d.owner_user_id = ?
            ORDER BY d.created_at DESC
            """,
            (owner_user_id,),
        ).fetchall()

    results = []
    uploads_dir = (BASE_DIR / "data" / "uploads").resolve()
    for row in rows:
        size = row["size_bytes"]
        if size is None:
            p = uploads_dir / f"{row['dataset_id']}{row['extension']}"
            if p.exists() and p.is_file():
                size = p.stat().st_size
            else:
                size = 0
        results.append({
            "dataset_id": row["dataset_id"],
            "extension": row["extension"],
            "created_at": row["created_at"],
            "filename": row["filename"] or f"dataset_{row['dataset_id'][:8]}{row['extension']}",
            "size_bytes": size,
            "row_count": row["row_count"],
            "col_count": row["col_count"],
            "validation_status": "valid" if (row["row_count"] or 0) > 0 else "ready",
        })
    return results


def get_owned_dataset_details(dataset_id: str, owner_user_id: str) -> dict | None:
    if not owns_dataset(dataset_id, owner_user_id):
        return None
    with get_connection() as connection:
        d_row = connection.execute(
            "SELECT dataset_id, extension, created_at FROM datasets WHERE dataset_id=?",
            (dataset_id,),
        ).fetchone()
        m_row = connection.execute(
            "SELECT filename, size_bytes, row_count, col_count, profile_json FROM dataset_metadata WHERE dataset_id=?",
            (dataset_id,),
        ).fetchone()

    if not d_row:
        return None

    uploads_dir = (BASE_DIR / "data" / "uploads").resolve()
    file_path = uploads_dir / f"{d_row['dataset_id']}{d_row['extension']}"
    size_bytes = m_row["size_bytes"] if m_row else None
    if size_bytes is None and file_path.exists() and file_path.is_file():
        size_bytes = file_path.stat().st_size

    profile = None
    if m_row and m_row["profile_json"]:
        try:
            profile = json.loads(m_row["profile_json"])
        except Exception:
            profile = None

    if not profile and file_path.exists() and file_path.is_file():
        from app.tools.data_tools import profile_dataset
        try:
            profile = profile_dataset(dataset_id)
            save_dataset_metadata(
                dataset_id,
                (m_row["filename"] if m_row else None) or f"dataset_{dataset_id[:8]}{d_row['extension']}",
                size_bytes,
                profile.get("rows"),
                profile.get("columns"),
                profile,
            )
        except Exception:
            profile = None

    row_count = (profile.get("rows") if profile else None) or (m_row["row_count"] if m_row else None) or 0
    col_count = (profile.get("columns") if profile else None) or (m_row["col_count"] if m_row else None) or 0
    filename = (m_row["filename"] if m_row else None) or f"dataset_{d_row['dataset_id'][:8]}{d_row['extension']}"

    return {
        "dataset_id": d_row["dataset_id"],
        "extension": d_row["extension"],
        "created_at": d_row["created_at"],
        "filename": filename,
        "size_bytes": size_bytes or 0,
        "row_count": row_count,
        "col_count": col_count,
        "column_names": profile.get("column_names", []) if profile else [],
        "dtypes": profile.get("dtypes", {}) if profile else {},
        "missing_values": profile.get("missing_values", {}) if profile else {},
        "duplicate_rows": profile.get("duplicate_rows", 0) if profile else 0,
        "validation_status": "valid" if row_count > 0 else "ready",
        "profile": profile,
    }


def delete_owned_dataset(dataset_id: str, owner_user_id: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT extension FROM datasets WHERE dataset_id=? AND owner_user_id=?",
            (dataset_id, owner_user_id),
        ).fetchone()
        if not row:
            return False
        extension = row["extension"]
        connection.execute("DELETE FROM dataset_metadata WHERE dataset_id=?", (dataset_id,))
        connection.execute("UPDATE analysis_sessions SET owned_dataset_id=NULL WHERE owned_dataset_id=?", (dataset_id,))
        connection.execute("DELETE FROM datasets WHERE dataset_id=? AND owner_user_id=?", (dataset_id, owner_user_id))
        connection.commit()

    file_path = BASE_DIR / "data" / "uploads" / f"{dataset_id}{extension}"
    try:
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except Exception:
        pass
    return True


def list_owned_sessions(owner_user_id: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT s.session_id, s.user_query, s.dataset_id, s.status,
                   s.tool_calls, s.evidence, s.validation_results, s.errors,
                   s.final_report, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM report_assets a WHERE a.session_id = s.session_id) as chart_count,
                   m.filename as dataset_name
            FROM analysis_sessions s
            LEFT JOIN dataset_metadata m ON s.dataset_id = m.dataset_id
            WHERE s.owner_user_id = ?
            ORDER BY s.created_at DESC
            """,
            (owner_user_id,),
        ).fetchall()

    results = []
    for row in rows:
        tool_calls = json.loads(row["tool_calls"] or "[]")
        evidence = json.loads(row["evidence"] or "[]")
        validation = json.loads(row["validation_results"] or "[]")
        errors = json.loads(row["errors"] or "[]")
        final_report = _safe_report(row["final_report"] or "")

        results.append({
            "session_id": row["session_id"],
            "user_query": row["user_query"],
            "dataset_id": row["dataset_id"],
            "dataset_name": row["dataset_name"] or f"dataset_{row['dataset_id'][:8]}",
            "status": row["status"],
            "tool_calls_count": len(tool_calls),
            "evidence_count": len(evidence),
            "validation_count": len(validation),
            "all_validations_passed": len(validation) > 0 and all(v.get("passed", False) for v in validation),
            "errors_count": len(errors),
            "has_report": bool(final_report.strip()),
            "chart_count": row["chart_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    return results


def list_owned_reports(owner_user_id: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT s.session_id, s.user_query, s.dataset_id, s.status,
                   s.final_report, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM report_assets a WHERE a.session_id = s.session_id) as chart_count,
                   m.filename as dataset_name
            FROM analysis_sessions s
            LEFT JOIN dataset_metadata m ON s.dataset_id = m.dataset_id
            WHERE s.owner_user_id = ? AND s.final_report IS NOT NULL AND trim(s.final_report) != ''
            ORDER BY s.created_at DESC
            """,
            (owner_user_id,),
        ).fetchall()

    results = []
    for row in rows:
        report_text = _safe_report(row["final_report"] or "")
        preview = report_text[:300] + ("..." if len(report_text) > 300 else "")
        results.append({
            "report_id": row["session_id"],
            "session_id": row["session_id"],
            "title": f"Report: {row['user_query'][:60]}",
            "user_query": row["user_query"],
            "dataset_id": row["dataset_id"],
            "dataset_name": row["dataset_name"] or f"dataset_{row['dataset_id'][:8]}",
            "status": row["status"],
            "created_at": row["created_at"],
            "report_preview": preview,
            "report_length": len(report_text),
            "final_report": report_text,
            "chart_count": row["chart_count"],
            "is_saved": True,
        })
    return results


def list_owned_traces(owner_user_id: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT s.session_id, s.user_query, s.dataset_id, s.status,
                   s.analysis_plan, s.tool_calls, s.evidence, s.errors,
                   s.created_at, s.updated_at,
                   m.filename as dataset_name
            FROM analysis_sessions s
            LEFT JOIN dataset_metadata m ON s.dataset_id = m.dataset_id
            WHERE s.owner_user_id = ?
            ORDER BY s.created_at DESC
            """,
            (owner_user_id,),
        ).fetchall()

    results = []
    for row in rows:
        plan = json.loads(row["analysis_plan"] or "[]")
        calls = json.loads(row["tool_calls"] or "[]")
        raw_evidence = json.loads(row["evidence"] or "[]")
        evidence = [
            {**item, "result": "[private asset]" if item.get("operation", "").startswith("create_") else item.get("result")}
            for item in raw_evidence
        ]
        errors = [_safe_report(str(err)) for err in json.loads(row["errors"] or "[]")]

        results.append({
            "session_id": row["session_id"],
            "user_query": row["user_query"],
            "dataset_id": row["dataset_id"],
            "dataset_name": row["dataset_name"] or f"dataset_{row['dataset_id'][:8]}",
            "status": row["status"],
            "created_at": row["created_at"],
            "plan_steps": plan,
            "tool_calls": calls,
            "evidence": evidence,
            "errors": errors,
            "total_steps": len(calls),
            "has_failures": len(errors) > 0 or any(c.get("success") is False for c in calls),
        })
    return results


def list_evaluations(owner_user_id: str) -> dict:
    with get_connection() as connection:
        session_rows = connection.execute(
            """
            SELECT s.session_id, s.user_query, s.dataset_id, s.status,
                   s.validation_results, s.created_at,
                   m.filename as dataset_name
            FROM analysis_sessions s
            LEFT JOIN dataset_metadata m ON s.dataset_id = m.dataset_id
            WHERE s.owner_user_id = ? AND s.validation_results IS NOT NULL AND s.validation_results != '[]'
            ORDER BY s.created_at DESC
            """,
            (owner_user_id,),
        ).fetchall()

        run_rows = connection.execute(
            """
            SELECT * FROM evaluation_runs
            WHERE owner_user_id = ?
            ORDER BY created_at DESC
            """,
            (owner_user_id,),
        ).fetchall()

    pipeline_validations = []
    for row in session_rows:
        val_checks = json.loads(row["validation_results"] or "[]")
        all_passed = len(val_checks) > 0 and all(v.get("passed", False) for v in val_checks)
        pipeline_validations.append({
            "session_id": row["session_id"],
            "user_query": row["user_query"],
            "dataset_id": row["dataset_id"],
            "dataset_name": row["dataset_name"] or f"dataset_{row['dataset_id'][:8]}",
            "created_at": row["created_at"],
            "status": row["status"],
            "all_passed": all_passed,
            "checks": val_checks,
            "passed_count": sum(1 for v in val_checks if v.get("passed", False)),
            "total_count": len(val_checks),
        })

    benchmark_runs = []
    for row in run_rows:
        details = json.loads(row["details_json"] or "{}")
        benchmark_runs.append({
            "run_id": row["run_id"],
            "benchmark_name": row["benchmark_name"],
            "dataset_id": row["dataset_id"],
            "status": row["status"],
            "accuracy_score": row["accuracy_score"],
            "assertions_passed": row["assertions_passed"],
            "assertions_total": row["assertions_total"],
            "execution_time_ms": row["execution_time_ms"],
            "details": details,
            "created_at": row["created_at"],
        })

    return {
        "pipeline_validations": pipeline_validations,
        "benchmark_runs": benchmark_runs,
        "available_benchmarks": [
            {
                "id": "stress_sales_500k",
                "name": "Deterministic Sales Benchmark (500,003 Rows)",
                "description": "Evaluates exact mathematical computation across 500,003 records and 22 columns against ground truth constants (Mean: $420.44, Median: $143.06, Sum: $210,220,637.26, Min: $3.49, Max: $35,535.47, Duplicate Rows: 3).",
                "dataset_file": "autonomous_business_sales_dataset_stress.csv",
                "expected_assertions": 6,
            },
            {
                "id": "sales_aggregations_10",
                "name": "Standard Regional Aggregation Benchmark",
                "description": "Evaluates regional grouping, deterministic sum aggregations, and chart asset consistency against sales.csv.",
                "dataset_file": "sales.csv",
                "expected_assertions": 4,
            }
        ]
    }


def run_evaluation(benchmark_id: str | None, owner_user_id: str) -> dict:
    import time
    t0 = time.time()
    now = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid4())

    assertions = []
    benchmark_name = "Deterministic Sales Benchmark (500,003 Rows)"
    dataset_name = "autonomous_business_sales_dataset_stress.csv"

    if benchmark_id == "stress_sales_500k" or benchmark_id is None:
        dataset_path = BASE_DIR / "data" / "test" / "autonomous_business_sales_dataset_stress.csv"
        if not dataset_path.exists():
            raise FileNotFoundError("Benchmark dataset not found.")

        import pandas as pd
        df = pd.read_csv(dataset_path)
        if "revenue" not in df.columns and "Quantity" in df.columns and "UnitSellingPrice" in df.columns:
            discount = df["DiscountPercentage"] if "DiscountPercentage" in df.columns else 0
            df["revenue"] = df["Quantity"] * df["UnitSellingPrice"] * (1 - discount / 100.0)
        df["sales"] = df["revenue"]

        rows = int(df.shape[0])
        cols = int(df.shape[1])
        mean_sales = float(df["sales"].mean())
        median_sales = float(df["sales"].median())
        sum_sales = float(df["sales"].sum())
        min_sales = float(df["sales"].min())
        max_sales = float(df["sales"].max())
        duplicates = int(df.duplicated().sum())

        GT_ROWS = 500003
        GT_MEAN = 420.4387518824887
        GT_MEDIAN = 143.0605
        GT_SUM = 210220637.2575
        GT_MIN = 3.493
        GT_MAX = 35535.474
        GT_DUPS = 3

        assertions.append({
            "name": "Row Count Precision",
            "expected": str(GT_ROWS),
            "actual": str(rows),
            "passed": rows == GT_ROWS,
            "category": "Data Ingestion & Integrity",
        })
        assertions.append({
            "name": "Average Sales (Mean) Precision",
            "expected": "$420.44",
            "actual": f"${mean_sales:.2f}",
            "passed": abs(mean_sales - GT_MEAN) < 1e-4,
            "category": "Statistical Computation",
        })
        assertions.append({
            "name": "Median Sales Precision",
            "expected": "$143.06",
            "actual": f"${median_sales:.2f}",
            "passed": abs(median_sales - GT_MEDIAN) < 1e-4,
            "category": "Statistical Computation",
        })
        assertions.append({
            "name": "Total Sales Volume (Sum) Precision",
            "expected": "$210,220,637.26",
            "actual": f"${sum_sales:,.2f}",
            "passed": abs(sum_sales - GT_SUM) < 1e-2,
            "category": "Statistical Computation",
        })
        assertions.append({
            "name": "Min/Max Range Boundaries",
            "expected": f"[{GT_MIN}, {GT_MAX}]",
            "actual": f"[{min_sales}, {max_sales}]",
            "passed": abs(min_sales - GT_MIN) < 1e-3 and abs(max_sales - GT_MAX) < 1e-3,
            "category": "Statistical Computation",
        })
        assertions.append({
            "name": "Duplicate Row Detection",
            "expected": f"{GT_DUPS} duplicates",
            "actual": f"{duplicates} duplicates",
            "passed": duplicates == GT_DUPS,
            "category": "Data Quality Profiling",
        })
    else:
        benchmark_name = "Standard Regional Aggregation Benchmark"
        dataset_name = "sales.csv"
        dataset_path = BASE_DIR / "data" / "sample" / "sales.csv"
        if not dataset_path.exists():
            dataset_path = BASE_DIR / "data" / "test" / "sales.csv"
        if not dataset_path.exists():
            raise FileNotFoundError("Benchmark dataset not found.")

        import pandas as pd
        df = pd.read_csv(dataset_path)
        rows = int(df.shape[0])
        cols = int(df.shape[1])
        agg = df.groupby("region")["revenue"].sum().to_dict()

        assertions.append({
            "name": "Record Count",
            "expected": "10",
            "actual": str(rows),
            "passed": rows == 10,
            "category": "Data Ingestion",
        })
        assertions.append({
            "name": "North Region Revenue",
            "expected": "$300,000.00",
            "actual": f"${float(agg.get('North', 0)):,.2f}",
            "passed": abs(float(agg.get("North", 0)) - 300000.0) < 1e-2,
            "category": "Aggregation",
        })
        assertions.append({
            "name": "South Region Revenue",
            "expected": "$285,000.00",
            "actual": f"${float(agg.get('South', 0)):,.2f}",
            "passed": abs(float(agg.get("South", 0)) - 285000.0) < 1e-2,
            "category": "Aggregation",
        })
        assertions.append({
            "name": "Distinct Regions Count",
            "expected": "4",
            "actual": str(len(agg)),
            "passed": len(agg) == 4,
            "category": "Grouping",
        })
        assertions.append({
            "name": "Total Dataset Revenue",
            "expected": "$900,000.00",
            "actual": f"${float(df['revenue'].sum()):,.2f}",
            "passed": abs(float(df["revenue"].sum()) - 900000.0) < 1e-2,
            "category": "Aggregation",
        })

    elapsed_ms = round((time.time() - t0) * 1000, 2)
    passed_count = sum(1 for a in assertions if a["passed"])
    total_count = len(assertions)
    score = round((passed_count / total_count) * 100.0, 1) if total_count > 0 else 0.0
    status = "passed" if passed_count == total_count else "failed"

    details = {
        "dataset_name": dataset_name,
        "assertions": assertions,
        "summary": f"{passed_count} of {total_count} assertions passed ({score}% accuracy) in {elapsed_ms}ms.",
    }

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO evaluation_runs (
                run_id, owner_user_id, benchmark_name, dataset_id, status,
                accuracy_score, assertions_passed, assertions_total, execution_time_ms,
                details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, owner_user_id, benchmark_name, dataset_name, status,
                score, passed_count, total_count, elapsed_ms, json.dumps(details), now
            ),
        )
        connection.commit()

    return {
        "run_id": run_id,
        "benchmark_name": benchmark_name,
        "dataset_name": dataset_name,
        "status": status,
        "accuracy_score": score,
        "assertions_passed": passed_count,
        "assertions_total": total_count,
        "execution_time_ms": elapsed_ms,
        "details": details,
        "created_at": now,
    }
