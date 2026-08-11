from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import polars as pl


class DailyValueLike(Protocol):
    @property
    def value_date(self) -> str: ...

    @property
    def index_value(self) -> float: ...

    @property
    def daily_return(self) -> float: ...

    @property
    def whole_market_carried_forward(self) -> bool: ...


class ContributionLike(Protocol):
    @property
    def value_date(self) -> str: ...

    @property
    def stable_variant_id(self) -> str: ...

    @property
    def cm_product_id(self) -> int: ...

    @property
    def variant_key(self) -> str: ...

    @property
    def used_return(self) -> float: ...

    @property
    def contribution(self) -> float: ...

    @property
    def flag(self) -> str: ...


@dataclass(frozen=True)
class RankedMetric:
    stable_variant_id: str
    cm_product_id: int
    variant_key: str
    product_name: str
    value: float
    observation_days: int


@dataclass(frozen=True)
class WindowAnalytics:
    window: str
    start_date: str
    observation_dates: int
    excluded_whole_market_dates: int
    constituent_observations: int
    top_movers: list[RankedMetric]
    bottom_movers: list[RankedMetric]
    contribution_leaders: list[RankedMetric]
    contribution_laggards: list[RankedMetric]


@dataclass(frozen=True)
class DailyAnalytics:
    value_date: str
    index_value: float
    daily_return: float
    drawdown: float
    volatility_30d: float | None
    volatility_observations: int
    breadth_7d: float | None
    breadth_observations: int
    whole_market_carried_forward: bool
    windows: list[WindowAnalytics]


@dataclass
class _Aggregate:
    stable_variant_id: str
    cm_product_id: int
    variant_key: str
    compounded_return: float = 0.0
    contribution: float = 0.0
    observation_days: int = 0


def calculate_analytics(
    values: Sequence[DailyValueLike],
    contributions: Sequence[ContributionLike],
    products: pl.DataFrame,
    windows: tuple[int, ...] = (1, 7, 30),
    ranking_limit: int = 10,
) -> list[DailyAnalytics]:
    """Calculate private aggregate analytics without exposing source prices."""
    if not values:
        return []
    if any(window <= 0 for window in windows):
        raise ValueError("analytics windows must be positive")
    if ranking_limit <= 0:
        raise ValueError("ranking_limit must be positive")

    ordered_values = sorted(values, key=lambda item: item.value_date)
    values_by_date = {date.fromisoformat(item.value_date): item for item in ordered_values}
    contributions_by_date: dict[date, list[ContributionLike]] = {}
    for item in contributions:
        contributions_by_date.setdefault(date.fromisoformat(item.value_date), []).append(item)
    product_names = _product_names(products)

    peak = -math.inf
    result: list[DailyAnalytics] = []
    for value in ordered_values:
        value_date = date.fromisoformat(value.value_date)
        peak = max(peak, value.index_value)
        drawdown = value.index_value / peak - 1 if peak > 0 else 0.0

        window_records: list[WindowAnalytics] = []
        aggregates_by_window: dict[int, dict[str, _Aggregate]] = {}
        for window in windows:
            start_date = value_date - timedelta(days=window - 1)
            aggregates, observation_dates, excluded_dates = _window_aggregates(
                contributions_by_date,
                values_by_date,
                start_date,
                value_date,
            )
            aggregates_by_window[window] = aggregates
            window_records.append(
                _window_record(
                    window,
                    start_date,
                    aggregates,
                    observation_dates,
                    excluded_dates,
                    product_names,
                    ranking_limit,
                )
            )

        breadth_source = aggregates_by_window.get(7, {})
        breadth_observations = len(breadth_source)
        breadth_7d = (
            sum(item.compounded_return > 0 for item in breadth_source.values())
            / breadth_observations
            if breadth_observations
            else None
        )
        volatility_returns = [
            item.daily_return
            for item in ordered_values
            if value_date - timedelta(days=29)
            <= date.fromisoformat(item.value_date)
            <= value_date
        ]
        volatility = (
            statistics.stdev(volatility_returns) * math.sqrt(365)
            if len(volatility_returns) >= 2
            else None
        )
        result.append(
            DailyAnalytics(
                value_date=value.value_date,
                index_value=value.index_value,
                daily_return=value.daily_return,
                drawdown=drawdown,
                volatility_30d=volatility,
                volatility_observations=len(volatility_returns),
                breadth_7d=breadth_7d,
                breadth_observations=breadth_observations,
                whole_market_carried_forward=value.whole_market_carried_forward,
                windows=window_records,
            )
        )
    return result


def _window_aggregates(
    contributions_by_date: dict[date, list[ContributionLike]],
    values_by_date: dict[date, DailyValueLike],
    start_date: date,
    end_date: date,
) -> tuple[dict[str, _Aggregate], int, int]:
    aggregates: dict[str, _Aggregate] = {}
    observation_dates = 0
    excluded_dates = 0
    cursor = start_date
    while cursor <= end_date:
        day_value = values_by_date.get(cursor)
        if day_value is not None and day_value.whole_market_carried_forward:
            excluded_dates += 1
            cursor += timedelta(days=1)
            continue
        day_rows = [
            item
            for item in contributions_by_date.get(cursor, [])
            if item.flag != "snapshot_unchanged"
        ]
        if day_rows:
            observation_dates += 1
        for item in day_rows:
            aggregate = aggregates.setdefault(
                item.stable_variant_id,
                _Aggregate(
                    stable_variant_id=item.stable_variant_id,
                    cm_product_id=item.cm_product_id,
                    variant_key=item.variant_key,
                ),
            )
            aggregate.compounded_return = (
                (1 + aggregate.compounded_return) * (1 + item.used_return) - 1
            )
            aggregate.contribution += item.contribution
            aggregate.observation_days += 1
        cursor += timedelta(days=1)
    return aggregates, observation_dates, excluded_dates


def _window_record(
    window: int,
    start_date: date,
    aggregates: dict[str, _Aggregate],
    observation_dates: int,
    excluded_dates: int,
    product_names: dict[int, str],
    ranking_limit: int,
) -> WindowAnalytics:
    returns = [
        _ranked_metric(item, item.compounded_return, product_names)
        for item in aggregates.values()
    ]
    contribution_totals = [
        _ranked_metric(item, item.contribution, product_names) for item in aggregates.values()
    ]
    return WindowAnalytics(
        window=f"{window}d",
        start_date=start_date.isoformat(),
        observation_dates=observation_dates,
        excluded_whole_market_dates=excluded_dates,
        constituent_observations=len(aggregates),
        top_movers=_rank(returns, ranking_limit, descending=True),
        bottom_movers=_rank(returns, ranking_limit, descending=False),
        contribution_leaders=_rank(contribution_totals, ranking_limit, descending=True),
        contribution_laggards=_rank(contribution_totals, ranking_limit, descending=False),
    )


def _ranked_metric(
    aggregate: _Aggregate,
    value: float,
    product_names: dict[int, str],
) -> RankedMetric:
    return RankedMetric(
        stable_variant_id=aggregate.stable_variant_id,
        cm_product_id=aggregate.cm_product_id,
        variant_key=aggregate.variant_key,
        product_name=product_names.get(
            aggregate.cm_product_id, f"Product {aggregate.cm_product_id}"
        ),
        value=value,
        observation_days=aggregate.observation_days,
    )


def _rank(
    records: list[RankedMetric], ranking_limit: int, *, descending: bool
) -> list[RankedMetric]:
    if descending:
        return sorted(records, key=lambda item: (-item.value, item.stable_variant_id))[
            :ranking_limit
        ]
    return sorted(records, key=lambda item: (item.value, item.stable_variant_id))[:ranking_limit]


def _product_names(products: pl.DataFrame) -> dict[int, str]:
    if products.is_empty() or not {"cm_product_id", "name"}.issubset(products.columns):
        return {}
    return {
        int(row["cm_product_id"]): str(row["name"])
        for row in products.select("cm_product_id", "name").iter_rows(named=True)
    }
