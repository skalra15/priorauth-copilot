"""One-time export: local SQLite -> prod Postgres (e.g. Supabase).

Run this once after creating the Supabase project, and again any time you
want to refresh prod with newer local data (ingest a new CMS drop, extract
more policies, etc.) -- it's a full overwrite of the target tables, not an
incremental sync.

Usage:
    TARGET_DATABASE_URL="postgres://user:pass@host:port/dbname" \\
        python scripts/migrate_to_postgres.py

Deliberately NOT reusing db.connect() for both sides at once -- that
function picks SQLite vs Postgres from config.DATABASE_URL globally, so this
script reads everything from SQLite first (config.DATABASE_URL unset, the
normal local-dev state), then flips that flag in-process to write to
Postgres. Two live connections under one global switch would be more
confusing than this straightforward "read phase, then write phase" split.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from priorauth import config, db  # noqa: E402

TABLES = ["policies", "policy_codes", "code_descriptions", "extracted_criteria", "llm_cache"]
BATCH_SIZE = 2000


def _read_all_rows() -> dict[str, tuple[list[str], list[tuple]]]:
    """Read every row of every table from local SQLite. Returns
    {table: (column_names, rows_as_tuples)}."""
    assert not config.DATABASE_URL, "Expected DATABASE_URL unset to read from local SQLite"
    data = {}
    with db.connect() as conn:
        for table in TABLES:
            cols = db.columns(conn, table)
            rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
            data[table] = (cols, [tuple(r[c] for c in cols) for r in rows])
            print(f"  read {len(rows):>7,} rows from {table}")
    return data


def _write_all_rows(data: dict[str, tuple[list[str], list[tuple]]], target_url: str) -> None:
    config.DATABASE_URL = target_url
    db.init_db()
    with db.connect() as conn:
        for table, (cols, rows) in data.items():
            if not rows:
                print(f"  {table}: nothing to write")
                continue
            placeholders = ", ".join(["?"] * len(cols))
            col_list = ", ".join(f'"{c}"' for c in cols)
            sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                conn.executemany(sql, batch)
                print(f"  {table}: {min(i + BATCH_SIZE, len(rows)):>7,} / {len(rows):,}", end="\r")
            print(f"  {table}: {len(rows):>7,} / {len(rows):,} written")


def main() -> None:
    target_url = os.environ.get("TARGET_DATABASE_URL", "")
    if not target_url:
        print("Set TARGET_DATABASE_URL to the destination Postgres connection string.")
        raise SystemExit(1)
    if config.DATABASE_URL:
        print("Unset DATABASE_URL before running this -- it must read from local SQLite first.")
        raise SystemExit(1)

    print("Reading from local SQLite...")
    data = _read_all_rows()

    print("\nWriting to target Postgres...")
    _write_all_rows(data, target_url)

    print("\nDone.")


if __name__ == "__main__":
    main()
