"""Central configuration. Everything reads paths and settings from here."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INDEX_DIR = DATA_DIR / "index"
DB_PATH = DATA_DIR / "priorauth.db"

EVAL_DIR = ROOT / "evals"
GOLDEN_DIR = EVAL_DIR / "golden"
RESULTS_DIR = EVAL_DIR / "results"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = os.getenv("PRIORAUTH_MODEL", "claude-sonnet-5")
CACHE_ENABLED = os.getenv("PRIORAUTH_CACHE", "1") == "1"

# Unset (default) -> SQLite at DB_PATH, canonical for local dev/ingest/eval.
# Set -> Postgres (prod only, e.g. Supabase). See db.py's module docstring --
# ingest.normalize() never runs against this; it's populated by
# scripts/migrate_to_postgres.py from the local SQLite file instead.
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Local, free, no API cost — semantic fallback for retrieval ().
EMBEDDING_MODEL = os.getenv("PRIORAUTH_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Models swept in the cost/accuracy comparison.
SWEEP_MODELS = ["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"]

for _d in (DATA_DIR, RAW_DIR, INDEX_DIR, GOLDEN_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def require_api_key() -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return ANTHROPIC_API_KEY
