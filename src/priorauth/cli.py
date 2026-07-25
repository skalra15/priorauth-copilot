"""Command line entrypoint: `python -m priorauth.cli <command>`."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import config, db, extract, ingest, retrieve, verify
from .schemas import ExtractedCriteria

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


if __name__ == "__main__":
    app()
