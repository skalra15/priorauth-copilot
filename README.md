# PriorAuth Copilot

An open, benchmarked agent that decides whether a clinical case meets Medicare coverage criteria — and drafts a citation-backed appeal when it doesn't.

Give it a procedure code, a diagnosis code, a jurisdiction, and a clinical note. It retrieves the governing Local or National Coverage Determination from the CMS Medicare Coverage Database, extracts that policy's prose into structured testable criteria, checks the note against each criterion with evidence spans, and returns a decision plus an appeal draft.

**Why this exists.** CMS-0057-F went operational on 1 January 2026. Payers must now issue prior authorization decisions in 72 hours (urgent) or 7 days (standard), give specific denial reasons, and — as of 31 March 2026 — publicly report their approval, denial, and appeal-overturn rates. Denial rates across those first disclosures range from under 2% to over 27%. Commercial vendors sell closed-box appeal automation into this gap. There is no open, measured implementation. This is one.

**Why the eval matters more than the demo.** Building a RAG pipeline over coverage policies is a weekend. Knowing whether it is *right* — and publishing the rate at which it invents citations — is the actual work. Every metric in this repo is reported on a hand-labeled golden set, including the failure modes.

---

## Status

🚧 In development. complete.


|---|---|---|

| 1 | CMS LCD/NCD ingestion | ⬜ |
| 2 | Criteria extractor (go/no-go gate) | ⬜ |
| 3 | Hybrid policy retrieval | ⬜ |
| 4 | Checker agent + appeal drafter | ⬜ |
| 5 | Eval harness + golden set | ⬜ |
| 6 | Demo UI | ⬜ |
| 7 | Public writeup | ⬜ |

## Results

<!-- Populated at . Do not delete this section — it is the point of the project. -->

| Metric | Value | n |
|---|---|---|
| Criteria extraction precision | — | — |
| Criteria extraction recall | — | — |
| Hallucinated citation rate | — | — |
| Retrieval recall@5 | — | — |
| End-to-end verdict accuracy | — | — |

---

## Quickstart

```bash
git clone <your-repo-url>
cd priorauth-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then add your ANTHROPIC_API_KEY
pytest                       # 7 tests, all green

# Download CMS coverage data (see the project docs Step 1.1 — requires accepting a license)
python -m priorauth.cli ingest --source data/raw

# Inspect what landed
python -m priorauth.cli inspect
```

New to the project? Start with **[the project docs](the project docs)** — the literal,
command-by-command walkthrough for Days 1 and 2. Then move to
**[the project docs](the project docs)** for the seven phases and their gates.

## Architecture

```
CPT + ICD-10 + jurisdiction + clinical note
            │
            ▼
   ┌─────────────────┐
   │ Retrieval       │  deterministic code-table lookup
   │                 │  + semantic fallback over policy text
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Criteria        │  policy prose → structured JSON criteria
   │ Extractor       │  (cached; each criterion keeps a source span)
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Checker Agent   │  per-criterion verdict + evidence span from note
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Decision +      │  approve / deny / insufficient evidence
   │ Appeal Drafter  │  + appeal letter citing the exact unmet criterion
   └─────────────────┘
            │
            ▼
      Eval harness  ← measures every stage above against a golden set
```

## Data sources

- **CMS Medicare Coverage Database** — bulk LCD, NCD, and Article downloads (CSV + Access, with data dictionaries). ~300 active NCDs, 1,500+ active LCDs. Requires accepting ADA/AMA/NUBC license terms at download time.
- **CMS DE-SynPUF** — free synthetic Medicare claims (5% sample, 2008–2010, inpatient/outpatient/carrier/PDE). Used for claim-shaped inputs. Synthetic and dated; this is disclosed, not hidden.
- Clinical notes are LLM-synthesized against the retrieved policy. No real PHI touches this repo, ever.

## Disclaimer

Research and portfolio project. Not a medical device, not clinical decision support, not for use in real coverage or care decisions.

## License

MIT for the code. CMS coverage data is subject to its own license terms — see `data/raw/README_LICENSE.md` after download. Do not commit the raw CMS files.
