from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import click
from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings, utc_now
from core.store import ObjectStore
from indexengine.methodology import Methodology
from ingest.audit import audit_archive, render_audit_summary


@click.command()
@click.option("--since", required=True, help="YYYY-MM-DD archive inception date")
@click.option(
    "--until", "until_value", default=None, help="YYYY-MM-DD end date, UTC today by default"
)
@click.option("--store-root", default=None, help="Local object-store root; omit to verify R2")
@click.option("--games", default=None, help="CSV game keys; defaults to CM_GAMES.")
@click.option(
    "--game-inceptions",
    default=None,
    help="CSV game=YYYY-MM-DD pairs; defaults every game to --since.",
)
@click.option("--sample-rate", type=click.FloatRange(0.0, 1.0, min_open=True), default=1.0)
@click.option("--seed", default=None, help="Deterministic sample seed; defaults to end date")
@click.option("--output", default=None, help="Optional JSON report path")
@click.option("--summary-output", default=None, help="Optional Markdown summary path")
@click.option("--indexes", default=None, help="CSV index codes; defaults to methodology.")
@click.option("--required-lookback-days", type=click.IntRange(min=1), default=60)
@click.option("--scheduled-attempts-per-day", type=click.IntRange(min=1), default=4)
def main(
    since: str,
    until_value: str | None,
    store_root: str | None,
    games: str | None,
    game_inceptions: str | None,
    sample_rate: float,
    seed: str | None,
    output: str | None,
    summary_output: str | None,
    indexes: str | None,
    required_lookback_days: int,
    scheduled_attempts_per_day: int,
) -> None:
    start = date.fromisoformat(since)
    end = date.fromisoformat(until_value) if until_value else utc_now().date()
    if end < start:
        raise click.ClickException("--until must be on or after --since")
    settings = Settings.from_env()
    expected_games = (
        [item.strip() for item in games.split(",") if item.strip()]
        if games
        else settings.cm_games
    )
    inception_dates = {game: start for game in expected_games}
    if game_inceptions:
        try:
            inception_dates = {
                game.strip(): date.fromisoformat(value.strip())
                for item in game_inceptions.split(",")
                for game, value in [item.split("=", 1)]
                if game.strip()
            }
        except ValueError as exc:
            raise click.ClickException(
                "--game-inceptions must use game=YYYY-MM-DD pairs"
            ) from exc
    store: ObjectStore = (
        LocalObjectStore(Path(store_root)) if store_root else R2Client(settings)
    )
    index_codes = (
        [item.strip() for item in indexes.split(",") if item.strip()]
        if indexes
        else [item.code for item in Methodology.load().indexes]
    )
    report = audit_archive(
        store,
        start,
        end,
        expected_games,
        sample_rate,
        seed or end.isoformat(),
        index_codes=index_codes,
        required_lookback_days=required_lookback_days,
        scheduled_attempts_per_day=scheduled_attempts_per_day,
        game_inceptions=inception_dates,
    )
    body = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body)
    if summary_output:
        summary_destination = Path(summary_output)
        summary_destination.parent.mkdir(parents=True, exist_ok=True)
        summary_destination.write_text(render_audit_summary(report))
    click.echo(body, nl=False)
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
