"""Application-owned resource lifecycle tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings import Settings
from backend.app.storage import SQLiteStore


def test_application_shutdown_closes_file_backed_store_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "remedygraph.sqlite3"
    close_calls: list[SQLiteStore] = []
    original_close = SQLiteStore.close

    def tracked_close(store: SQLiteStore) -> None:
        close_calls.append(store)
        original_close(store)

    monkeypatch.setattr(SQLiteStore, "close", tracked_close)
    app = create_app(Settings(workspace_root=tmp_path, database_path=str(database_path)))
    store: SQLiteStore = app.state.store

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert store.is_closed is False
        assert store.connection.execute("SELECT 1").fetchone()[0] == 1

    assert close_calls == [store]
    assert store.is_closed is True
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        store.connection.execute("SELECT 1")

    renamed_path = tmp_path / "released.sqlite3"
    database_path.rename(renamed_path)
    renamed_path.unlink()
    assert not database_path.exists()
    assert not renamed_path.exists()

    original_close(store)
    assert close_calls == [store]
    assert store.is_closed is True
