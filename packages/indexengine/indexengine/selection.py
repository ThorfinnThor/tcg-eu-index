from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

import polars as pl
from core.r2 import sha256_hex

from indexengine.liquidity import score_liquidity
from indexengine.methodology import IndexDefinition, Methodology


@dataclass(frozen=True)
class Constituent:
    cm_product_id: int
    variant_key: str
    action: str
    reason: str
    liquidity_score: float
    ref_price: float
    stable_variant_id: str = ""

    @property
    def identity(self) -> tuple[int, str]:
        return self.cm_product_id, self.variant_key


@dataclass(frozen=True)
class RemovedConstituent:
    cm_product_id: int
    variant_key: str
    action: str
    reason: str
    stable_variant_id: str


@dataclass(frozen=True)
class SelectionResult:
    constituents: list[Constituent]
    removed: list[RemovedConstituent]
    eligible_count: int
    snapshot_sha256: str


def _catalogue_dates(products: pl.DataFrame) -> dict[int, date | None]:
    if products.is_empty():
        return {}
    dates: dict[int, date | None] = {}
    for row in products.select("cm_product_id", "source_date_added", "first_seen").iter_rows(
        named=True
    ):
        raw = row.get("source_date_added") or row.get("first_seen")
        try:
            dates[int(row["cm_product_id"])] = date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            dates[int(row["cm_product_id"])] = None
    return dates


def _snapshot_sha(rows: list[dict[str, object]], definition: IndexDefinition) -> str:
    body = json.dumps(
        {"index_code": definition.code, "eligible": rows},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return sha256_hex(body)


def select_constituents(
    prices: pl.DataFrame,
    products: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    effective_date: date,
    incumbents: set[tuple[int, str]] | None = None,
    *,
    expected_days: int | None = None,
    minimum_history_days: int | None = None,
) -> SelectionResult:
    incumbents = incumbents or set()
    if prices.is_empty():
        return SelectionResult(
            [],
            _removed_records(incumbents, {}, definition),
            0,
            _snapshot_sha([], definition),
        )

    lookback_start = effective_date - timedelta(days=methodology.selection_lookback_days)
    product_kind = "sealed" if definition.universe == "sealed" else "single"
    window = prices.filter(
        (pl.col("value_date") >= lookback_start)
        & (pl.col("value_date") < effective_date)
        & (pl.col("product_kind") == product_kind)
    )
    if window.is_empty():
        return SelectionResult(
            [],
            _removed_records(incumbents, {}, definition),
            0,
            _snapshot_sha([], definition),
        )
    if "stable_variant_id" not in window.columns:
        window = window.with_columns(
            (
                pl.lit(f"cardmarket:{definition.game_key}:product:")
                + pl.col("cm_product_id").cast(pl.String)
                + pl.lit(":")
                + pl.col("variant_key")
            ).alias("stable_variant_id")
        )

    min_price = methodology.min_price_eur[definition.universe]
    scoring_days = expected_days or methodology.selection_lookback_days
    required_history_days = (
        minimum_history_days
        if minimum_history_days is not None
        else methodology.min_history_days
    )
    scores = score_liquidity(window, scoring_days, min_price)
    seasoning_cutoff = effective_date - timedelta(days=methodology.seasoning_days)
    product_dates = _catalogue_dates(products)
    eligible_rows = []
    for row in scores.iter_rows(named=True):
        added_on = product_dates.get(int(row["cm_product_id"]))
        if added_on is None or added_on > seasoning_cutoff:
            continue
        if int(row["history_days"]) < required_history_days:
            continue
        if float(row["observation_ratio"]) < methodology.min_observation_ratio:
            continue
        if float(row["price_floor_ratio"]) < methodology.price_floor_observation_ratio:
            continue
        if float(row["suspect_zero_ratio"]) > methodology.max_suspect_zero_ratio:
            continue
        eligible_rows.append(row)

    if methodology.selection_rank != "reference_price_descending":
        raise ValueError(f"unsupported selection rank {methodology.selection_rank}")
    ranking_field = methodology.ranking_price_field
    if ranking_field not in scores.columns:
        raise ValueError(f"ranking price field {ranking_field} is unavailable")
    eligible_rows.sort(
        key=lambda row: (
            -float(row[ranking_field]),
            -float(row["liquidity_score"]),
            str(row["stable_variant_id"]),
        )
    )
    distinct_products: list[dict[str, Any]] = []
    seen_product_ids: set[int] = set()
    for row in eligible_rows:
        product_id = int(row["cm_product_id"])
        if product_id in seen_product_ids:
            continue
        distinct_products.append(row)
        seen_product_ids.add(product_id)
    eligible_rows = distinct_products
    snapshot_rows = [
        {
            "stable_variant_id": str(row["stable_variant_id"]),
            "reference_price": round(float(row[ranking_field]), 8),
            "liquidity_score": round(float(row["liquidity_score"]), 12),
        }
        for row in eligible_rows
    ]
    snapshot_sha = _snapshot_sha(snapshot_rows, definition)
    if not eligible_rows:
        return SelectionResult(
            [], _removed_records(incumbents, {}, definition), 0, snapshot_sha
        )

    ranked = [(rank, row) for rank, row in enumerate(eligible_rows, start=1)]
    selected_ranked = ranked[: definition.target_size]

    constituents: list[Constituent] = []
    for rank, row in selected_ranked:
        identity = _identity(row)
        if identity in incumbents:
            action = "retained"
            reason = f"incumbent retained at reference-price rank {rank}"
        else:
            action = "added"
            reason = f"entrant selected at reference-price rank {rank}"
        constituents.append(
            Constituent(
                cm_product_id=identity[0],
                variant_key=identity[1],
                action=action,
                reason=reason,
                liquidity_score=float(row["liquidity_score"]),
                ref_price=float(row[ranking_field]),
                stable_variant_id=str(row["stable_variant_id"]),
            )
        )

    rank_by_identity = {_identity(row): rank for rank, row in ranked}
    removed = _removed_records(
        incumbents - {item.identity for item in constituents},
        rank_by_identity,
        definition,
    )
    return SelectionResult(constituents, removed, len(eligible_rows), snapshot_sha)


def _identity(row: dict[str, Any]) -> tuple[int, str]:
    return int(row["cm_product_id"]), str(row["variant_key"])


def _removed_records(
    identities: set[tuple[int, str]],
    ranks: dict[tuple[int, str], int],
    definition: IndexDefinition,
) -> list[RemovedConstituent]:
    records = []
    for product_id, variant_key in sorted(identities):
        rank = ranks.get((product_id, variant_key))
        reason = (
            f"incumbent removed at reference-price rank {rank} outside top {definition.target_size}"
            if rank is not None
            else "incumbent removed after failing current eligibility gates"
        )
        records.append(
            RemovedConstituent(
                cm_product_id=product_id,
                variant_key=variant_key,
                action="removed",
                reason=reason,
                stable_variant_id=(
                    f"cardmarket:{definition.game_key}:product:{product_id}:{variant_key}"
                ),
            )
        )
    return records


def selection_as_dict(result: SelectionResult) -> dict[str, object]:
    return {
        "constituents": [asdict(item) for item in result.constituents],
        "removed": [asdict(item) for item in result.removed],
        "eligible_count": result.eligible_count,
        "snapshot_sha256": result.snapshot_sha256,
    }
