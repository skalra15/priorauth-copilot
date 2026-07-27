"""Tests for the deterministic retrieval ranking -- the path that resolves
most real queries with no model call involved at all. Uses a throwaway
SQLite file per test, not the project's real data.db.
"""

from __future__ import annotations

import json

import pytest

from priorauth import config, db, retrieve


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    db.init_db()

    def add_policy(policy_id, policy_type, states, codes):
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO policies
                   (policy_id, policy_type, title, jurisdiction, states, coverage_text)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (policy_id, policy_type, f"Title for {policy_id}", None, json.dumps(states), "coverage text"),
            )
            for code, system in codes:
                conn.execute(
                    "INSERT INTO policy_codes (policy_id, code, code_system, covered) VALUES (?, ?, ?, 1)",
                    (policy_id, code, system),
                )
            conn.commit()

    # Same CPT code shared across three policies with different jurisdiction
    # fit -- this is exactly the ambiguity lookup_by_code's ranking exists for.
    add_policy("L-STATE-MATCH", "LCD", ["CA", "NV"], [("86003", "HCPCS")])
    add_policy("N-NATIONAL", "NCD", [], [("86003", "HCPCS")])
    add_policy("L-OTHER-STATE", "LCD", ["NY"], [("86003", "HCPCS")])

    # A separate code pair, isolated from the 86003 policies above, so the
    # combined-lookup test doesn't perturb the single-code ranking tests.
    add_policy("L-BOTH-CODES", "LCD", ["CA"], [("99213", "HCPCS"), ("J30.0", "ICD10")])
    add_policy("L-SINGLE-CODE-ONLY", "LCD", ["NY"], [("99213", "HCPCS")])

    return tmp_path


def test_lookup_by_code_ranks_exact_state_match_first(seeded_db):
    results = retrieve.lookup_by_code("86003", "HCPCS", state="CA")
    ids = [r["policy_id"] for r in results]
    assert ids[0] == "L-STATE-MATCH"


def test_lookup_by_code_ranks_ncd_above_unrelated_state(seeded_db):
    # No state given -- NCD (national) should outrank an LCD tied to a
    # different, non-matching state.
    results = retrieve.lookup_by_code("86003", "HCPCS", state=None)
    ids = [r["policy_id"] for r in results]
    assert ids[0] == "N-NATIONAL"


def test_lookup_by_code_state_mismatch_ranks_lowest(seeded_db):
    results = retrieve.lookup_by_code("86003", "HCPCS", state="TX")
    ids = [r["policy_id"] for r in results]
    # A policy scoped to states that don't include the query state should
    # never outrank the NCD (always-in-scope) or an unscoped policy.
    assert ids.index("L-OTHER-STATE") > ids.index("N-NATIONAL")


def test_retrieve_boosts_policy_matching_both_codes(seeded_db):
    # L-BOTH-CODES matches on both cpt and icd10; L-SINGLE-CODE-ONLY only
    # matches on cpt but is scoped to the query's own state. The combined
    # match should still win -- an AND-match is a stronger signal than a
    # single-code match with a better jurisdiction fit.
    result = retrieve.retrieve(cpt="99213", icd10="J30.0", state="NY", top_k=5)
    assert result["method"] == "deterministic"
    assert result["results"][0]["policy_id"] == "L-BOTH-CODES"


def test_retrieve_falls_back_to_none_with_no_match_and_no_query_text(seeded_db):
    result = retrieve.retrieve(cpt="00000", icd10=None, state=None, top_k=5)
    assert result["method"] == "none"
    assert result["results"] == []
