# PriorAuth Copilot

An open, benchmarked agent that checks whether a clinical case meets Medicare coverage criteria and drafts a citation-backed appeal when it doesn't.

Give it a procedure code, a diagnosis code, a state, and a clinical note. It retrieves the governing Local or National Coverage Determination from the CMS Medicare Coverage Database, extracts that policy's prose into structured testable criteria, checks the note against each criterion with an evidence span, and returns a decision plus an appeal draft. Every citation is a verbatim, programmatically verified quote, never a paraphrase.

**Live demo:** [priorauth-copilot-zeta.vercel.app](https://priorauth-copilot-zeta.vercel.app)

**Why this exists.** CMS-0057-F went operational on 1 January 2026. Payers must now issue prior authorization decisions in 72 hours for urgent requests or 7 days for standard ones, give specific denial reasons, and starting 31 March 2026 publicly report their approval, denial, and appeal-overturn rates. Denial rates across those first disclosures range from under 2% to over 27%. Commercial vendors sell closed-box appeal automation into this gap. This project is an open, measured alternative.

**Why the eval matters.** This is a RAG pipeline over Medicare coverage policies. Every metric below is measured against a golden set labeled to a rubric defined up front, including the failure modes, not just the cases where extraction and retrieval succeeded. That includes the rate at which the pipeline invents citations, reported directly instead of glossed over.

---

## Results

Full model sweep against the golden set: 20 labeled policies for extraction, 50 combined-query plus 30 NCD-only retrieval queries, and 30 synthetic notes (10 policies × 3 variants: meets all / fails one / ambiguous one) for the checker and appeal drafter. Reproduce with `python -m priorauth.cli eval --full --sweep`.

| Model | Extraction P / R | Hallucination rate | Retrieval R@1 / R@5 | Verdict accuracy | Correct abstention | Cost (full sweep) |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | 79.8% / 94.0% | **8.5%** | 72.0% / 100.0% | 70.5% | 47.2% | $0.30 |
| Claude Sonnet 5 | 88.1% / 88.5% | **0.0%** | 72.0% / 100.0% | 86.8% | 63.9% | $0.68 |
| Claude Opus 5 | 67.5% / 96.7% | **0.0%** | 72.0% / 100.0% | 67.4% | 44.4% | $1.96 |

**Hallucination rate is the headline number**: the fraction of extracted policy citations that are not a verbatim substring of the source policy text, checked programmatically (`verify.span_is_grounded`), never eyeballed. Sonnet and Opus hit zero on this golden set. Haiku doesn't. The same grounding check runs on note-evidence citations in the checker stage. A check during development found 3 of 219 evidence spans were paraphrased rather than verbatim, and the system now downgrades those to an explicit abstention instead of showing a fabricated quote.

One thing worth explaining in the extraction row: Opus has the highest recall but the lowest precision, which looks backward at first. Opus and Haiku both extract background and definitional sentences as their own criteria more readily than Sonnet does, which inflates apparent false positives on a metric that scores extraction structure rather than extraction correctness.

## Quickstart

```bash
git clone <your-repo-url>
cd priorauth-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,retrieval,ui]"
cp .env.example .env        # then add your ANTHROPIC_API_KEY
pytest

# Download CMS coverage data from the Medicare Coverage Database (requires accepting a license)
python -m priorauth.cli ingest --source data/raw --normalize

# Inspect what landed
python -m priorauth.cli stats
```

### Running the live demo locally

```bash
# Backend (FastAPI), from the repo root
uvicorn priorauth.api:app --app-dir src --reload --port 8000

# Frontend (Next.js), in another terminal
cd web && npm install && npm run dev
```

Open `http://localhost:3000`.

## Architecture

```
CPT/HCPCS + ICD-10 + state + clinical note
            │
            ▼
   ┌─────────────────┐
   │ Retrieve        │  deterministic code-table lookup
   │                 │  + local semantic fallback (sentence-transformers)
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Extract         │  policy prose → structured criteria
   │                 │  every source_span verified verbatim in the policy
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Check           │  per-criterion verdict + evidence span from the note
   │                 │  insufficient_evidence is a first-class verdict
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Decide          │  approve / deny / needs human review,
   │                 │  aggregated deterministically in code, not by the model
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Appeal          │  model writes the narrative; every citation is the
   │                 │  already-verified source_span, never generated text
   └─────────────────┘
            │
            ▼
      Eval harness  ← measures every stage above against the golden set
```

**Deployment:** Next.js frontend (Vercel) → FastAPI backend (Render) → Postgres (Supabase). SQLite is canonical for local dev, ingestion, and the eval harness; `db.py` switches to Postgres in production via a `DATABASE_URL` env var, with the exact same query interface on both backends.

## Data sources

- **CMS Medicare Coverage Database**: bulk LCD, NCD, and Article downloads (CSV, with data dictionaries). 1,301 active policies ingested (947 LCDs, 354 NCDs) after filtering out policies with insufficient coverage text. Requires accepting ADA/AMA/NUBC license terms at download time.
- Clinical notes are LLM-synthesized against the actual retrieved policy criteria, with the generating model self-reporting which criteria its own note addresses. That self-report is used as ground truth for the checker eval, not assumed independently. Synthetic throughout, no real PHI touches this repo.

## Honest limitations

- **Nested boolean logic, temporal qualifiers, and exclusions phrased as coverage** ("not covered unless...") are the hardest extraction cases, and where most of the extraction error concentrates.
- **Retrieval recall@1 is 72%, not 100%.** Deterministic code and state lookup doesn't always rank the correct policy first when a code is shared across many policies. Recall@5 is 100% on this query set, so the correct policy is essentially always found, just not always ranked first.
- **Correct-abstention rate is 44 to 64%, not near 100%.** The checker's `insufficient_evidence` verdict doesn't perfectly align with the cases that actually warrant abstention. Abstaining correctly is arguably the most safety-relevant metric in this project, and it's the one solved the least.
- **The clinical notes are synthetic, not real patient notes.** Ground truth comes from the note-generating model's own self-report rather than an independent clinician review, so this measures internal consistency more than real-world clinical accuracy.
- **Medicare only.** Commercial payer policies have different structures and aren't covered by this pipeline as built.
- **No clinician in the loop.** This is a research and portfolio artifact, not a validated clinical tool. See the disclaimer below.

## Disclaimer

This is a research and portfolio project. It is not a medical device or clinical decision support tool, and it isn't intended for real coverage or care decisions.

## License

MIT for the code (see `LICENSE`). CMS coverage data is subject to its own license terms, see `data/raw/README_LICENSE.md` after download. Do not commit the raw CMS files.
