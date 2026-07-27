"""FastAPI wrapper around the retrieve -> extract -> check -> appeal pipeline.

Deployment layer only. This is a thin HTTP layer -- it orchestrates the same
functions the CLI and eval harness call, it doesn't reimplement any of the
correctness-critical logic. Runs on Render, SQLite stays canonical, the
Next.js frontend on Vercel is the only caller in practice but CORS is left
open since this is a read-only demo API with no auth and no PHI (synthetic
notes only).
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import appeal, check, config, db, extract, retrieve
from .appeal import AppealSection
from .schemas import Criterion, CoverageDecision

app = FastAPI(title="PriorAuth Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CheckRequest(BaseModel):
    cpt: str | None = None
    icd10: str | None = None
    state: str | None = None
    note_text: str


class PolicySummary(BaseModel):
    policy_id: str
    title: str
    policy_type: str
    jurisdiction: str | None
    source_url: str | None


class CodeSuggestion(BaseModel):
    code: str
    description: str | None


class CheckResponse(BaseModel):
    policy: PolicySummary
    criteria: list[Criterion]
    decision: CoverageDecision
    appeal_text: str | None = None
    appeal_sections: list[AppealSection] | None = None
    appeal_closing: str | None = None
    appeal_error: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/codes", response_model=list[CodeSuggestion])
def codes_endpoint(
    system: Literal["HCPCS", "ICD10"],
    q: str = Query("", max_length=64),
    limit: int = Query(15, ge=1, le=50),
) -> list[CodeSuggestion]:
    return [CodeSuggestion(**c) for c in retrieve.search_codes(system, q, limit=limit)]


@app.post("/api/check", response_model=CheckResponse)
def check_endpoint(req: CheckRequest) -> CheckResponse:
    if not req.cpt and not req.icd10:
        raise HTTPException(400, "Provide at least one of cpt or icd10")

    retrieval = retrieve.retrieve(cpt=req.cpt, icd10=req.icd10, state=req.state, top_k=1)
    if not retrieval["results"]:
        raise HTTPException(
            404,
            f"No matching policy found for cpt={req.cpt!r} icd10={req.icd10!r} state={req.state!r}",
        )

    policy_id = retrieval["results"][0]["policy_id"]
    p = db.get_policy(policy_id)
    if not p:
        raise HTTPException(404, f"Policy {policy_id} was retrieved but not found in the database")

    predicted, _ = extract.extract_criteria(policy_id, p["title"], p["coverage_text"], model=config.MODEL)
    decision, _ = check.check_note(policy_id, predicted.criteria, req.note_text, model=config.MODEL)

    appeal_text = None
    appeal_sections = None
    appeal_closing = None
    appeal_error = None
    if decision.decision == "likely_deny":
        try:
            appeal_text, appeal_sections, appeal_closing, _ = appeal.draft_appeal(
                policy_id, p["title"], p["coverage_text"], predicted.criteria, decision, model=config.MODEL
            )
        except Exception as exc:  # surfaced to the UI, not swallowed
            appeal_error = str(exc)

    return CheckResponse(
        policy=PolicySummary(
            policy_id=policy_id,
            title=p["title"],
            policy_type=p["policy_type"],
            jurisdiction=p["jurisdiction"],
            source_url=p["source_url"],
        ),
        criteria=predicted.criteria,
        decision=decision,
        appeal_text=appeal_text,
        appeal_sections=appeal_sections,
        appeal_closing=appeal_closing,
        appeal_error=appeal_error,
    )
