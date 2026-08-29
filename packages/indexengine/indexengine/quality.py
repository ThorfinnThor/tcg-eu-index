from __future__ import annotations

import polars as pl

IDENTITY_COLUMNS = ["stable_variant_id", "cm_product_id", "variant_key"]


def score_data_quality(
    prices: pl.DataFrame,
    expected_days: int,
    *,
    valuation_field: str = "avg30",
    selection_price_field: str = "avg30",
) -> pl.DataFrame:
    """Calculate v1.5 data-quality diagnostics without implying market liquidity."""
    if prices.is_empty() or expected_days <= 0:
        return pl.DataFrame()

    required = {*IDENTITY_COLUMNS, "value_date"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"data-quality input is missing columns: {', '.join(sorted(missing))}")

    frame = prices
    numeric_fields = {valuation_field, selection_price_field, "price_avg", "price_low"}
    for field in numeric_fields:
        if field not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(pl.Float64).alias(field))
    frame = (
        frame.unique([*IDENTITY_COLUMNS, "value_date"], keep="last")
        .sort([*IDENTITY_COLUMNS, "value_date"])
        .with_columns(
            pl.col(valuation_field).cast(pl.Float64, strict=False).alias("valuation_price"),
            pl.col(selection_price_field).cast(pl.Float64, strict=False).alias("selection_price"),
            pl.col("price_avg").cast(pl.Float64, strict=False),
            pl.col("price_low").cast(pl.Float64, strict=False),
        )
        .with_columns(
            (pl.col("valuation_price").is_not_null() & (pl.col("valuation_price") > 0)).alias(
                "has_valuation_price"
            ),
            (pl.col("selection_price").is_not_null() & (pl.col("selection_price") > 0)).alias(
                "has_selection_price"
            ),
            (pl.col("valuation_price").is_not_null() & (pl.col("valuation_price") <= 0)).alias(
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
                pl.col("valuation_price").is_not_null()
                & pl.col("valuation_price").shift(1).over(IDENTITY_COLUMNS).is_not_null()
                & (
                    pl.col("valuation_price")
                    != pl.col("valuation_price").shift(1).over(IDENTITY_COLUMNS)
                )
            ).alias("valuation_price_changed")
        )
    )

    denominator = float(expected_days)
    change_denominator = float(max(expected_days - 1, 1))
    return (
        frame.group_by(IDENTITY_COLUMNS)
        .agg(
            pl.col("valuation_price").is_not_null().sum().alias("history_days"),
            pl.col("has_valuation_price").sum().alias("valuation_observation_days"),
            pl.col("has_selection_price").sum().alias("selection_price_observation_days"),
            pl.col("suspect_zero").sum().alias("suspect_zero_days"),
            pl.col("valuation_price_changed").sum().alias("price_update_days"),
            pl.col("inverse_dispersion_day").mean().alias("inverse_dispersion"),
            pl.col("value_date").min().alias("first_observation_date"),
            pl.col("value_date").max().alias("last_observation_date"),
            pl.col("valuation_price").drop_nulls().last().alias("latest_valuation_price"),
            pl.col("selection_price").drop_nulls().last().alias("latest_selection_price"),
        )
        .with_columns(
            (pl.col("valuation_observation_days") / denominator).alias(
                "valuation_observation_ratio"
            ),
            (pl.col("selection_price_observation_days") / denominator).alias(
                "selection_price_observation_ratio"
            ),
            (pl.col("suspect_zero_days") / denominator).alias("suspect_zero_ratio"),
            (pl.col("price_update_days") / change_denominator).alias("price_update_frequency"),
        )
        .with_columns(
            (
                0.5 * pl.col("valuation_observation_ratio")
                + 0.3 * pl.col("price_update_frequency")
                + 0.2 * pl.col("inverse_dispersion")
            )
            .clip(0, 1)
            .alias("data_quality_score")
        )
        .sort("stable_variant_id")
    )
