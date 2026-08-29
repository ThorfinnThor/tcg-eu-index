from __future__ import annotations

import json
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from statistics import median
from typing import Any, cast

import click
import polars as pl
from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings
from core.store import ObjectStore
from ingest.manifest import Manifest

from indexengine.activity import score_trading_activity_proxy
from indexengine.methodology import Methodology


def build_activity_audit(
    store: ObjectStore,
    methodology: Methodology,
    through_date: date,
) -> dict[str, object]:
    if methodology.activity is None:
        raise ValueError("activity audit requires a schema v2 methodology")
    games = sorted({definition.game_key for definition in methodology.indexes})
    game_reports = []
    for game in games:
        prices = _load_prices(store, game, through_date)
        calendar_dates, unchanged_dates = _archive_calendar(store, game, through_date)
        start = through_date + timedelta(days=1 - methodology.activity.lookback_days)
        quality_calendar = [value for value in calendar_dates if start <= value <= through_date]
        observable_dates = [
            value
            for value in quality_calendar
            if not (methodology.activity.exclude_unchanged_snapshots and value in unchanged_dates)
        ]
        window = prices.filter(
            (pl.col("value_date") >= start) & (pl.col("value_date") <= through_date)
        )
        activity = score_trading_activity_proxy(
            window,
            observable_dates,
            through_date + timedelta(days=1),
            signal_field=methodology.activity.signal_field,
        )
        latest_kinds = (
            window.sort("value_date")
            .group_by(["stable_variant_id", "cm_product_id", "variant_key"])
            .agg(pl.col("product_kind").last())
        )
        scored = activity.join(
            latest_kinds,
            on=["stable_variant_id", "cm_product_id", "variant_key"],
            how="left",
        )
        game_reports.append(
            {
                "game_key": game,
                "calendar_days": len(quality_calendar),
                "observable_source_days": len(observable_dates),
                "excluded_unchanged_snapshots": len(set(quality_calendar) & unchanged_dates),
                "universes": {
                    universe: _universe_report(
                        scored.filter(pl.col("product_kind") == product_kind),
                        len(observable_dates),
                    )
                    for universe, product_kind in (
                        ("singles", "single"),
                        ("sealed", "sealed"),
                    )
                },
            }
        )
    return {
        "schema_version": 1,
        "methodology_version": methodology.methodology_version,
        "through_date": through_date.isoformat(),
        "signal_field": methodology.activity.signal_field,
        "semantics": {
            "validated_claim": (
                "positive aggregate one-day sale-price signal; not a transaction count, "
                "traded quantity, or traded value"
            ),
            "hard_eligibility_gate_supported": False,
            "reason": (
                "Cardmarket public archives expose rolling aggregate avg1 values but no "
                "underlying sales, quantities, conditions, languages, or timestamps"
            ),
        },
        "games": game_reports,
    }


def render_summary(report: dict[str, object]) -> str:
    lines = [
        "# Cardmarket avg1 activity-proxy audit",
        "",
        f"Through: `{report['through_date']}`",
        "",
        "`avg1 > 0` is retained only as an aggregate activity proxy. The audit does not "
        "support using it as a hard eligibility gate.",
        "",
        "| Game | Universe | Observable days | Variants | Positive signal rate | "
        "Repeated-positive rate |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for game in cast(list[dict[str, Any]], report["games"]):
        for universe, values in game["universes"].items():
            lines.append(
                f"| {game['game_key']} | {universe} | {game['observable_source_days']} | "
                f"{values['variant_count']} | {values['positive_signal_rate']:.4f} | "
                f"{values['repeated_positive_signal_rate']:.4f} |"
            )
    return "\n".join(lines) + "\n"


def _load_prices(store: ObjectStore, game: str, through_date: date) -> pl.DataFrame:
    keys = sorted(
        key
        for key in store.list_keys(f"derived/prices/{game}")
        if key.endswith(".parquet") and Path(key).stem <= through_date.strftime("%Y-%m")
    )
    if not keys:
        raise RuntimeError(f"no normalized price history for {game} through {through_date}")
    frames = [pl.read_parquet(BytesIO(store.read_bytes(key))) for key in keys]
    return pl.concat(frames, how="diagonal_relaxed").filter(pl.col("value_date") <= through_date)


def _archive_calendar(
    store: ObjectStore, game: str, through_date: date
) -> tuple[list[date], set[date]]:
    dates: list[date] = []
    unchanged: set[date] = set()
    for key in sorted(store.list_keys("manifests")):
        if not key.endswith(".json"):
            continue
        manifest = Manifest.from_bytes(store.read_bytes(key))
        manifest_date = date.fromisoformat(manifest.run_date)
        if manifest_date > through_date:
            continue
        price_file = next(
            (item for item in manifest.files if item.game == game and item.kind == "priceguide"),
            None,
        )
        if price_file is None:
            continue
        dates.append(manifest_date)
        if price_file.unchanged_from_previous:
            unchanged.add(manifest_date)
    return sorted(set(dates)), unchanged


def _universe_report(scores: pl.DataFrame, observable_days: int) -> dict[str, object]:
    if scores.is_empty():
        return {
            "variant_count": 0,
            "positive_signal_rate": 0.0,
            "zero_signal_rate": 0.0,
            "null_or_missing_signal_rate": 0.0,
            "repeated_positive_signal_rate": 0.0,
            "median_variant_activity_ratio": 0.0,
            "p90_days_since_positive_signal": None,
        }
    variant_count = scores.height
    denominator = variant_count * observable_days
    activity_days = int(scores["activity_days"].sum())
    zero_days = int(scores["zero_signal_days"].sum())
    null_days = int(scores["null_or_missing_signal_days"].sum())
    repeated_days = int(scores["repeated_positive_signal_days"].sum())
    lags = [int(value) for value in scores["days_since_positive_signal"].drop_nulls().to_list()]
    return {
        "variant_count": variant_count,
        "positive_signal_rate": _ratio(activity_days, denominator),
        "zero_signal_rate": _ratio(zero_days, denominator),
        "null_or_missing_signal_rate": _ratio(null_days, denominator),
        "repeated_positive_signal_rate": _ratio(repeated_days, activity_days),
        "median_variant_activity_ratio": float(median(scores["activity_ratio"].to_list())),
        "p90_days_since_positive_signal": _percentile(lags, 0.9),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(int((len(ordered) - 1) * fraction), len(ordered) - 1)]


@click.command()
@click.option("--through", "through_value", required=True, help="Last archive date, YYYY-MM-DD")
@click.option("--store-root", default=None, help="Local object-store root; omit for R2")
@click.option(
    "--methodology",
    "methodology_path",
    type=click.Path(path_type=Path),
    default=Path("packages/indexengine/methodologies/v1.5.0-preview.2.yaml"),
)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--summary-output", type=click.Path(path_type=Path), required=True)
def main(
    through_value: str,
    store_root: str | None,
    methodology_path: Path,
    output: Path,
    summary_output: Path,
) -> None:
    settings = Settings.from_env()
    store: ObjectStore = LocalObjectStore(Path(store_root)) if store_root else R2Client(settings)
    report = build_activity_audit(
        store,
        Methodology.load(methodology_path),
        date.fromisoformat(through_value),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(render_summary(report))
    click.echo(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
