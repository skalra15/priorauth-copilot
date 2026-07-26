"""SQLite (dev/eval, canonical) or Postgres (prod, via DATABASE_URL) access.

No ORM — the schema is small and explicit on purpose. Every runtime call site
(retrieve.py, llm.py, extract.py, this file's own get_policy) uses plain
`?`-placeholder SQL and reads rows via `row["col"]` / `dict(row)`. That
interface is identical on both backends, so those call sites never need to
know which one is live -- only `connect()` here does.

Postgres is prod-only and is never written to by `ingest.normalize()` --
the project docs's rule is SQLite stays canonical for ingest/extract/eval. The prod
Postgres DB is populated once via `scripts/migrate_to_postgres.py`, which
copies the already-computed tables (policies, policy_codes,
code_descriptions, extracted_criteria, llm_cache) out of local SQLite. From
then on, Postgres only gets new rows the same way SQLite does at runtime: a
cache miss during a live `/api/check` call.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    policy_id       TEXT PRIMARY KEY,
    policy_type     TEXT NOT NULL,
    title           TEXT NOT NULL,
    jurisdiction    TEXT,
    states          TEXT,           -- JSON array
    effective_date  TEXT,
    retired_date    TEXT,
    coverage_text   TEXT NOT NULL,
    source_url      TEXT
);

CREATE TABLE IF NOT EXISTS policy_codes (
    policy_id   TEXT NOT NULL,
    code        TEXT NOT NULL,
    code_system TEXT NOT NULL,      -- CPT | HCPCS | ICD10
    covered     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (policy_id, code, code_system, covered)
);
CREATE INDEX IF NOT EXISTS idx_codes_code ON policy_codes(code, code_system);

-- Human-readable code descriptions, for the checker UI's code autocomplete.
-- Not every code has one (CMS coverage is spottier for some code systems);
-- absence here just means the autocomplete shows the bare code.
CREATE TABLE IF NOT EXISTS code_descriptions (
    code        TEXT NOT NULL,
    code_system TEXT NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (code, code_system)
);

-- Cached criteria extractions, keyed on (policy text hash, model).
CREATE TABLE IF NOT EXISTS extracted_criteria (
    policy_id    TEXT NOT NULL,
    text_hash    TEXT NOT NULL,
    model        TEXT NOT NULL,
    payload      TEXT NOT NULL,     -- JSON: ExtractedCriteria
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (text_hash, model)
);

-- Generic LLM response cache. Keeps the project inside its budget.
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key    TEXT PRIMARY KEY,
    model        TEXT NOT NULL,
    response     TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# datetime('now') is SQLite-only syntax; Postgres wants CURRENT_TIMESTAMP.
# Everything else in SCHEMA (TEXT/INTEGER columns, composite PRIMARY KEY,
# CREATE INDEX IF NOT EXISTS) is valid in both dialects unchanged.
_SCHEMA_POSTGRES = SCHEMA.replace("DEFAULT (datetime('now'))", "DEFAULT CURRENT_TIMESTAMP")

_QMARK_RE = re.compile(r"\?")


class _PGCursorWrapper:
    """Wraps a psycopg2 cursor so `conn.execute(...)` behaves like sqlite3's
    connection-level `.execute()` shortcut -- same call site, same `?`
    placeholders, same fetchone/fetchall-of-dicts return shape."""

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def execute(self, sql: str, params: tuple | list = ()) -> "_PGCursorWrapper":
        self._cursor.execute(_QMARK_RE.sub("%s", sql), params)
        return self

    def executemany(self, sql: str, seq_of_params: list) -> None:
        self._cursor.executemany(_QMARK_RE.sub("%s", sql), seq_of_params)

    def executescript(self, sql: str) -> None:
        self._cursor.execute(sql)

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list:
        return self._cursor.fetchall()


class _PGConnWrapper:
    """Same idea, at the connection level -- `conn.execute(...)` returns a
    cursor-like object, matching sqlite3.Connection's convenience method."""

    def __init__(self, pg_conn: Any) -> None:
        self._conn = pg_conn

    def execute(self, sql: str, params: tuple | list = ()) -> _PGCursorWrapper:
        cur = self._conn.cursor()
        return _PGCursorWrapper(cur).execute(sql, params)

    def executemany(self, sql: str, seq_of_params: list) -> None:
        cur = self._conn.cursor()
        _PGCursorWrapper(cur).executemany(sql, seq_of_params)

    def executescript(self, sql: str) -> None:
        cur = self._conn.cursor()
        cur.execute(sql)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _is_postgres() -> bool:
    return bool(config.DATABASE_URL)


@contextmanager
def connect() -> Iterator[Any]:
    if _is_postgres():
        import psycopg2
        import psycopg2.extras

        pg_conn = psycopg2.connect(config.DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn = _PGConnWrapper(pg_conn)
    else:
        raw = sqlite3.connect(config.DB_PATH)
        raw.row_factory = sqlite3.Row
        conn = raw
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA_POSTGRES if _is_postgres() else SCHEMA)


def table_names(conn: Any) -> list[str]:
    if _is_postgres():
        rows = conn.execute(
            "SELECT table_name AS name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return [r["name"] for r in rows]


def columns(conn: Any, table: str) -> list[str]:
    if _is_postgres():
        rows = conn.execute(
            "SELECT column_name AS name FROM information_schema.columns WHERE table_name = ?", (table,)
        ).fetchall()
    else:
        rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r["name"] for r in rows]


def row_count(conn: Any, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()["n"]


def upsert_policy(conn: Any, policy: dict[str, Any]) -> None:
    """Local/SQLite only -- called by ingest.normalize(), which never runs
    against Postgres (see module docstring). Named `:param` placeholders are
    a sqlite3-ism not translated by the Postgres wrapper above."""
    conn.execute(
        """
        INSERT INTO policies (policy_id, policy_type, title, jurisdiction, states,
                              effective_date, retired_date, coverage_text, source_url)
        VALUES (:policy_id, :policy_type, :title, :jurisdiction, :states,
                :effective_date, :retired_date, :coverage_text, :source_url)
        ON CONFLICT(policy_id) DO UPDATE SET
            title=excluded.title,
            jurisdiction=excluded.jurisdiction,
            states=excluded.states,
            coverage_text=excluded.coverage_text,
            effective_date=excluded.effective_date,
            retired_date=excluded.retired_date,
            source_url=excluded.source_url
        """,
        {
            **policy,
            "states": json.dumps(policy.get("states") or []),
        },
    )


def get_policy(policy_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM policies WHERE policy_id = ?", (policy_id,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["states"] = json.loads(d["states"] or "[]")
    return d
