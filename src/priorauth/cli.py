"""Command line entrypoint: `python -m priorauth.cli <command>`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import config, db, ingest

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


if __name__ == "__main__":
    app()
