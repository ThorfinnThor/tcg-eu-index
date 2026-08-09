from __future__ import annotations

import polars as pl


def score_liquidity(prices: pl.DataFrame) -> pl.DataFrame:
    if prices.is_empty():
        return pl.DataFrame()
    frame = prices.with_columns(
        [
            pl.col("price_avg").is_not_null().alias("has_price"),
            (
                1
                - (
                    (pl.col("price_low") - pl.col("price_avg")).abs()
                    / pl.when(pl.col("price_avg") <= 0).then(None).otherwise(pl.col("price_avg"))
                ).clip(0, 1)
            ).fill_null(0).alias("inverse_dispersion_day"),
        ]
    )
    changes = frame.sort("value_date").with_columns(
        (pl.col("price_avg") != pl.col("price_avg").shift(1))
        .over(["cm_product_id", "variant_key"])
        .fill_null(False)
        .alias("changed")
    )
    return changes.group_by(["cm_product_id", "variant_key"]).agg(
        [
            pl.col("has_price").mean().alias("observation_ratio"),
            pl.col("changed").mean().alias("price_update_frequency"),
            pl.col("inverse_dispersion_day").mean().alias("inverse_dispersion"),
            pl.col("price_avg").mean().alias("avg30"),
        ]
    ).with_columns(
        (
            0.5 * pl.col("observation_ratio")
            + 0.3 * pl.col("price_update_frequency")
            + 0.2 * pl.col("inverse_dispersion")
        ).alias("liquidity_score")
    )
