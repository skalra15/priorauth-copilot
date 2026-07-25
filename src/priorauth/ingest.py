"""CMS Medicare Coverage Database ingestion.

Deliberately two-stage:

  1. `load_raw()`  — discovers every CSV under data/raw/ and loads it into SQLite
                     as `raw_<filename>`, unchanged. No assumptions about schema.
  2. `normalize()` — maps the raw tables onto the `policies` / `policy_codes`
                     shape in schemas.py.

Stage 2 is left for you to complete because CMS column names shift between
releases, and guessing them produces code that looks right and silently drops
data. Run `cli inspect` first, read the actual schema, then fill it in.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from . import config, db

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def strip_html(raw: str | None) -> str:
    """CMS ships coverage text as HTML. The extractor needs clean prose."""
    if not raw:
        return ""
    text = BeautifulSoup(raw, "lxml").get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _safe_table_name(path: Path) -> str:
    stem = path.stem.lower()
    return "raw_" + "".join(ch if ch.isalnum() else "_" for ch in stem)


def load_raw(source: Path | None = None) -> dict[str, int]:
    """Load every CSV under `source` into SQLite verbatim. Returns table→rowcount."""
    source = source or config.RAW_DIR
    csv_paths = sorted(source.rglob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(
            f"No CSVs under {source}. See the project docs Step 1.1 — the CMS bulk "
            "downloads must be fetched manually (they require a license click-through)."
        )

    db.init_db()
    loaded: dict[str, int] = {}

    with db.connect() as conn:
        for path in csv_paths:
            table = _safe_table_name(path)
            with path.open(newline="", encoding="utf-8", errors="replace") as fh:
                reader = csv.reader(fh)
                try:
                    header = next(reader)
                except StopIteration:
                    continue
                cols = [
                    "".join(ch if ch.isalnum() else "_" for ch in (h or "col")).lower()
                    or f"col{i}"
                    for i, h in enumerate(header)
                ]
                col_defs = ", ".join('"{}" TEXT'.format(c) for c in cols)
                conn.execute('DROP TABLE IF EXISTS "{}"'.format(table))
                conn.execute('CREATE TABLE "{}" ({})'.format(table, col_defs))
                placeholders = ", ".join("?" for _ in cols)
                rows = (r[: len(cols)] + [None] * (len(cols) - len(r)) for r in reader)
                conn.executemany(
                    f'INSERT INTO "{table}" VALUES ({placeholders})', rows
                )
            loaded[table] = db.row_count(conn, table)

    return loaded


def describe_raw() -> dict[str, dict]:
    """Schema + row counts for every raw table. Read this before writing normalize()."""
    out: dict[str, dict] = {}
    with db.connect() as conn:
        for table in db.table_names(conn):
            if not table.startswith("raw_"):
                continue
            cols = db.columns(conn, table)
            sample_row = conn.execute(
                f'SELECT * FROM "{table}" LIMIT 1'
            ).fetchone()
            out[table] = {
                "rows": db.row_count(conn, table),
                "columns": cols,
                "sample": dict(sample_row) if sample_row else {},
            }
    return out


# ---------------------------------------------------------------------------
# STAGE 2 — YOU IMPLEMENT THIS (, step 1.3)
# ---------------------------------------------------------------------------


def normalize() -> tuple[int, int]:
    """Map raw CMS tables onto `policies` and `policy_codes`.

    Run `python -m priorauth.cli inspect` first and read the real schema.

    What you are looking for in the raw tables:
      * the LCD record table — an id, a title, effective/retired dates, and a long
        HTML field holding "Coverage Indications, Limitations, and/or Medical
        Necessity". That HTML field goes through strip_html() into coverage_text.
      * the HCPCS/CPT association table — policy id → procedure code
      * the ICD-10 tables — usually *two*, one covered and one non-covered. The
        non-covered one sets covered=False. Don't merge them.
      * the contractor/jurisdiction table — policy id → MAC jurisdiction → states
      * the NCD table, which has a different shape from LCDs. Handle it separately;
        NCDs are national so jurisdiction is None.

    Returns (n_policies, n_codes).
    """
    raise NotImplementedError(
        "See the project docs Step 1.3. Run `cli inspect` first, then implement "
        "against the real column names — do not guess them."
    )


def policy_stats() -> dict[str, int]:
    with db.connect() as conn:
        if "policies" not in db.table_names(conn):
            return {"policies": 0, "with_coverage_text": 0, "codes": 0}
        return {
            "policies": db.row_count(conn, "policies"),
            "with_coverage_text": conn.execute(
                "SELECT COUNT(*) AS n FROM policies WHERE length(trim(coverage_text)) > 100"
            ).fetchone()["n"],
            "codes": db.row_count(conn, "policy_codes"),
        }
