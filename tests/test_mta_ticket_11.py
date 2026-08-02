from __future__ import annotations

import re
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STORE = REPO_ROOT / "mta" / "ankigta" / "server" / "store.lua"
MAIN = REPO_ROOT / "mta" / "ankigta" / "server" / "main.lua"
F7 = REPO_ROOT / "mta" / "ankigta" / "client" / "panel.lua"
TICKET = REPO_ROOT / ".scratch" / "ankigta-v1" / "issues" / "11-persistent-change-history.md"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(lua: str, name: str) -> str:
    match = re.search(
        rf"(?:local )?function {re.escape(name)}\([^)]*\)(.*?)"
        rf"(?=\n(?:local function |function |[A-Za-z][A-Za-z.]* = |addEvent\())",
        lua,
        flags=re.DOTALL,
    )
    assert match, f"Lua function not found: {name}"
    return match.group(1)


def test_history_schema_is_bounded_and_persistent() -> None:
    store = source(STORE)
    assert "change_history" in store
    assert "change_history_state" in store
    assert "HISTORY_LIMIT = 100" in store
    assert "DELETE FROM change_history WHERE history_id >" in store
    assert "ORDER BY history_id DESC LIMIT" in store
    assert "Store.open" in store
    assert "ensureChangeHistorySchema" in store


def test_history_entries_capture_before_after_in_same_transaction() -> None:
    store = source(STORE)
    assert "before_json" in store
    assert "after_json" in store
    assert "recordChange" in store
    assert "historyTransaction" in store
    activation = function_body(store, "Store.activateSpatialLink")
    assert "historyTransaction" in activation
    assert "before" in activation.lower()
    assert "after" in activation.lower()


def test_undo_redo_are_persistent_and_atomic() -> None:
    store = source(STORE)
    for name in ("Store.undo", "Store.redo", "Store.historyStatus"):
        assert name in store
    assert "applyHistoryState" in store
    assert "transaction(Store.connection" in function_body(store, "moveHistory")
    assert "cursor_id" in store
    assert "relink_entity" in store
    assert "historyTransaction(" in function_body(store, "Store.relinkEntity")
    assert "exists = false" in store or "exists = metadataRows[1]" in store


def test_f7_exposes_undo_redo_controls_and_server_events() -> None:
    main = source(MAIN)
    f7 = source(F7)
    assert "UNDO_REQUEST_EVENT" in main
    assert "REDO_REQUEST_EVENT" in main
    assert "ANKIGTA.Store.undo" in main
    assert "ANKIGTA.Store.redo" in main
    assert "UNDO_REQUEST_EVENT" in f7
    assert "REDO_REQUEST_EVENT" in f7
    assert "Undo" in f7
    assert "Redo" in f7


def test_excluded_operations_are_not_recorded() -> None:
    store = source(STORE)
    adr = source(REPO_ROOT / "docs" / "adr" / "0013-use-a-bounded-persistent-change-history.md")
    assert "не журналируются" in adr
    assert "recordChange" not in function_body(store, "Store.close")
    assert "recordChange" not in function_body(store, "Store.open")


def test_sql_history_branch_and_bound_semantics() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE change_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation TEXT NOT NULL,
            target TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL
        );
        CREATE TABLE change_history_state (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            cursor_id INTEGER NOT NULL
        );
        INSERT INTO change_history_state VALUES (1, 0);
        """
    )
    for index in range(101):
        connection.execute(
            "DELETE FROM change_history WHERE history_id > "
            "(SELECT cursor_id FROM change_history_state WHERE singleton = 1)"
        )
        connection.execute(
            "INSERT INTO change_history(operation, target, before_json, after_json) "
            "VALUES (?, ?, ?, ?)",
            ("edit", str(index), "{}", "{}"),
        )
        cursor = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "UPDATE change_history_state SET cursor_id = ? WHERE singleton = 1",
            (cursor,),
        )
        connection.execute(
            "DELETE FROM change_history WHERE history_id NOT IN "
            "(SELECT history_id FROM change_history ORDER BY history_id DESC LIMIT 100)"
        )
    assert connection.execute("SELECT COUNT(*) FROM change_history").fetchone()[0] == 100
    cursor = connection.execute("SELECT cursor_id FROM change_history_state").fetchone()[0]
    previous = connection.execute(
        "SELECT MAX(history_id) FROM change_history WHERE history_id < ?", (cursor,)
    ).fetchone()[0]
    connection.execute("UPDATE change_history_state SET cursor_id = ?", (previous or 0,))
    connection.execute(
        "DELETE FROM change_history WHERE history_id > "
        "(SELECT cursor_id FROM change_history_state WHERE singleton = 1)"
    )
    connection.execute(
        "INSERT INTO change_history(operation, target, before_json, after_json) "
        "VALUES ('edit', 'branch', '{}', '{}')"
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM change_history WHERE target = 'branch'"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM change_history WHERE target = '100'"
    ).fetchone()[0] == 0


def test_mutation_and_history_rollback_together_on_history_failure() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE entity (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE change_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL
        );
        INSERT INTO entity VALUES (1, 'before');
        """
    )
    connection.execute("BEGIN")
    connection.execute("UPDATE entity SET value = 'after' WHERE id = 1")
    try:
        connection.execute(
            "INSERT INTO change_history(operation, before_json, after_json) "
            "VALUES (?, ?, NULL)",
            ("edit", "{}",),
        )
    except sqlite3.IntegrityError:
        connection.rollback()
    assert connection.execute("SELECT value FROM entity WHERE id = 1").fetchone()[0] == "before"
    assert connection.execute("SELECT COUNT(*) FROM change_history").fetchone()[0] == 0
