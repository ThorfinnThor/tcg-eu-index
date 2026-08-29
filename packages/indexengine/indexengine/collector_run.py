from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from io import BytesIO
from pathlib import Path

import click
import polars as pl
from core.logging import configure_logging
from core.r2 import R2Client, sha256_hex
from core.settings import Settings, parse_run_date
from core.store import ObjectStore
from ingest.manifest import Manifest

from indexengine.collector_calc import (
    build_monthly_collector_rebalances,
    calculate_collector_chain_linked,
)
from indexengine.eligibility import evaluate_collector_eligibility
from indexengine.methodology import Methodology
from indexengine.product_identity import build_collector_product_metadata
from indexengine.versioned_outputs import (
    build_collector_output_bundle,
    write_collector_output_bundle,
)

DEFAULT_METHODOLOGY = Path("packages/indexengine/methodologies/v1.5.0-preview.2.yaml")


@dataclass(frozen=True)
class CollectorRunResult:
    index_code: str
    run_date: str
    methodology_version: str
    status: str
    archive_days: int
    rebalances: int
    constituents: int
    value_days: int
    changed_outputs: list[str]


def run_collector_shadow(
    run_date: date,
    settings: Settings,
    *,
    store: ObjectStore | None = None,
    methodology_path: Path = DEFAULT_METHODOLOGY,
) -> list[CollectorRunResult]:
    """Calculate enabled v1.5 families into versioned private R2 namespaces."""
    store = store or R2Client(settings)
    methodology = Methodology.load(methodology_path)
    enabled = [
        definition
        for definition in methodology.indexes
        if definition.game_key in settings.cm_games
        and definition.family is not None
        and methodology.families[definition.family].calculation_enabled
    ]
    results: list[CollectorRunResult] = []
    for definition in enabled:
        prices, price_hash = _load_prices(store, definition.game_key, run_date)
        products_body = _required_body(
            store, f"derived/catalogue/{definition.game_key}/products.parquet"
        )
        sets_body = _required_body(
            store, f"derived/catalogue/{definition.game_key}/sets.parquet"
        )
        products = pl.read_parquet(BytesIO(products_body))
        sets = pl.read_parquet(BytesIO(sets_body))
        calendar_dates, unchanged_dates = _archive_calendar(
            store, definition.game_key, run_date
        )
        rebalances = build_monthly_collector_rebalances(
            prices,
            products,
            definition,
            methodology,
            calendar_dates,
            unchanged_dates=unchanged_dates,
            data_state="shadow",
        )
        daily_values, contributions = calculate_collector_chain_linked(
            prices,
            definition,
            methodology,
            rebalances,
            calendar_dates,
            unchanged_dates=unchanged_dates,
        )
        diagnostics = []
        if rebalances:
            diagnostics = list(
                evaluate_collector_eligibility(
                    prices,
                    products,
                    definition,
                    methodology,
                    rebalances[-1].effective_date,
                    calendar_dates=calendar_dates,
                    unchanged_dates=unchanged_dates,
                    data_state="shadow",
                ).diagnostics
            )
        bundle = build_collector_output_bundle(
            definition,
            methodology,
            run_date,
            rebalances,
            daily_values,
            contributions,
            diagnostics,
            product_metadata=build_collector_product_metadata(products, sets),
            source_hashes={
                "methodology": sha256_hex(methodology_path.read_bytes()),
                "price_history": price_hash,
                "products": sha256_hex(products_body),
                "sets": sha256_hex(sets_body),
            },
            engine_revision=os.getenv("GITHUB_SHA", "local-working-tree"),
        )
        changed = write_collector_output_bundle(store, bundle)
        latest_count = len(rebalances[-1].constituents) if rebalances else 0
        results.append(
            CollectorRunResult(
                index_code=definition.code,
                run_date=run_date.isoformat(),
                methodology_version=methodology.methodology_version,
                status=(
                    "preview"
                    if any(item.index_value is not None for item in daily_values)
                    else "accumulating"
                ),
                archive_days=len(calendar_dates),
                rebalances=len(rebalances),
                constituents=latest_count,
                value_days=sum(item.index_value is not None for item in daily_values),
                changed_outputs=changed,
            )
        )
    return results


def _load_prices(
    store: ObjectStore,
    game: str,
    through_date: date,
) -> tuple[pl.DataFrame, str]:
    keys = sorted(
        key
        for key in store.list_keys(f"derived/prices/{game}")
        if key.endswith(".parquet") and Path(key).stem <= through_date.strftime("%Y-%m")
    )
    if not keys:
        raise RuntimeError(f"no normalized price history for {game} through {through_date}")
    bodies = [store.read_bytes(key) for key in keys]
    frames = [pl.read_parquet(BytesIO(body)) for body in bodies]
    prices = pl.concat(frames, how="diagonal_relaxed").filter(
        pl.col("value_date") <= through_date
    )
    hash_body = "".join(sha256_hex(body) for body in bodies).encode()
    return prices, sha256_hex(hash_body)


def _archive_calendar(
    store: ObjectStore,
    game: str,
    through_date: date,
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
            (
                item
                for item in manifest.files
                if item.game == game and item.kind == "priceguide"
            ),
            None,
        )
        if price_file is None:
            continue
        dates.append(manifest_date)
        if price_file.unchanged_from_previous:
            unchanged.add(manifest_date)
    return sorted(set(dates)), unchanged


def _required_body(store: ObjectStore, key: str) -> bytes:
    if not store.exists(key):
        raise RuntimeError(f"missing normalized catalogue {key}")
    return store.read_bytes(key)


@click.command()
@click.option("--date", "date_value", default="today")
@click.option(
    "--methodology",
    "methodology_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_METHODOLOGY,
)
def main(date_value: str, methodology_path: Path) -> None:
    configure_logging()
    results = run_collector_shadow(
        parse_run_date(date_value),
        Settings.from_env(),
        methodology_path=methodology_path,
    )
    click.echo(json.dumps([asdict(item) for item in results], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
