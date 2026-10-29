"""Tests for the database keep-alive loop in api.py.

Supabase's free tier pauses after a week without database activity, which
took the live demo down twice. These cover the three things the keep-alive
has to get right: the ping runs a real query, one failed ping doesn't stop
the loop, and the loop only starts when a Postgres URL is configured.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from priorauth import api, config, db


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO policies
               (policy_id, policy_type, title, jurisdiction, states, coverage_text)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("L1", "LCD", "Title", None, json.dumps([]), "coverage text"),
        )
    return tmp_path


def test_ping_runs_a_real_query(seeded_db):
    api._ping_database()


def test_failed_ping_does_not_stop_the_loop(monkeypatch):
    def failing_ping():
        raise RuntimeError("database unreachable")

    async def stop_at_sleep(_seconds):
        # Reaching the sleep means the failure was caught and the loop
        # carried on. Cancel here so the test doesn't wait 12 hours.
        raise asyncio.CancelledError

    monkeypatch.setattr(api, "_ping_database", failing_ping)
    monkeypatch.setattr(api.asyncio, "sleep", stop_at_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(api._keep_database_awake())


def _run_lifespan_and_report_started(monkeypatch) -> bool:
    started = False

    async def fake_loop():
        nonlocal started
        started = True
        await asyncio.Event().wait()

    monkeypatch.setattr(api, "_keep_database_awake", fake_loop)

    async def run():
        async with api.lifespan(api.app):
            await asyncio.sleep(0)

    asyncio.run(run())
    return started


def test_loop_starts_when_postgres_is_configured(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://example")
    assert _run_lifespan_and_report_started(monkeypatch)


def test_loop_does_not_start_on_local_sqlite(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    assert not _run_lifespan_and_report_started(monkeypatch)
