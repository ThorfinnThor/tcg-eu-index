from __future__ import annotations

from datetime import date

import polars as pl

IDENTITY_COLUMNS = ["stable_variant_id", "cm_product_id", "variant_key"]


def score_trading_activity_proxy(
    prices: pl.DataFrame,
    observable_dates: list[date],
    effective_date: date,
    *,
    signal_field: str = "avg1",
) -> pl.DataFrame:
    """Measure positive aggregate avg1 signals; this is not traded volume."""
    dates = sorted(set(observable_dates))
    if prices.is_empty() or not dates:
        return pl.DataFrame()

    required = {*IDENTITY_COLUMNS, "value_date"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"activity input is missing columns: {', '.join(sorted(missing))}")

    frame = prices
    if signal_field not in frame.columns:
        frame = frame.with_columns(pl.lit(None).cast(pl.Float64).alias(signal_field))
    frame = (
        frame.filter(pl.col("value_date").is_in(dates))
        .unique([*IDENTITY_COLUMNS, "value_date"], keep="last")
        .sort([*IDENTITY_COLUMNS, "value_date"])
        .with_columns(pl.col(signal_field).cast(pl.Float64, strict=False).alias("activity_signal"))
        .with_columns(
            (pl.col("activity_signal").is_not_null() & (pl.col("activity_signal") > 0)).alias(
                "positive_activity_signal"
            ),
            (pl.col("activity_signal").is_not_null() & (pl.col("activity_signal") == 0)).alias(
                "zero_activity_signal"
            ),
        )
        .with_columns(
            (
                pl.col("positive_activity_signal")
                & pl.col("positive_activity_signal")
                .shift(1)
                .over(IDENTITY_COLUMNS)
                .fill_null(False)
                & (
                    pl.col("activity_signal")
                    == pl.col("activity_signal").shift(1).over(IDENTITY_COLUMNS)
                )
            ).alias("repeated_positive_activity_signal")
        )
    )
    denominator = float(len(dates))
    return (
        frame.group_by(IDENTITY_COLUMNS)
        .agg(
            pl.col("activity_signal").is_not_null().sum().alias("signal_observation_days"),
            pl.col("positive_activity_signal").sum().alias("activity_days"),
            pl.col("zero_activity_signal").sum().alias("zero_signal_days"),
            pl.col("repeated_positive_activity_signal")
            .sum()
            .alias("repeated_positive_signal_days"),
            pl.when(pl.col("positive_activity_signal"))
            .then(pl.col("value_date"))
            .otherwise(None)
            .drop_nulls()
            .last()
            .alias("last_positive_signal_date"),
            pl.col("activity_signal").drop_nulls().last().alias("latest_activity_signal"),
        )
        .with_columns(
            pl.lit(len(dates)).alias("observable_source_days"),
            (pl.col("activity_days") / denominator).alias("activity_ratio"),
            (pl.col("repeated_positive_signal_days") / denominator).alias(
                "repeated_positive_signal_ratio"
            ),
            (pl.lit(len(dates)) - pl.col("signal_observation_days")).alias(
                "null_or_missing_signal_days"
            ),
            (pl.lit(effective_date) - pl.col("last_positive_signal_date"))
            .dt.total_days()
            .alias("days_since_positive_signal"),
        )
        .sort("stable_variant_id")
    )
