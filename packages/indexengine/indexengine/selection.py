from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl

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


def select_constituents(
    prices: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    effective_date: date,
    incumbents: set[tuple[int, str]] | None = None,
) -> list[Constituent]:
    incumbents = incumbents or set()
    if prices.is_empty():
        return []
    lookback_start = effective_date - timedelta(days=methodology.selection_lookback_days)
    min_price = methodology.min_price_eur[definition.universe]
    window = prices.filter(
        (pl.col("value_date") >= lookback_start)
        & (pl.col("value_date") < effective_date)
        & (pl.col("product_kind") == ("sealed" if definition.universe == "sealed" else "single"))
    )
    scores = score_liquidity(window)
    eligible = scores.filter(
        (pl.col("observation_ratio") >= methodology.min_observation_ratio)
        & (pl.col("avg30") >= min_price)
    ).sort(["liquidity_score", "avg30"], descending=[True, True])
    ranked = eligible.with_row_index("rank", offset=1)
    target = definition.target_size
    retained_cutoff = int(target * 1.2)
    entrant_cutoff = max(1, int(target * 0.9))
    rows = ranked.iter_rows(named=True)
    selected: list[Constituent] = []
    for row in rows:
        identity = (int(row["cm_product_id"]), str(row["variant_key"]))
        rank = int(row["rank"])
        is_incumbent = identity in incumbents
        if is_incumbent and rank <= retained_cutoff:
            action = "retained"
            reason = f"incumbent retained at liquidity rank {rank}"
        elif not is_incumbent and rank <= entrant_cutoff:
            action = "added"
            reason = f"entrant selected at liquidity rank {rank}"
        else:
            continue
        selected.append(
            Constituent(
                cm_product_id=identity[0],
                variant_key=identity[1],
                action=action,
                reason=reason,
                liquidity_score=float(row["liquidity_score"]),
                ref_price=float(row["avg30"]),
            )
        )
        if len(selected) >= target:
            break
    return selected
