from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import click
from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings, utc_now
from core.store import ObjectStore
from ingest.audit import audit_archive


@click.command()
@click.option("--since", required=True, help="YYYY-MM-DD archive inception date")
@click.option(
    "--until", "until_value", default=None, help="YYYY-MM-DD end date, UTC today by default"
)
@click.option("--store-root", default=None, help="Local object-store root; omit to verify R2")
@click.option("--games", default="onepiece,pokemon")
@click.option("--sample-rate", type=click.FloatRange(0.0, 1.0, min_open=True), default=1.0)
@click.option("--seed", default=None, help="Deterministic sample seed; defaults to end date")
@click.option("--output", default=None, help="Optional JSON report path")
def main(
    since: str,
    until_value: str | None,
    store_root: str | None,
    games: str,
    sample_rate: float,
    seed: str | None,
    output: str | None,
) -> None:
    start = date.fromisoformat(since)
    end = date.fromisoformat(until_value) if until_value else utc_now().date()
    if end < start:
        raise click.ClickException("--until must be on or after --since")
    expected_games = [item.strip() for item in games.split(",") if item.strip()]
    settings = Settings.from_env()
    store: ObjectStore = (
        LocalObjectStore(Path(store_root)) if store_root else R2Client(settings)
    )
    report = audit_archive(store, start, end, expected_games, sample_rate, seed or end.isoformat())
    body = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body)
    click.echo(body, nl=False)
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
