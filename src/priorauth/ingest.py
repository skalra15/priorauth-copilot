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


_BLOCK_TAGS = ["p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6"]


def strip_html(raw: str | None) -> str:
    """CMS ships coverage text as HTML. The extractor needs clean prose.

    Only break lines at block-level tags. get_text(separator="\\n") breaks at
    EVERY tag boundary, including inline formatting — CMS policy text is full
    of <sub>/<sup>/<strong> mid-sentence (e.g. "Vitamin B<sub>12</sub>"), which
    would otherwise fragment into "Vitamin B", "12", "Injections" on separate
    lines and break every source_span that quotes across one."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = soup.get_text()
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def strip_html_inline(raw: str | None) -> str:
    """Same as strip_html but collapses to one line — for titles, not body text."""
    if not raw:
        return ""
    text = BeautifulSoup(raw, "lxml").get_text(separator=" ")
    return " ".join(text.split())


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


def _date(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw[:10]


def _coverage_text(row: sqlite3.Row) -> str:
    """LCDs split 'Coverage Indications, Limitations, and/or Medical Necessity'
    across several fields instead of one HTML blob. Concatenate the ones that
    actually carry coverage criteria; skip evidentiary background fields."""
    sections = [
        ("Coverage Indications", row["indication"]),
        ("ICD-10 Diagnoses That Support Medical Necessity", row["diagnoses_support"]),
        ("ICD-10 Diagnoses That Do Not Support Medical Necessity", row["diagnoses_dont_support"]),
        ("Coding Guidelines", row["coding_guidelines"]),
        ("Documentation Requirements", row["doc_reqs"]),
        ("Associated Information", row["associated_info"]),
    ]
    parts = []
    for label, html in sections:
        text = strip_html(html)
        if text:
            parts.append(f"== {label} ==\n{text}")
    return "\n\n".join(parts)


def normalize() -> tuple[int, int]:
    """Map raw CMS tables onto `policies` and `policy_codes`.

    Real schema notes (differs from the generic description in the project docs):
      * LCDs don't have one HTML coverage blob — it's split across `indication`,
        `diagnoses_support(_dont_support)`, `coding_guidelines`, `doc_reqs`,
        `associated_info`. See `_coverage_text()`.
      * CPT/HCPCS and ICD-10 code tables live on *Articles*, not LCDs (except DME
        LCDs, which keep a direct `lcd_x_hcpc_code` table). Articles link back to
        their LCD via `article_related_documents.r_lcd_id`. Articles with no
        linked LCD carry no policy to attach codes to and are skipped.
      * MAC jurisdiction code comes from lcd_id -> lcd_x_contractor -> contractor
        -> dmerc_rgn -> dmerc_region_lookup.mac_description (e.g. "J-A").
      * States come from lcd_x_primary_jurisdiction -> state_lookup.
      * NCDs (raw_ncd_trkg) have a different shape entirely: no code tables in
        this download, jurisdiction is always None (national), and coverage text
        is `itm_srvc_desc` + `indctn_lmtn`.

    Returns (n_policies, n_codes).
    """
    with db.connect() as conn:
        if "raw_lcd" not in db.table_names(conn):
            raise RuntimeError("No raw tables found. Run `cli ingest` first.")

        db.init_db()

        state_abbrev = {
            r["state_id"]: r["state_abbrev"]
            for r in conn.execute("SELECT state_id, state_abbrev FROM raw_state_lookup")
        }
        mac_by_region = {
            r["region_id"]: r["mac_description"]
            for r in conn.execute("SELECT region_id, mac_description FROM raw_dmerc_region_lookup")
        }
        mac_by_contractor = {
            r["contractor_id"]: mac_by_region.get(r["dmerc_rgn"])
            for r in conn.execute("SELECT contractor_id, dmerc_rgn FROM raw_contractor")
        }

        lcd_states: dict[str, set[str]] = {}
        for r in conn.execute("SELECT lcd_id, state_id FROM raw_lcd_x_primary_jurisdiction"):
            abbrev = state_abbrev.get(r["state_id"])
            if abbrev:
                lcd_states.setdefault(r["lcd_id"], set()).add(abbrev)

        lcd_jurisdictions: dict[str, set[str]] = {}
        for r in conn.execute("SELECT lcd_id, contractor_id FROM raw_lcd_x_contractor"):
            mac = mac_by_contractor.get(r["contractor_id"])
            if mac:
                lcd_jurisdictions.setdefault(r["lcd_id"], set()).add(mac)

        article_to_lcds: dict[str, set[str]] = {}
        skipped_articles_no_lcd = 0
        seen_articles = set()
        for r in conn.execute(
            "SELECT article_id, r_lcd_id FROM raw_article_related_documents WHERE r_lcd_id IS NOT NULL AND r_lcd_id != ''"
        ):
            article_to_lcds.setdefault(r["article_id"], set()).add(r["r_lcd_id"])
        for r in conn.execute("SELECT DISTINCT article_id FROM raw_article"):
            seen_articles.add(r["article_id"])
        skipped_articles_no_lcd = len(seen_articles - article_to_lcds.keys())

        n_policies = 0
        n_skipped_short = 0
        codes: list[tuple[str, str, str, int]] = []

        for row in conn.execute("SELECT * FROM raw_lcd"):
            lcd_id = row["lcd_id"]
            policy_id = f"L{lcd_id}"
            coverage_text = _coverage_text(row)
            if len(coverage_text.strip()) < 100:
                n_skipped_short += 1
                continue

            jurisdictions = lcd_jurisdictions.get(lcd_id, set())
            db.upsert_policy(
                conn,
                {
                    "policy_id": policy_id,
                    "policy_type": "LCD",
                    "title": strip_html_inline(row["title"]) or row["title"],
                    "jurisdiction": "; ".join(sorted(jurisdictions)) or None,
                    "states": sorted(lcd_states.get(lcd_id, set())),
                    "effective_date": _date(row["rev_eff_date"] or row["orig_det_eff_date"]),
                    "retired_date": _date(row["date_retired"]),
                    "coverage_text": coverage_text,
                    "source_url": None,
                },
            )
            n_policies += 1

            for r in conn.execute(
                "SELECT hcpc_code_id FROM raw_lcd_x_hcpc_code WHERE lcd_id = ?", (lcd_id,)
            ):
                if r["hcpc_code_id"]:
                    codes.append((policy_id, r["hcpc_code_id"], "HCPCS", 1))

        for article_id, lcd_ids in article_to_lcds.items():
            policy_ids = [f"L{lid}" for lid in lcd_ids]
            for r in conn.execute(
                "SELECT hcpc_code_id FROM raw_article_x_hcpc_code WHERE article_id = ?", (article_id,)
            ):
                if r["hcpc_code_id"]:
                    for pid in policy_ids:
                        codes.append((pid, r["hcpc_code_id"], "HCPCS", 1))
            for r in conn.execute(
                "SELECT icd10_code_id FROM raw_article_x_icd10_covered WHERE article_id = ?", (article_id,)
            ):
                if r["icd10_code_id"]:
                    for pid in policy_ids:
                        codes.append((pid, r["icd10_code_id"], "ICD10", 1))
            for r in conn.execute(
                "SELECT icd10_code_id FROM raw_article_x_icd10_noncovered WHERE article_id = ?", (article_id,)
            ):
                if r["icd10_code_id"]:
                    for pid in policy_ids:
                        codes.append((pid, r["icd10_code_id"], "ICD10", 0))

        for row in conn.execute("SELECT * FROM raw_ncd_trkg"):
            sect = row["ncd_mnl_sect"]
            if not sect:
                continue
            policy_id = f"NCD-{sect}"
            coverage_text = "\n\n".join(
                strip_html(t) for t in (row["itm_srvc_desc"], row["indctn_lmtn"]) if strip_html(t)
            )
            if len(coverage_text.strip()) < 100:
                n_skipped_short += 1
                continue

            db.upsert_policy(
                conn,
                {
                    "policy_id": policy_id,
                    "policy_type": "NCD",
                    "title": strip_html_inline(row["ncd_mnl_sect_title"]) or row["ncd_mnl_sect_title"],
                    "jurisdiction": None,
                    "states": [],
                    "effective_date": _date(row["ncd_efctv_dt"]),
                    "retired_date": _date(row["ncd_trmntn_dt"]),
                    "coverage_text": coverage_text,
                    "source_url": None,
                },
            )
            n_policies += 1

        conn.executemany(
            """
            INSERT OR IGNORE INTO policy_codes (policy_id, code, code_system, covered)
            VALUES (?, ?, ?, ?)
            """,
            codes,
        )
        n_codes = len(codes)

    print(
        f"Skipped {n_skipped_short} policies with <100 chars of coverage text; "
        f"{skipped_articles_no_lcd} articles had no linked LCD and were not used for codes."
    )
    return n_policies, n_codes


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
