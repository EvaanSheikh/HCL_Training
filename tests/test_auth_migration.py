import sqlite3

import pytest

from scripts.migrate_auth import migrate


def test_migration_preserves_legacy_rows_and_is_repeatable(tmp_path):
    db_path = tmp_path / "legacy.db"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE analysis_sessions(session_id TEXT PRIMARY KEY,user_query TEXT NOT NULL,dataset_id TEXT NOT NULL,status TEXT NOT NULL,analysis_plan TEXT,tool_calls TEXT,evidence TEXT,validation_results TEXT,errors TEXT,final_report TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    db.execute("INSERT INTO analysis_sessions(session_id,user_query,dataset_id,status,created_at,updated_at) VALUES('legacy','q','old-dataset','done','now','now')")
    db.commit(); db.close()

    migrate(db_path)
    migrate(db_path)

    db = sqlite3.connect(db_path)
    legacy = db.execute("SELECT session_id,dataset_id,owner_user_id,owned_dataset_id FROM analysis_sessions").fetchone()
    assert legacy == ("legacy", "old-dataset", None, None)
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 0  # SQLite's per-connection default; runtime connection enables it.
    user = "u1"
    db.execute("INSERT INTO users VALUES(?,?,?,?)", (user, "issuer", "subject", "now"))
    db.execute("INSERT INTO datasets VALUES(?,?,?,?)", ("d1", user, ".csv", "now"))
    db.commit()
    db.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO datasets VALUES(?,?,?,?)", ("d2", "missing-user", ".csv", "now"))
    db.close()


def test_application_connections_enable_foreign_keys(tmp_path, monkeypatch):
    from app.storage import database
    path = tmp_path / "app.db"
    path.touch()
    migrate(path)
    monkeypatch.setattr(database, "DB_PATH", path)
    with database.get_connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_owned_resources_are_scoped_and_legacy_session_stays_unowned(tmp_path, monkeypatch):
    from app.storage import database
    path = tmp_path / "owners.db"
    path.touch()
    migrate(path)
    monkeypatch.setattr(database, "DB_PATH", path)
    owner = database.get_or_create_user("https://issuer/", "subject-a")
    other = database.get_or_create_user("https://issuer/", "subject-b")
    database.register_dataset("dataset-a", owner, ".csv")
    assert database.owns_dataset("dataset-a", owner)
    assert not database.owns_dataset("dataset-a", other)
    with database.get_connection() as connection:
        connection.execute("INSERT INTO analysis_sessions(session_id,user_query,dataset_id,status,created_at,updated_at,owner_user_id,owned_dataset_id) VALUES('session-a','q','dataset-a','done','now','now',?,?)", (owner, "dataset-a"))
        connection.execute("INSERT INTO analysis_sessions(session_id,user_query,dataset_id,status,created_at,updated_at) VALUES('legacy','q','old-id','done','now','now')")
        connection.execute("INSERT INTO report_assets(asset_id,session_id,relative_path,media_type) VALUES('asset-a','session-a','session-a/chart.png','image/png')")
    assert database.get_owned_analysis_session("session-a", owner) is not None
    assert database.get_owned_analysis_session("session-a", other) is None
    assert database.get_owned_analysis_session("legacy", owner) is None
    assert database.get_owned_report_asset("session-a", "asset-a", owner) is not None
    assert database.get_owned_report_asset("session-a", "asset-a", other) is None
    assert database.get_owned_report_asset("legacy", "asset-a", owner) is None
