from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import click
import polars as pl
from core.logging import configure_logging
from core.r2 import R2Client, sha256_hex
from core.settings import Settings, parse_run_date
from core.store import ObjectStore
from ingest.manifest import Manifest

from indexengine.analytics import calculate_analytics
from indexengine.methodology import IndexDefinition, Methodology
from indexengine.selection import (
    Constituent,
    RemovedConstituent,
    SelectionResult,
    select_constituents,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rebalance:
    effective_date: str
    methodology_version: str
    selection_snapshot_sha256: str
    eligible_count: int
    constituents: list[Constituent]
    removed: list[RemovedConstituent]


@dataclass(frozen=True)
class DailyValue:
    value_date: str
    index_value: float
    daily_return: float
    n_constituents_active: int
    n_capped: int
    n_carried_forward: int
    n_stale: int
    whole_market_carried_forward: bool
    rebalance_effective_date: str
    calc_version: str


@dataclass(frozen=True)
class Contribution:
    value_date: str
    stable_variant_id: str
    cm_product_id: int
    variant_key: str
    weight: float
    used_return: float
    contribution: float
    flag: str


@dataclass(frozen=True)
class CalcRunResult:
    index_code: str
    run_date: str
    status: str
    available_days: int
    required_days: int
    selected_constituents: int
    daily_values: int
    contributions: int
    analytics_days: int
    latest_rebalance: str | None
    changed_outputs: list[str]


DAILY_SCHEMA = {
    "value_date": pl.String,
    "index_value": pl.Float64,
    "daily_return": pl.Float64,
    "n_constituents_active": pl.Int64,
    "n_capped": pl.Int64,
    "n_carried_forward": pl.Int64,
    "n_stale": pl.Int64,
    "whole_market_carried_forward": pl.Boolean,
    "rebalance_effective_date": pl.String,
    "calc_version": pl.String,
}
CONTRIBUTION_SCHEMA = {
    "value_date": pl.String,
    "stable_variant_id": pl.String,
    "cm_product_id": pl.Int64,
    "variant_key": pl.String,
    "weight": pl.Float64,
    "used_return": pl.Float64,
    "contribution": pl.Float64,
    "flag": pl.String,
}


def price_column(frame: pl.DataFrame, primary: str, fallback: str) -> pl.DataFrame:
    return frame.with_columns(
        pl.coalesce([pl.col(primary), pl.col(fallback)]).cast(pl.Float64).alias("used_price")
    )


def calculate_chain_linked(
    prices: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    rebalances: list[Rebalance],
    calendar_dates: list[date] | None = None,
    unchanged_dates: set[date] | None = None,
) -> tuple[list[DailyValue], list[Contribution]]:
    if not rebalances or prices.is_empty():
        return [], []
    unchanged_dates = unchanged_dates or set()
    priced = price_column(prices, methodology.price_field_primary, methodology.price_field_fallback)
    if "stable_variant_id" not in priced.columns:
        priced = priced.with_columns(
            (
                pl.lit(f"cardmarket:{definition.game_key}:product:")
                + pl.col("cm_product_id").cast(pl.String)
                + pl.lit(":")
                + pl.col("variant_key")
            ).alias("stable_variant_id")
        )
    rows_by_day: dict[date, dict[tuple[int, str], dict[str, Any]]] = {}
    for row in priced.sort(["value_date", "stable_variant_id"]).iter_rows(named=True):
        value_date = row["value_date"]
        parsed_date = date.fromisoformat(value_date) if isinstance(value_date, str) else value_date
        identity = int(row["cm_product_id"]), str(row["variant_key"])
        rows_by_day.setdefault(parsed_date, {})[identity] = row

    calendar_dates = sorted(rows_by_day) if calendar_dates is None else sorted(set(calendar_dates))
    ordered_rebalances = sorted(rebalances, key=lambda item: item.effective_date)
    rebalance_cursor = 0
    current_rebalance: Rebalance | None = None
    current_constituents: dict[tuple[int, str], Constituent] = {}
    previous_price: dict[tuple[int, str], float] = {}
    carried_days: dict[tuple[int, str], int] = {}
    index_value = definition.base_value
    values: list[DailyValue] = []
    contributions: list[Contribution] = []
    cap = methodology.daily_return_cap

    for value_date in calendar_dates:
        while (
            rebalance_cursor < len(ordered_rebalances)
            and date.fromisoformat(ordered_rebalances[rebalance_cursor].effective_date)
            <= value_date
        ):
            current_rebalance = ordered_rebalances[rebalance_cursor]
            current_constituents = {item.identity: item for item in current_rebalance.constituents}
            rebalance_cursor += 1
        if current_rebalance is None:
            continue

        day_returns: list[tuple[tuple[int, str], float, str, bool]] = []
        n_stale = 0
        day_rows = rows_by_day.get(value_date, {})
        if value_date in unchanged_dates:
            for identity in sorted(current_constituents):
                if identity in previous_price:
                    day_returns.append((identity, 0.0, "snapshot_unchanged", False))
        else:
            for identity in sorted(current_constituents):
                current_row = day_rows.get(identity)
                price = _positive_price(current_row.get("used_price") if current_row else None)
                if price is not None:
                    if identity not in previous_price:
                        previous_price[identity] = price
                        carried_days[identity] = 0
                        day_returns.append((identity, 0.0, "initialized", False))
                        continue
                    raw_return = price / previous_price[identity] - 1
                    used_return = min(cap, max(-cap, raw_return))
                    capped = not math.isclose(used_return, raw_return, rel_tol=0, abs_tol=1e-15)
                    previous_price[identity] = price
                    carried_days[identity] = 0
                    day_returns.append(
                        (identity, used_return, "spike_capped" if capped else "fresh", capped)
                    )
                    continue

                carried = carried_days.get(identity, 0)
                if identity in previous_price and carried < methodology.carry_forward_max_days:
                    carried_days[identity] = carried + 1
                    day_returns.append((identity, 0.0, "carried_forward", False))
                else:
                    n_stale += 1

        if not day_returns:
            continue
        daily_return = sum(item[1] for item in day_returns) / len(day_returns)
        index_value *= 1 + daily_return
        weight = 1 / len(day_returns)
        values.append(
            DailyValue(
                value_date=value_date.isoformat(),
                index_value=index_value,
                daily_return=daily_return,
                n_constituents_active=len(day_returns),
                n_capped=sum(1 for item in day_returns if item[3]),
                n_carried_forward=sum(
                    1
                    for item in day_returns
                    if item[2] in {"carried_forward", "snapshot_unchanged"}
                ),
                n_stale=n_stale,
                whole_market_carried_forward=value_date in unchanged_dates,
                rebalance_effective_date=current_rebalance.effective_date,
                calc_version=methodology.methodology_version,
            )
        )
        for identity, used_return, flag, _ in day_returns:
            constituent = current_constituents[identity]
            stable_id = constituent.stable_variant_id or (
                f"cardmarket:{definition.game_key}:product:{identity[0]}:{identity[1]}"
            )
            contributions.append(
                Contribution(
                    value_date=value_date.isoformat(),
                    stable_variant_id=stable_id,
                    cm_product_id=identity[0],
                    variant_key=identity[1],
                    weight=weight,
                    used_return=used_return,
                    contribution=weight * used_return,
                    flag=flag,
                )
            )
    return values, contributions


def calculate_daily_values(
    prices: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    constituents: list[Constituent],
    start_value: float | None = None,
) -> tuple[list[DailyValue], list[Contribution]]:
    if not constituents or prices.is_empty():
        return [], []
    if start_value is not None and start_value != definition.base_value:
        definition = IndexDefinition(**{**asdict(definition), "base_value": start_value})
    first_date = prices["value_date"].min()
    if not isinstance(first_date, date):
        first_date = date.fromisoformat(str(first_date))
    rebalance = Rebalance(
        effective_date=first_date.isoformat(),
        methodology_version=methodology.methodology_version,
        selection_snapshot_sha256="single-selection",
        eligible_count=len(constituents),
        constituents=constituents,
        removed=[],
    )
    return calculate_chain_linked(prices, definition, methodology, [rebalance])


def monthly_rebalances(
    prices: pl.DataFrame,
    products: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    run_date: date,
) -> list[Rebalance]:
    if prices.is_empty():
        return []
    earliest = prices["value_date"].min()
    earliest_date = earliest if isinstance(earliest, date) else date.fromisoformat(str(earliest))
    cursor = date(earliest_date.year, earliest_date.month, 1)
    rebalances: list[Rebalance] = []
    incumbents: set[tuple[int, str]] = set()
    while cursor <= run_date:
        if cursor >= date.fromisoformat(definition.base_date):
            selection = select_constituents(
                prices,
                products,
                definition,
                methodology,
                cursor,
                incumbents,
            )
            if len(selection.constituents) >= definition.target_size:
                rebalance = _rebalance_from_selection(cursor, methodology, selection)
                rebalances.append(rebalance)
                incumbents = {item.identity for item in rebalance.constituents}
        cursor = _next_month(cursor)
    return rebalances


def _rebalance_from_selection(
    effective_date: date,
    methodology: Methodology,
    selection: SelectionResult,
) -> Rebalance:
    return Rebalance(
        effective_date=effective_date.isoformat(),
        methodology_version=methodology.methodology_version,
        selection_snapshot_sha256=selection.snapshot_sha256,
        eligible_count=selection.eligible_count,
        constituents=selection.constituents,
        removed=selection.removed,
    )


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def _load_price_history(store: ObjectStore, game: str, run_date: date) -> tuple[pl.DataFrame, str]:
    keys = sorted(
        key
        for key in store.list_keys(f"derived/prices/{game}")
        if key.endswith(".parquet") and Path(key).stem <= run_date.strftime("%Y-%m")
    )
    if not keys:
        raise RuntimeError(f"no normalized price history for {game} through {run_date}")
    frames: list[pl.DataFrame] = []
    sources: list[dict[str, object]] = []
    for key in keys:
        body = store.read_bytes(key)
        frames.append(pl.read_parquet(BytesIO(body)))
        sources.append({"key": key, "sha256": sha256_hex(body), "size": len(body)})
    prices = pl.concat(frames, how="diagonal_relaxed").filter(pl.col("value_date") <= run_date)
    source_sha = sha256_hex(_json_bytes(sources))
    return prices, source_sha


def _archive_calendar(
    store: ObjectStore, game: str, run_date: date, prices: pl.DataFrame
) -> tuple[list[date], set[date]]:
    dates: list[date] = []
    unchanged: set[date] = set()
    for key in sorted(store.list_keys("manifests")):
        if not key.endswith(".json"):
            continue
        try:
            manifest = Manifest.from_bytes(store.read_bytes(key))
            manifest_date = date.fromisoformat(manifest.run_date)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if manifest_date > run_date:
            continue
        dates.append(manifest_date)
        price_file = next(
            (item for item in manifest.files if item.game == game and item.kind == "priceguide"),
            None,
        )
        if price_file is not None and price_file.unchanged_from_previous:
            unchanged.add(manifest_date)
    if not dates:
        dates = sorted(set(prices["value_date"].to_list()))
    return sorted(set(dates)), unchanged


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n"


def _positive_price(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _parquet_bytes(records: list[dict[str, Any]], schema: dict[str, Any]) -> bytes:
    frame = pl.DataFrame(records, schema=schema) if records else pl.DataFrame(schema=schema)
    if records:
        sort_columns = ["value_date"]
        if "stable_variant_id" in frame.columns:
            sort_columns.append("stable_variant_id")
        frame = frame.sort(sort_columns)
    buffer = BytesIO()
    frame.write_parquet(buffer, compression="zstd", statistics=True)
    return buffer.getvalue()


def _write_if_changed(store: ObjectStore, key: str, body: bytes, content_type: str) -> bool:
    if store.exists(key) and store.read_bytes(key) == body:
        return False
    store.write_bytes(key, body, content_type)
    return True


def _metadata(key: str, body: bytes, rows: int) -> dict[str, object]:
    return {"key": key, "rows": rows, "size": len(body), "sha256": sha256_hex(body)}


def run_calc(
    run_date: date,
    settings: Settings,
    store: ObjectStore | None = None,
    methodology_path: Path = Path("packages/indexengine/methodology.yaml"),
) -> list[CalcRunResult]:
    store = store or R2Client(settings)
    methodology = Methodology.load(methodology_path)
    methodology_body = methodology_path.read_bytes()
    engine_revision = os.getenv("GITHUB_SHA", "local-working-tree")
    results: list[CalcRunResult] = []

    definitions = [
        definition
        for definition in methodology.indexes
        if definition.game_key in settings.cm_games
    ]
    for definition in definitions:
        prices, price_source_sha = _load_price_history(store, definition.game_key, run_date)
        products_key = f"derived/catalogue/{definition.game_key}/products.parquet"
        if not store.exists(products_key):
            raise RuntimeError(f"missing normalized catalogue {products_key}")
        products_body = store.read_bytes(products_key)
        products = pl.read_parquet(BytesIO(products_body))
        calendar_dates, unchanged_dates = _archive_calendar(
            store, definition.game_key, run_date, prices
        )
        rebalances = monthly_rebalances(prices, products, definition, methodology, run_date)
        values, contributions = calculate_chain_linked(
            prices,
            definition,
            methodology,
            rebalances,
            calendar_dates,
            unchanged_dates,
        )
        analytics = calculate_analytics(values, contributions, products)
        latest_rebalance = rebalances[-1] if rebalances else None
        selected_count = len(latest_rebalance.constituents) if latest_rebalance else 0
        status = (
            "ready"
            if latest_rebalance is not None
            and selected_count == definition.target_size
            and bool(values)
            else "accumulating"
        )

        prefix = f"derived/indexes/{definition.code}"
        rebalances_key = f"{prefix}/rebalances.json"
        values_key = f"{prefix}/daily-values.parquet"
        contributions_key = f"{prefix}/contributions.parquet"
        analytics_key = f"{prefix}/analytics.json"
        quality_key = f"{prefix}/quality/{run_date.isoformat()}.json"
        rebalances_body = _json_bytes(
            {
                "schema_version": 1,
                "index_code": definition.code,
                "methodology_version": methodology.methodology_version,
                "rebalances": [asdict(item) for item in rebalances],
            }
        )
        values_body = _parquet_bytes([asdict(item) for item in values], DAILY_SCHEMA)
        contributions_body = _parquet_bytes(
            [asdict(item) for item in contributions], CONTRIBUTION_SCHEMA
        )
        analytics_body = _json_bytes(
            {
                "schema_version": 1,
                "index_code": definition.code,
                "methodology_version": methodology.methodology_version,
                "generated_for": run_date.isoformat(),
                "windows": ["1d", "7d", "30d"],
                "volatility_label": "annualized listing-price volatility",
                "records": [asdict(item) for item in analytics],
            }
        )
        quality_body = _json_bytes(
            {
                "schema_version": 1,
                "index_code": definition.code,
                "run_date": run_date.isoformat(),
                "status": status,
                "available_archive_days": len(calendar_dates),
                "required_lookback_days": methodology.selection_lookback_days,
                "days_remaining_before_full_lookback": max(
                    methodology.selection_lookback_days - len(calendar_dates), 0
                ),
                "target_size": definition.target_size,
                "selected_constituents": selected_count,
                "daily_values": len(values),
                "analytics_days": len(analytics),
                "latest_analytics_date": analytics[-1].value_date if analytics else None,
                "latest_rebalance": latest_rebalance.effective_date if latest_rebalance else None,
                "language_scope": definition.language_scope,
                "language_scope_status": "pending_source_field",
                "public_export": "blocked_until_cutover_review",
            }
        )
        outputs = {
            rebalances_key: (rebalances_body, "application/json", len(rebalances)),
            values_key: (values_body, "application/vnd.apache.parquet", len(values)),
            contributions_key: (
                contributions_body,
                "application/vnd.apache.parquet",
                len(contributions),
            ),
            analytics_key: (analytics_body, "application/json", len(analytics)),
            quality_key: (quality_body, "application/json", 1),
        }
        changed: list[str] = []
        for key, (body, content_type, _) in outputs.items():
            if _write_if_changed(store, key, body, content_type):
                changed.append(key)

        manifest_key = f"{prefix}/manifest.json"
        manifest_body = _json_bytes(
            {
                "schema_version": 1,
                "index_code": definition.code,
                "generated_for": run_date.isoformat(),
                "status": status,
                "methodology_version": methodology.methodology_version,
                "methodology_sha256": sha256_hex(methodology_body),
                "engine_revision": engine_revision,
                "source": {
                    "price_history_sha256": price_source_sha,
                    "catalogue_key": products_key,
                    "catalogue_sha256": sha256_hex(products_body),
                },
                "outputs": {
                    key: _metadata(key, body, rows) for key, (body, _, rows) in outputs.items()
                },
            }
        )
        if _write_if_changed(store, manifest_key, manifest_body, "application/json"):
            changed.append(manifest_key)
        result = CalcRunResult(
            index_code=definition.code,
            run_date=run_date.isoformat(),
            status=status,
            available_days=len(calendar_dates),
            required_days=methodology.selection_lookback_days,
            selected_constituents=selected_count,
            daily_values=len(values),
            contributions=len(contributions),
            analytics_days=len(analytics),
            latest_rebalance=latest_rebalance.effective_date if latest_rebalance else None,
            changed_outputs=changed,
        )
        results.append(result)
        logger.info("shadow_index_complete", extra={"extra": asdict(result)})

    receipt_key = f"derived/calc_runs/{run_date.isoformat()}.json"
    receipt_body = _json_bytes(
        {
            "schema_version": 1,
            "run_date": run_date.isoformat(),
            "methodology_version": methodology.methodology_version,
            "engine_revision": engine_revision,
            "status": "ok",
            "indexes": [
                {key: value for key, value in asdict(result).items() if key != "changed_outputs"}
                for result in results
            ],
        }
    )
    receipt_changed = _write_if_changed(store, receipt_key, receipt_body, "application/json")
    if receipt_changed:
        results = [
            CalcRunResult(
                **{
                    **asdict(result),
                    "changed_outputs": [*result.changed_outputs, receipt_key],
                }
            )
            for result in results
        ]
    return results


@click.command()
@click.option("--date", "date_value", default="today")
def main(date_value: str) -> None:
    configure_logging()
    results = run_calc(parse_run_date(date_value), Settings.from_env())
    click.echo(_json_bytes({"results": [asdict(item) for item in results]}).decode(), nl=False)


if __name__ == "__main__":
    main()
