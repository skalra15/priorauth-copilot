"""Command line entrypoint: `python -m priorauth.cli <command>`."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import appeal, check, config, db, extract, ingest, retrieve, synth, verify
from .schemas import CoverageDecision, ExtractedCriteria

app = typer.Typer(add_completion=False, help="PriorAuth Copilot")
console = Console()


@app.command()
def init() -> None:
    """Create the SQLite schema."""
    db.init_db()
    console.print(f"[green]✓[/green] database ready at {config.DB_PATH}")


@app.command("ingest")
def ingest_cmd(
    source: Path = typer.Option(config.RAW_DIR, help="Directory of unzipped CMS CSVs"),
    normalize: bool = typer.Option(
        False, "--normalize", help="Also run stage 2 (implement it first)"
    ),
) -> None:
    """Stage 1: load every CMS CSV into SQLite verbatim."""
    try:
        loaded = ingest.load_raw(source)
    except FileNotFoundError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    table = Table("raw table", "rows")
    for name, count in sorted(loaded.items()):
        table.add_row(name, f"{count:,}")
    console.print(table)
    console.print(
        "\n[bold]Next:[/bold] run [cyan]inspect[/cyan] and read the real schema "
        "before implementing normalize() — see the project docs Step 1.3."
    )
    if normalize:
        n_pol, n_codes = ingest.normalize()
        console.print(f"[green]✓[/green] {n_pol:,} policies, {n_codes:,} code links")


@app.command()
def inspect(
    table_filter: str = typer.Option("", help="Only show tables containing this string"),
) -> None:
    """Print schema, row counts, and one sample row per raw table."""
    described = ingest.describe_raw()
    if not described:
        console.print("[yellow]No raw tables. Run `ingest` first.[/yellow]")
        raise typer.Exit(1)

    for name, info in sorted(described.items()):
        if table_filter and table_filter not in name:
            continue
        console.rule(f"[bold cyan]{name}[/bold cyan]  ({info['rows']:,} rows)")
        console.print("columns: " + ", ".join(info["columns"]))
        for key, value in info["sample"].items():
            preview = (value or "")[:160].replace("\n", " ")
            suffix = "…" if value and len(value) > 160 else ""
            console.print(f"  [dim]{key}[/dim] = {preview}{suffix}")


@app.command()
def stats() -> None:
    """check: how much normalized policy data do we actually have?"""
    s = ingest.policy_stats()
    table = Table("metric", "value")
    for key, value in s.items():
        table.add_row(key, f"{value:,}")
    console.print(table)
    if s["with_coverage_text"] >= 1000:
        console.print("[green]✓ .[/green]")
    else:
        console.print(
            "[yellow]yet — need ≥1,000 policies with "
            "coverage_text.[/yellow]"
        )


@app.command()
def policy(policy_id: str) -> None:
    """Print one normalized policy — use this to eyeball text quality."""
    p = db.get_policy(policy_id)
    if not p:
        console.print(f"[red]No policy {policy_id}[/red]")
        raise typer.Exit(1)
    console.rule(f"[bold]{p['policy_id']} — {p['title']}[/bold]")
    console.print(p["coverage_text"])


@app.command("extract")
def extract_cmd(
    policy_id: str,
    model: str = typer.Option(config.MODEL, help="Model to use for extraction"),
    force: bool = typer.Option(False, "--force", help="Bypass the extraction cache"),
) -> None:
    """Extract criteria for one policy and report the grounding check."""
    p = db.get_policy(policy_id)
    if not p:
        console.print(f"[red]No policy {policy_id}[/red]")
        raise typer.Exit(1)

    parsed, response = extract.extract_criteria(
        policy_id, p["title"], p["coverage_text"], model=model, force=force
    )

    table = Table("id", "type", "logic", "temporal", "text")
    for c in parsed.criteria:
        table.add_row(c.id, c.type.value, c.logic.value, c.temporal or "", c.text)
    console.print(table)

    spans = [c.source_span for c in parsed.criteria]
    report = verify.grounding_report(spans, p["coverage_text"])
    console.print(
        f"\ngrounded {report['grounded']}/{report['n']} "
        f"(hallucination rate {report['hallucination_rate']:.1%})"
        + ("  [dim](cached)[/dim]" if response.cached else "")
    )
    for span in verify.ungrounded_spans(spans, p["coverage_text"]):
        console.print(f"  [red]ungrounded:[/red] {span!r}")

    if parsed.notes:
        console.print(f"\n[dim]notes: {parsed.notes}[/dim]")


@app.command("eval-extraction")
def eval_extraction_cmd(
    model: str = typer.Option(config.MODEL, help="Model to use for extraction"),
    golden_dir: Path = typer.Option(config.GOLDEN_DIR / "criteria", help="Hand-labeled golden files"),
) -> None:
    """: precision/recall/hallucination-rate against your hand labels."""
    files = sorted(golden_dir.glob("*.json"))
    if not files:
        console.print(f"[yellow]No golden files in {golden_dir}[/yellow]")
        raise typer.Exit(1)

    table = Table("policy_id", "gold", "pred", "matched", "precision", "recall", "type agree", "grounded")
    total_gold = total_pred = total_matched = 0
    total_type_matched = total_type_agree = 0
    all_type_disagreements: list[tuple[str, dict]] = []
    all_spans: list[str | None] = []
    all_sources: list[str] = []
    n_unlabeled = 0
    failed: list[tuple[str, str]] = []

    for path in files:
        raw = json.loads(path.read_text())
        if not raw.get("criteria"):
            n_unlabeled += 1
            continue

        policy_id = raw["policy_id"]
        p = db.get_policy(policy_id)
        if not p:
            console.print(f"[red]{policy_id}: not found in policies table, skipping[/red]")
            continue

        gold = ExtractedCriteria.model_validate({k: v for k, v in raw.items() if not k.startswith("_")})
        try:
            predicted, _ = extract.extract_criteria(policy_id, p["title"], p["coverage_text"], model=model)
        except Exception as exc:
            # Visible in the report, not swallowed — a malformed extraction is a
            # real data point (see the project docs: failures should show up in the eval).
            failed.append((policy_id, str(exc)))
            table.add_row(policy_id, str(len(gold.criteria)), "FAILED", "-", "-", "-", "-", "-")
            continue

        result = extract.score_extraction(gold, predicted)
        total_gold += result["n_gold"]
        total_pred += result["n_predicted"]
        total_matched += result["n_matched"]
        total_type_matched += result["n_matched"]
        total_type_agree += result["type_agree_count"]
        all_type_disagreements.extend((policy_id, d) for d in result["type_disagreements"])

        spans = [c.source_span for c in predicted.criteria]
        all_spans.extend(spans)
        all_sources.extend([p["coverage_text"]] * len(spans))
        grounded = verify.grounding_report(spans, p["coverage_text"])

        table.add_row(
            policy_id,
            str(result["n_gold"]),
            str(result["n_predicted"]),
            str(result["n_matched"]),
            f"{result['precision']:.2f}",
            f"{result['recall']:.2f}",
            f"{result['type_agreement']:.2f}",
            f"{grounded['grounded']}/{grounded['n']}",
        )

    console.print(table)

    if n_unlabeled:
        console.print(f"[yellow]{n_unlabeled} golden file(s) still empty — not scored.[/yellow]")

    if failed:
        console.print(f"[red]{len(failed)} extraction(s) failed and were excluded from the totals below:[/red]")
        for policy_id, msg in failed:
            console.print(f"  [red]{policy_id}:[/red] {msg}")

    if total_pred == 0:
        console.print("[yellow]Nothing scored yet — label at least one golden file.[/yellow]")
        raise typer.Exit(1)

    precision = total_matched / total_pred
    recall = total_matched / total_gold if total_gold else 0.0
    hallucination = 1 - (
        sum(verify.span_is_grounded(s, src) for s, src in zip(all_spans, all_sources)) / len(all_spans)
        if all_spans
        else 0
    )
    type_agreement = total_type_agree / total_type_matched if total_type_matched else 0.0

    console.print(
        f"\n[bold]micro-averaged precision {precision:.2f} | recall {recall:.2f} | "
        f"hallucination rate {hallucination:.1%} | type agreement {type_agreement:.1%}[/bold]"
    )

    if precision > 0.80 and recall > 0.80 and hallucination < 0.05:
        console.print("[green]✓ — continue to .[/green]")
    elif precision >= 0.60 and recall >= 0.60 and hallucination < 0.10:
        console.print("[yellow]: fixable range — one more weekend of prompt tuning, then re-decide.[/yellow]")
    else:
        console.print(
            "[red]— per the project docs, stop and pivot to the "
            "CMS-0057-F Transparency Agent.[/red]"
        )

    # type_agreement isn't one of the project docs's thresholds, but a matched
    # span with the wrong type (e.g. exclusion mislabeled required) inverts the
    # actual coverage decision downstream -- too consequential to bury.
    if all_type_disagreements:
        console.print(
            f"\n[yellow]{len(all_type_disagreements)} matched criteria disagree on `type` "
            f"({type_agreement:.1%} agreement) -- span-matching alone can't see this:[/yellow]"
        )
        for policy_id, d in all_type_disagreements:
            console.print(
                f"  [yellow]{policy_id}:[/yellow] gold={d['gold_type']} predicted={d['predicted_type']} "
                f"— {d['text'][:80]!r}"
            )


@app.command()
def embed(model: str = typer.Option(config.EMBEDDING_MODEL, help="sentence-transformers model")) -> None:
    """Build the local semantic-search index over policy coverage_text."""
    n = retrieve.build_index(model)
    console.print(f"[green]✓[/green] embedded {n:,} policies -> {config.INDEX_DIR}")


@app.command("retrieve")
def retrieve_cmd(
    cpt: str = typer.Option(None, help="CPT/HCPCS code"),
    icd10: str = typer.Option(None, help="ICD-10 code"),
    state: str = typer.Option(None, help="2-letter state abbreviation"),
    query: str = typer.Option(None, "--query", help="Free-text query for semantic fallback"),
    top_k: int = typer.Option(5),
) -> None:
    """Look up candidate policies for a code/state, falling back to semantic search."""
    result = retrieve.retrieve(cpt=cpt, icd10=icd10, state=state, query_text=query, top_k=top_k)
    console.print(f"method: [bold]{result['method']}[/bold]")
    table = Table("policy_id", "score", "title")
    for r in result["results"]:
        table.add_row(r["policy_id"], f"{r['score']:.3f}", r.get("title", ""))
    console.print(table)


def _recall(hits_at_1: int, hits_at_5: int, n: int) -> tuple[float, float]:
    return (hits_at_1 / n if n else 0.0, hits_at_5 / n if n else 0.0)


@app.command("eval-retrieval")
def eval_retrieval_cmd(
    queries_path: Path = typer.Option(config.GOLDEN_DIR / "retrieval_queries.json"),
    ncd_queries_path: Path = typer.Option(config.GOLDEN_DIR / "retrieval_queries_ncd.json"),
) -> None:
    """: recall@1/@5, reported per scenario rather than one blended number.

    Three genuinely different situations, not one system: LCDs are code-indexed
    and the caller has both a procedure and a diagnosis code (the common case);
    LCDs where only one code is on hand; and NCDs, which this CMS download
    carries with zero CPT/HCPCS/ICD-10 linkage at all (only a coarse benefit-
    category classification) -- so NCDs are *only* ever reachable through the
    semantic path, structurally, not as a fallback of last resort.
    """
    if not queries_path.exists():
        console.print(f"[red]No query set at {queries_path}[/red]")
        raise typer.Exit(1)
    queries = json.loads(queries_path.read_text())
    n = len(queries)

    # Scenario 1: both codes + state — the query shape the project docs actually specifies.
    both_r1 = both_r5 = 0
    # Scenario 2: only one of the two codes — the weaker, still-realistic case.
    single_r1 = single_r5 = 0
    for q in queries:
        result = retrieve.retrieve(cpt=q["cpt"], icd10=q["icd10"], state=q["state"], top_k=5)
        ids = [r["policy_id"] for r in result["results"]]
        both_r1 += ids[:1] == [q["expected_policy_id"]]
        both_r5 += q["expected_policy_id"] in ids[:5]

        single_ids = [r["policy_id"] for r in retrieve.lookup_by_code(q["icd10"], "ICD10", q["state"])]
        single_r1 += single_ids[:1] == [q["expected_policy_id"]]
        single_r5 += q["expected_policy_id"] in single_ids[:5]

    both_recall = _recall(both_r1, both_r5, n)
    single_recall = _recall(single_r1, single_r5, n)

    # Scenario 3: NCDs — semantic-only by construction, not a fallback test.
    ncd_recall = None
    if ncd_queries_path.exists():
        ncd_queries = json.loads(ncd_queries_path.read_text())
        ncd_r1 = ncd_r5 = 0
        for q in ncd_queries:
            ids = [pid for pid, _ in retrieve.semantic_search(q["expected_title"], top_k=5)]
            ncd_r1 += ids[:1] == [q["expected_policy_id"]]
            ncd_r5 += q["expected_policy_id"] in ids[:5]
        ncd_recall = _recall(ncd_r1, ncd_r5, len(ncd_queries))

    table = Table("scenario", "n", "recall@1", "recall@5")
    table.add_row("LCD, both CPT+ICD10+state (typical case)", str(n), f"{both_recall[0]:.2f}", f"{both_recall[1]:.2f}")
    table.add_row("LCD, single code only (weaker case)", str(n), f"{single_recall[0]:.2f}", f"{single_recall[1]:.2f}")
    if ncd_recall:
        table.add_row("NCD, semantic-only (no codes exist)", str(len(ncd_queries)), f"{ncd_recall[0]:.2f}", f"{ncd_recall[1]:.2f}")
    console.print(table)

    console.print(
        "\n[dim]354 of 1,301 policies are NCDs. This CMS download carries zero CPT/HCPCS/"
        "ICD-10 codes for any of them (only a coarse benefit-category classification) -- "
        "NCDs are reachable only through semantic search, not as a last-resort fallback.[/dim]"
    )

    if both_recall[1] > 0.90:
        console.print(f"\n[green]✓ [/green] (LCD combined-code recall@5 = {both_recall[1]:.2f})")
    else:
        console.print(f"\n[red][/red] (LCD combined-code recall@5 = {both_recall[1]:.2f}, need > 0.90)")


DEFAULT_NOTE_POLICIES = [
    "L33591", "L33922", "L33967", "L34056", "L34064",
    "L34565", "L35222", "L36000", "L38303", "L39849",
]


@app.command("synthesize-notes")
def synthesize_notes_cmd(
    policy_id: list[str] = typer.Option(None, help="Specific policy IDs; defaults to a fixed set of 10"),
    notes_dir: Path = typer.Option(config.GOLDEN_DIR / "notes"),
    model: str = typer.Option(config.MODEL),
) -> None:
    """synthesize meets_all/fails_one/ambiguous_one notes per policy."""
    import random

    ids = policy_id or DEFAULT_NOTE_POLICIES
    notes_dir.mkdir(parents=True, exist_ok=True)
    n_written = 0

    for pid in ids:
        p = db.get_policy(pid)
        if not p:
            console.print(f"[red]{pid}: not found, skipping[/red]")
            continue
        predicted, _ = extract.extract_criteria(pid, p["title"], p["coverage_text"], model=model)
        testable_ids = [c.id for c in predicted.criteria if c.type.value in ("required", "exclusion")]
        required_ids = [c.id for c in predicted.criteria if c.type.value == "required"]
        if not testable_ids:
            console.print(f"[yellow]{pid}: no testable criteria, skipping[/yellow]")
            continue

        rnd = random.Random(hash(pid) & 0xFFFFFFFF)
        # ambiguous_one only targets required criteria: check.py's own design (correctly)
        # treats silence about a named-test exclusion as not_met, not insufficient_evidence
        # -- an "ambiguous exclusion" test would be asking the checker to contradict a
        # deliberate, correct design choice, not testing a real weakness.
        variants: list[tuple[str, str | None]] = [
            ("meets_all", None),
            ("fails_one", rnd.choice(testable_ids)),
            ("ambiguous_one", rnd.choice(required_ids or testable_ids)),
        ]

        for variant, target in variants:
            note, _ = synth.synthesize_note(pid, p["title"], predicted.criteria, variant, target, model=model)
            expected = synth.expected_verdicts(predicted.criteria, note)
            out = {
                "policy_id": pid,
                "variant": variant,
                "target_criterion_id": target,
                "note_text": note.note_text,
                "addressed_required_ids": note.addressed_required_ids,
                "triggered_exclusion_ids": note.triggered_exclusion_ids,
                "expected_verdicts": expected,
            }
            (notes_dir / f"{pid}_{variant}.json").write_text(json.dumps(out, indent=2) + "\n")
            n_written += 1

    console.print(f"[green]✓[/green] wrote {n_written} synthetic notes to {notes_dir}")


@app.command("eval-checker")
def eval_checker_cmd(
    notes_dir: Path = typer.Option(config.GOLDEN_DIR / "notes"),
    model: str = typer.Option(config.MODEL),
) -> None:
    """: per-criterion verdict accuracy, abstention correctness, and appeal
    citation integrity across the synthesized note set."""
    files = sorted(f for f in notes_dir.glob("*.json") if f.name != ".gitkeep")
    if not files:
        console.print(f"[yellow]No synthetic notes in {notes_dir}. Run synthesize-notes first.[/yellow]")
        raise typer.Exit(1)

    total = correct = 0
    should_abstain = correct_abstain = 0
    all_evidence_spans: list[str | None] = []
    all_notes: list[str] = []
    n_deny = n_appeal_ok = n_appeal_failed = 0
    table = Table("policy_id", "variant", "decision", "verdict acc")

    for path in files:
        raw = json.loads(path.read_text())
        pid = raw["policy_id"]
        p = db.get_policy(pid)
        if not p:
            continue
        predicted, _ = extract.extract_criteria(pid, p["title"], p["coverage_text"], model=model)
        decision, _ = check.check_note(pid, predicted.criteria, raw["note_text"], model=model)
        checks_by_id = {c.criterion_id: c for c in decision.checks}

        case_total = case_correct = 0
        for cid, expected in raw["expected_verdicts"].items():
            actual = checks_by_id.get(cid)
            actual_verdict = actual.verdict.value if actual else None
            total += 1
            case_total += 1
            if actual_verdict == expected:
                correct += 1
                case_correct += 1
            if expected == "insufficient_evidence":
                should_abstain += 1
                if actual_verdict == "insufficient_evidence":
                    correct_abstain += 1

        all_evidence_spans.extend(c.evidence_span for c in decision.checks)
        all_notes.extend([raw["note_text"]] * len(decision.checks))

        table.add_row(pid, raw["variant"], decision.decision, f"{case_correct}/{case_total}")

        if decision.decision == "likely_deny":
            n_deny += 1
            try:
                appeal.draft_appeal(pid, p["title"], p["coverage_text"], predicted.criteria, decision, model=model)
                n_appeal_ok += 1
            except RuntimeError as exc:
                n_appeal_failed += 1
                console.print(f"[red]{pid}/{raw['variant']}: appeal citation failure — {exc}[/red]")
            except Exception as exc:
                # A malformed LLM response (see llm.structured's bounded retry) is a
                # real, reportable data point -- same principle as eval-extraction's
                # per-policy try/except. One bad appeal draft shouldn't crash the
                # other 29 cases' worth of results.
                n_appeal_failed += 1
                console.print(f"[red]{pid}/{raw['variant']}: appeal draft error — {exc}[/red]")

    console.print(table)

    # grounding_report assumes one shared source; each evidence_span here is grounded
    # against its OWN note, so check individually for a correct hallucination count.
    grounded_count = sum(
        1 for span, note in zip(all_evidence_spans, all_notes) if span and verify.span_is_grounded(span, note)
    )
    checked_count = sum(1 for span in all_evidence_spans if span)
    hallucination_rate = 1 - (grounded_count / checked_count if checked_count else 1.0)

    verdict_accuracy = correct / total if total else 0.0
    abstention_precision = correct_abstain / should_abstain if should_abstain else 0.0

    console.print(
        f"\nper-criterion verdict accuracy: {correct}/{total} ({verdict_accuracy:.1%})\n"
        f"correct abstention rate: {correct_abstain}/{should_abstain} ({abstention_precision:.1%}) "
        f"— of cases that SHOULD abstain, how many did\n"
        f"evidence-span hallucination rate: {hallucination_rate:.1%} (against the note, not the policy)\n"
        f"appeal drafts: {n_appeal_ok} ok, {n_appeal_failed} citation failures (of {n_deny} denial cases)"
    )

    if verdict_accuracy >= 0.80 and n_appeal_failed == 0:
        console.print("[green]✓ [/green]")
    else:
        console.print("[yellow]not clearly passed — review the numbers above[/yellow]")


if __name__ == "__main__":
    app()
