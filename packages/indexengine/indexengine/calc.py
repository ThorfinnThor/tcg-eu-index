from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from io import BytesIO
from typing import Any, cast

import click
import polars as pl
from core.logging import configure_logging
from core.r2 import R2Client
from core.settings import Settings, parse_run_date
from core.store import ObjectStore

from indexengine.methodology import IndexDefinition, Methodology
from indexengine.selection import Constituent, select_constituents


@dataclass(frozen=True)
class DailyValue:
    value_date: str
    index_value: float
    daily_return: float
    n_constituents_active: int
    n_capped: int
    n_carried_forward: int
    calc_version: str


@dataclass(frozen=True)
class Contribution:
    value_date: str
    cm_product_id: int
    variant_key: str
    weight: float
    used_return: float
    contribution: float


def price_column(frame: pl.DataFrame, primary: str, fallback: str) -> pl.DataFrame:
    return frame.with_columns(
        pl.coalesce([pl.col(primary), pl.col(fallback)]).cast(pl.Float64).alias("used_price")
    )


def calculate_daily_values(
    prices: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    constituents: list[Constituent],
    start_value: float | None = None,
) -> tuple[list[DailyValue], list[Contribution]]:
    if not constituents or prices.is_empty():
        return [], []
    start_value = start_value or definition.base_value
    identities = {(item.cm_product_id, item.variant_key) for item in constituents}
    priced = price_column(
        prices,
        methodology.price_field_primary,
        methodology.price_field_fallback,
    )
    frame = priced.filter(
        pl.struct(["cm_product_id", "variant_key"]).map_elements(
            lambda row: (row["cm_product_id"], row["variant_key"]) in identities,
            return_dtype=pl.Boolean,
        )
    )
    by_day: dict[date, list[dict[str, object]]] = {}
    for row in frame.sort("value_date").iter_rows(named=True):
        value_date = row["value_date"]
        if isinstance(value_date, str):
            value_date = date.fromisoformat(value_date)
        by_day.setdefault(value_date, []).append(row)

    previous_price: dict[tuple[int, str], float] = {}
    carried_days: dict[tuple[int, str], int] = {}
    index_value = start_value
    values: list[DailyValue] = []
    contributions: list[Contribution] = []
    cap = methodology.daily_return_cap

    for value_date in sorted(by_day):
        day_returns: list[tuple[tuple[int, str], float, bool, bool]] = []
        rows = {}
        for row in by_day[value_date]:
            typed_row = cast(Any, row)
            rows[(int(typed_row["cm_product_id"]), str(typed_row["variant_key"]))] = row
        for identity in identities:
            price = cast(Any, rows.get(identity, {})).get("used_price")
            if price is None or (isinstance(price, float) and math.isnan(price)):
                carried = carried_days.get(identity, 0)
                if carried < methodology.carry_forward_max_days and identity in previous_price:
                    carried_days[identity] = carried + 1
                    day_returns.append((identity, 0.0, False, True))
                continue
            price_float = float(price)
            if identity not in previous_price:
                previous_price[identity] = price_float
                carried_days[identity] = 0
                day_returns.append((identity, 0.0, False, False))
                continue
            raw_return = price_float / previous_price[identity] - 1
            used_return = min(cap, max(-cap, raw_return))
            was_capped = used_return != raw_return
            previous_price[identity] = price_float
            carried_days[identity] = 0
            day_returns.append((identity, used_return, was_capped, False))

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
                n_capped=sum(1 for item in day_returns if item[2]),
                n_carried_forward=sum(1 for item in day_returns if item[3]),
                calc_version=methodology.methodology_version,
            )
        )
        for identity, used_return, _, _ in day_returns:
            contributions.append(
                Contribution(
                    value_date=value_date.isoformat(),
                    cm_product_id=identity[0],
                    variant_key=identity[1],
                    weight=weight,
                    used_return=used_return,
                    contribution=weight * used_return,
                )
            )
    return values, contributions


def analytics(values: list[DailyValue], contributions: list[Contribution]) -> dict[str, object]:
    if not values:
        return {"windows": {}}
    latest = values[-1]
    recent = contributions[-200:]
    movers = sorted(recent, key=lambda row: row.used_return, reverse=True)
    return {
        "latest": asdict(latest),
        "windows": {
            "1d": {
                "breadth": (
                    sum(1 for item in recent if item.used_return > 0) / len(recent)
                    if recent
                    else 0
                ),
                "top": [asdict(item) for item in movers[:10]],
                "bottom": [asdict(item) for item in movers[-10:]],
            }
        },
    }


def export_public(
    store: ObjectStore,
    definition: IndexDefinition,
    values: list[DailyValue],
    contributions: list[Contribution],
) -> None:
    payload = [asdict(item) for item in values]
    latest = payload[-1] if payload else None
    summary = analytics(values, contributions)
    prefix = f"derived/public/{definition.code}"
    write = store.write_bytes
    write(
        f"{prefix}/history.json",
        json.dumps(payload, indent=2).encode(),
        "application/json",
    )
    write(
        f"{prefix}/latest.json",
        json.dumps(latest, indent=2).encode(),
        "application/json",
    )
    write(
        f"{prefix}/summary.json",
        json.dumps(summary, indent=2).encode(),
        "application/json",
    )
    csv_lines = ["value_date,index_value,daily_return,n_constituents_active"]
    csv_lines.extend(
        f"{row.value_date},{row.index_value:.6f},{row.daily_return:.8f},{row.n_constituents_active}"
        for row in values
    )
    write(f"{prefix}/history.csv", ("\n".join(csv_lines) + "\n").encode(), "text/csv")


def run_calc(run_date: date, settings: Settings, store: ObjectStore | None = None) -> None:
    store = store or R2Client(settings)
    methodology = Methodology.load()
    for definition in methodology.indexes:
        parquet_key = f"derived/prices/{definition.game_key}/{run_date:%Y-%m}.parquet"
        if not store.exists(parquet_key):
            continue
        prices = pl.read_parquet(BytesIO(store.read_bytes(parquet_key)))
        effective = date.fromisoformat(definition.base_date)
        constituents = select_constituents(prices, definition, methodology, effective)
        values, contributions = calculate_daily_values(
            prices,
            definition,
            methodology,
            constituents,
        )
        export_public(store, definition, values, contributions)


@click.command()
@click.option("--date", "date_value", default="today")
def main(date_value: str) -> None:
    configure_logging()
    run_calc(parse_run_date(date_value), Settings.from_env())


if __name__ == "__main__":
    main()
