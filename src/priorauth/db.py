"""SQLite access. No ORM — the schema is small and explicit on purpose."""

from __future__ import annotations

import json
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


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r["name"] for r in rows]


def row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()["n"]


def upsert_policy(conn: sqlite3.Connection, policy: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO policies (policy_id, policy_type, title, jurisdiction, states,
                              effective_date, retired_date, coverage_text, source_url)
        VALUES (:policy_id, :policy_type, :title, :jurisdiction, :states,
                :effective_date, :retired_date, :coverage_text, :source_url)
        ON CONFLICT(policy_id) DO UPDATE SET
            title=excluded.title,
            coverage_text=excluded.coverage_text,
            effective_date=excluded.effective_date,
            retired_date=excluded.retired_date
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
