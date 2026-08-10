from __future__ import annotations

import polars as pl

IDENTITY_COLUMNS = ["stable_variant_id", "cm_product_id", "variant_key"]


def score_liquidity(
    prices: pl.DataFrame,
    expected_days: int,
    min_price: float,
) -> pl.DataFrame:
    """Score each variant against the complete expected calendar window."""
    if prices.is_empty() or expected_days <= 0:
        return pl.DataFrame()

    frame = (
        prices.sort([*IDENTITY_COLUMNS, "value_date"])
        .with_columns(
            pl.coalesce([pl.col("price_avg"), pl.col("price_low")])
            .cast(pl.Float64)
            .alias("used_price"),
            pl.col("price_avg").cast(pl.Float64),
            pl.col("price_low").cast(pl.Float64),
        )
        .with_columns(
            (pl.col("price_avg").is_not_null() & (pl.col("price_avg") > 0)).alias(
                "has_primary_price"
            ),
            (pl.col("used_price").is_not_null() & (pl.col("used_price") >= min_price)).alias(
                "meets_price_floor"
            ),
            (pl.col("used_price").is_not_null() & (pl.col("used_price") <= 0)).alias(
                "suspect_zero"
            ),
            (
                1
                - (
                    (pl.col("price_low") - pl.col("price_avg")).abs()
                    / pl.when(pl.col("price_avg") <= 0).then(None).otherwise(pl.col("price_avg"))
                ).clip(0, 1)
            )
            .fill_null(0.0)
            .alias("inverse_dispersion_day"),
        )
        .with_columns(
            (
                pl.col("price_avg").is_not_null()
                & pl.col("price_avg").shift(1).over(IDENTITY_COLUMNS).is_not_null()
                & (pl.col("price_avg") != pl.col("price_avg").shift(1).over(IDENTITY_COLUMNS))
            ).alias("primary_changed")
        )
    )

    denominator = float(expected_days)
    change_denominator = float(max(expected_days - 1, 1))
    return (
        frame.group_by(IDENTITY_COLUMNS)
        .agg(
            pl.col("has_primary_price").sum().alias("primary_observation_days"),
            pl.col("meets_price_floor").sum().alias("price_floor_days"),
            pl.col("suspect_zero").sum().alias("suspect_zero_days"),
            pl.col("primary_changed").sum().alias("price_update_days"),
            pl.col("inverse_dispersion_day").mean().alias("inverse_dispersion"),
            pl.col("used_price").is_not_null().sum().alias("history_days"),
            pl.col("value_date").min().alias("first_observation_date"),
            pl.col("value_date").max().alias("last_observation_date"),
            pl.col("avg30").drop_nulls().last().alias("source_avg30"),
            pl.col("used_price").drop_nulls().mean().alias("mean_used_price"),
        )
        .with_columns(
            (pl.col("primary_observation_days") / denominator).alias("observation_ratio"),
            (pl.col("price_floor_days") / denominator).alias("price_floor_ratio"),
            (pl.col("suspect_zero_days") / denominator).alias("suspect_zero_ratio"),
            (pl.col("price_update_days") / change_denominator).alias("price_update_frequency"),
            pl.coalesce([pl.col("source_avg30"), pl.col("mean_used_price")]).alias("avg30"),
        )
        .with_columns(
            (
                0.5 * pl.col("observation_ratio")
                + 0.3 * pl.col("price_update_frequency")
                + 0.2 * pl.col("inverse_dispersion")
            )
            .clip(0, 1)
            .alias("liquidity_score")
        )
        .sort(["liquidity_score", "avg30", "stable_variant_id"], descending=[True, True, False])
    )
