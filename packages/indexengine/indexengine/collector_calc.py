from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import polars as pl

from indexengine.eligibility import (
    CollectorEligibilityResult,
    DataState,
    evaluate_collector_eligibility,
)
from indexengine.methodology import (
    IndexDefinition,
    Methodology,
    MethodologyCalculation,
    MethodologyConfigError,
)

Identity = tuple[int, str]
PriceState = Literal[
    "initialized",
    "fresh",
    "fresh_after_carry",
    "fresh_after_suspension",
    "spike_capped",
    "carried_forward",
    "suspended_stale",
    "snapshot_unchanged",
]


@dataclass(frozen=True)
class CollectorMember:
    cm_product_id: int
    variant_key: str
    stable_variant_id: str
    selection_price: float

    @property
    def identity(self) -> Identity:
        return self.cm_product_id, self.variant_key


@dataclass(frozen=True)
class CollectorRebalance:
    effective_date: date
    selection_as_of: date
    methodology_version: str
    selection_snapshot_sha256: str
    eligible_count: int
    constituents: tuple[CollectorMember, ...]


@dataclass(frozen=True)
class CollectorDailyValue:
    value_date: date
    index_value: float | None
    daily_return: float | None
    status: Literal["active", "empty_eligible_universe"]
    constituent_count: int
    fresh_count: int
    capped_count: int
    carried_count: int
    suspended_count: int
    capped_weight_share: float
    carried_weight_share: float
    suspended_weight_share: float
    largest_end_weight: float
    whole_market_carried_forward: bool
    rebalance_effective_date: date
    selection_as_of: date
    methodology_version: str


@dataclass(frozen=True)
class CollectorContribution:
    value_date: date
    stable_variant_id: str
    cm_product_id: int
    variant_key: str
    target_weight: float | None
    weight_before: float
    raw_return: float | None
    used_return: float
    contribution: float
    weight_after: float
    valuation_price: float | None
    price_state: PriceState
    capped: bool


@dataclass
class _PriceMemory:
    price: float
    value_date: date
    previous_state: PriceState = "fresh"


@dataclass(frozen=True)
class _DayReturn:
    member: CollectorMember
    weight_before: float
    target_weight: float | None
    raw_return: float | None
    used_return: float
    valuation_price: float | None
    price_state: PriceState
    capped: bool


def collector_rebalance_from_eligibility(
    result: CollectorEligibilityResult,
    *,
    selection_as_of: date,
) -> CollectorRebalance:
    """Freeze one S2 eligibility result as a monthly S3 composition."""
    if selection_as_of >= result.effective_date:
        raise ValueError("selection_as_of must precede the rebalance effective date")
    members: list[CollectorMember] = []
    for item in result.eligible_variants:
        if item.reference_price is None or not _is_positive_finite(item.reference_price):
            raise ValueError(f"eligible variant {item.stable_variant_id} has no selection price")
        members.append(
            CollectorMember(
                cm_product_id=item.cm_product_id,
                variant_key=item.variant_key,
                stable_variant_id=item.stable_variant_id,
                selection_price=item.reference_price,
            )
        )
    return CollectorRebalance(
        effective_date=result.effective_date,
        selection_as_of=selection_as_of,
        methodology_version=result.methodology_version,
        selection_snapshot_sha256=result.snapshot_sha256,
        eligible_count=len(members),
        constituents=tuple(sorted(members, key=lambda item: item.stable_variant_id)),
    )


def build_monthly_collector_rebalances(
    prices: pl.DataFrame,
    products: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    calendar_dates: list[date],
    *,
    unchanged_dates: set[date] | None = None,
    data_state: DataState = "official",
) -> list[CollectorRebalance]:
    """Evaluate and freeze the first shadow basket and later monthly baskets."""
    _validate_contract(definition, methodology)
    quality = methodology.quality
    if quality is None:
        raise MethodologyConfigError("collector rebalance scheduling requires v1.5 quality")
    calendar = sorted(set(calendar_dates))
    if len(calendar) < 2:
        return []

    monthly_first: list[date] = []
    seen_months: set[tuple[int, int]] = set()
    for value in calendar:
        month = value.year, value.month
        if month not in seen_months:
            monthly_first.append(value)
            seen_months.add(month)

    def freeze(effective_date: date) -> CollectorRebalance | None:
        prior_dates = [value for value in calendar if value < effective_date]
        if not prior_dates:
            return None
        result = evaluate_collector_eligibility(
            prices,
            products,
            definition,
            methodology,
            effective_date,
            calendar_dates=calendar,
            unchanged_dates=unchanged_dates,
            data_state=data_state,
        )
        return collector_rebalance_from_eligibility(
            result,
            selection_as_of=prior_dates[-1],
        )

    if data_state == "official":
        return [
            frozen
            for effective_date in monthly_first
            if (frozen := freeze(effective_date)) is not None
        ]

    candidates = [
        value
        for value in calendar
        if _prior_lookback_count(calendar, value, quality.selection_lookback_days)
        >= quality.shadow_min_history_days
    ]
    last_empty: CollectorRebalance | None = None
    first_shadow: CollectorRebalance | None = None
    for effective_date in candidates:
        frozen = freeze(effective_date)
        if frozen is None:
            continue
        if frozen.constituents:
            first_shadow = frozen
            break
        last_empty = frozen
    if first_shadow is None:
        return [] if last_empty is None else [last_empty]

    rebalances = [first_shadow]
    for effective_date in monthly_first:
        if (effective_date.year, effective_date.month) <= (
            first_shadow.effective_date.year,
            first_shadow.effective_date.month,
        ):
            continue
        frozen = freeze(effective_date)
        if frozen is not None:
            rebalances.append(frozen)
    return rebalances


def calculate_collector_chain_linked(
    prices: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    rebalances: list[CollectorRebalance],
    calendar_dates: list[date],
    *,
    unchanged_dates: set[date] | None = None,
) -> tuple[list[CollectorDailyValue], list[CollectorContribution]]:
    """Calculate the schema-v2 collector series without changing the legacy engine."""
    calculation = _validate_contract(definition, methodology)
    ordered_rebalances = _validate_rebalances(rebalances, methodology.methodology_version)
    if not ordered_rebalances:
        return [], []
    ordered_calendar = sorted(set(calendar_dates))
    _validate_rebalance_calendar(
        ordered_rebalances,
        ordered_calendar,
        allow_late_first=methodology.methodology_state == "private_shadow",
    )
    prices_by_day = _price_rows(prices, definition, calculation.valuation_price_field)
    unchanged = unchanged_dates or set()
    active_rebalance: CollectorRebalance | None = None
    members: dict[Identity, CollectorMember] = {}
    weights: dict[Identity, float] = {}
    memory: dict[Identity, _PriceMemory] = {}
    rebalance_cursor = 0
    index_value: float | None = None
    daily_values: list[CollectorDailyValue] = []
    contributions: list[CollectorContribution] = []

    for value_date in ordered_calendar:
        applied_rebalance = False
        while (
            rebalance_cursor < len(ordered_rebalances)
            and ordered_rebalances[rebalance_cursor].effective_date <= value_date
        ):
            active_rebalance = ordered_rebalances[rebalance_cursor]
            members = {item.identity: item for item in active_rebalance.constituents}
            weights = _equal_weights(members)
            memory = {
                identity: _PriceMemory(member.selection_price, active_rebalance.selection_as_of)
                for identity, member in members.items()
            }
            rebalance_cursor += 1
            applied_rebalance = True
        if active_rebalance is None:
            continue
        if not members:
            daily_values.append(
                _empty_daily_value(value_date, active_rebalance, methodology.methodology_version)
            )
            continue

        if index_value is None:
            day_returns = _initialize_series_day(
                value_date,
                members,
                weights,
                memory,
                prices_by_day.get(value_date, {}),
                applied_rebalance,
            )
            index_value = definition.base_value
            end_weights = dict(weights)
            daily_return = 0.0
        else:
            day_returns = _calculate_day_returns(
                value_date,
                members,
                weights,
                memory,
                prices_by_day.get(value_date, {}),
                calculation,
                value_date in unchanged,
                applied_rebalance,
            )
            daily_return = sum(item.weight_before * item.used_return for item in day_returns)
            denominator = 1.0 + daily_return
            if denominator <= 0 or not math.isfinite(denominator):
                raise ValueError(f"invalid collector return denominator on {value_date}")
            index_value *= denominator
            end_weights = {
                item.member.identity: item.weight_before * (1.0 + item.used_return) / denominator
                for item in day_returns
            }
            _assert_weight_total(end_weights, value_date)

        contributions.extend(
            _contribution_records(value_date, day_returns, end_weights)
        )
        daily_values.append(
            _daily_value(
                value_date,
                index_value,
                daily_return,
                day_returns,
                end_weights,
                active_rebalance,
                methodology.methodology_version,
                value_date in unchanged,
            )
        )
        weights = end_weights

    return daily_values, contributions


def _validate_contract(
    definition: IndexDefinition, methodology: Methodology
) -> MethodologyCalculation:
    calculation = methodology.calculation
    if methodology.schema_version != 2 or calculation is None or definition.family is None:
        raise MethodologyConfigError("collector calculation requires a schema-v2 index family")
    expected = (
        calculation.weighting == "equal_weight_at_monthly_rebalance",
        calculation.rebalance == "monthly",
        calculation.rebalance_effective_day == "first_observable_source_day",
        calculation.price_fallback is None,
        calculation.stale_policy == "suspend_at_last_valid_price",
    )
    if not all(expected):
        raise MethodologyConfigError("unsupported collector calculation contract")
    try:
        family = methodology.families[definition.family]
    except KeyError as exc:
        raise MethodologyConfigError(f"unknown collector family {definition.family}") from exc
    if family.valuation_price_field != calculation.valuation_price_field:
        raise MethodologyConfigError("family and calculation valuation fields must match")
    return calculation


def _validate_rebalances(
    rebalances: list[CollectorRebalance], methodology_version: str
) -> list[CollectorRebalance]:
    ordered = sorted(rebalances, key=lambda item: item.effective_date)
    dates: set[date] = set()
    for item in ordered:
        if item.effective_date in dates:
            raise ValueError(f"duplicate collector rebalance date {item.effective_date}")
        if item.selection_as_of >= item.effective_date:
            raise ValueError("collector selection date must precede its effective date")
        if item.methodology_version != methodology_version:
            raise ValueError("collector rebalance methodology version mismatch")
        identities = [member.identity for member in item.constituents]
        if len(identities) != len(set(identities)):
            raise ValueError(f"duplicate collector identity on {item.effective_date}")
        if item.eligible_count != len(item.constituents):
            raise ValueError("collector rebalance eligible count does not match membership")
        dates.add(item.effective_date)
    return ordered


def _validate_rebalance_calendar(
    rebalances: list[CollectorRebalance],
    calendar_dates: list[date],
    *,
    allow_late_first: bool,
) -> None:
    calendar = set(calendar_dates)
    for position, item in enumerate(rebalances):
        if item.effective_date not in calendar:
            raise ValueError(f"collector effective date {item.effective_date} is not observable")
        prior_dates = [value for value in calendar_dates if value < item.effective_date]
        if not prior_dates or item.selection_as_of != prior_dates[-1]:
            raise ValueError(
                f"collector selection_as_of for {item.effective_date} is not the last "
                "observable source day"
            )
        month_dates = [
            value
            for value in calendar_dates
            if value.year == item.effective_date.year and value.month == item.effective_date.month
        ]
        if not month_dates:
            raise ValueError(
                f"collector rebalance month {item.effective_date:%Y-%m} is unobservable"
            )
        if (position > 0 or not allow_late_first) and item.effective_date != month_dates[0]:
            raise ValueError(
                f"collector effective date {item.effective_date} is not the first observable "
                "source day of its month"
            )


def _price_rows(
    prices: pl.DataFrame,
    definition: IndexDefinition,
    valuation_field: str,
) -> dict[date, dict[Identity, float | None]]:
    required = {"value_date", "cm_product_id", "variant_key", valuation_field}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"collector price input is missing columns: {', '.join(sorted(missing))}")
    frame = prices
    if "game_key" in frame.columns:
        frame = frame.filter(pl.col("game_key") == definition.game_key)
    if "product_kind" in frame.columns:
        product_kind = "sealed" if definition.universe == "sealed" else "single"
        frame = frame.filter(pl.col("product_kind") == product_kind)
    result: dict[date, dict[Identity, float | None]] = {}
    for row in frame.sort(["value_date", "cm_product_id", "variant_key"]).iter_rows(named=True):
        value_date = _as_date(row["value_date"])
        identity = int(row["cm_product_id"]), str(row["variant_key"])
        day = result.setdefault(value_date, {})
        if identity in day:
            raise ValueError(f"duplicate collector price row for {identity} on {value_date}")
        day[identity] = _positive_float(row.get(valuation_field))
    return result


def _initialize_series_day(
    value_date: date,
    members: dict[Identity, CollectorMember],
    weights: dict[Identity, float],
    memory: dict[Identity, _PriceMemory],
    day_prices: dict[Identity, float | None],
    applied_rebalance: bool,
) -> list[_DayReturn]:
    result: list[_DayReturn] = []
    for identity in sorted(members):
        price = day_prices.get(identity)
        if price is not None:
            memory[identity] = _PriceMemory(price, value_date, "initialized")
        result.append(
            _DayReturn(
                member=members[identity],
                weight_before=weights[identity],
                target_weight=weights[identity] if applied_rebalance else None,
                raw_return=None,
                used_return=0.0,
                valuation_price=memory[identity].price,
                price_state="initialized",
                capped=False,
            )
        )
    return result


def _calculate_day_returns(
    value_date: date,
    members: dict[Identity, CollectorMember],
    weights: dict[Identity, float],
    memory: dict[Identity, _PriceMemory],
    day_prices: dict[Identity, float | None],
    calculation: MethodologyCalculation,
    unchanged: bool,
    applied_rebalance: bool,
) -> list[_DayReturn]:
    result: list[_DayReturn] = []
    for identity in sorted(members):
        member = members[identity]
        prior = memory[identity]
        target = weights[identity] if applied_rebalance else None
        if unchanged:
            unchanged_state: PriceState = (
                "suspended_stale"
                if prior.previous_state == "suspended_stale"
                else "snapshot_unchanged"
            )
            prior.previous_state = unchanged_state
            result.append(
                _DayReturn(
                    member,
                    weights[identity],
                    target,
                    None,
                    0.0,
                    prior.price,
                    unchanged_state,
                    False,
                )
            )
            continue
        price = day_prices.get(identity)
        if price is None:
            age = (value_date - prior.value_date).days
            state: PriceState = (
                "carried_forward"
                if age <= calculation.carry_forward_max_days
                else "suspended_stale"
            )
            prior.previous_state = state
            result.append(
                _DayReturn(
                    member,
                    weights[identity],
                    target,
                    None,
                    0.0,
                    prior.price,
                    state,
                    False,
                )
            )
            continue

        raw_return = price / prior.price - 1.0
        used_return = min(
            calculation.daily_constituent_return_cap,
            max(-calculation.daily_constituent_return_cap, raw_return),
        )
        capped = not math.isclose(raw_return, used_return, rel_tol=0, abs_tol=1e-15)
        if capped:
            state = "spike_capped"
        elif prior.previous_state == "suspended_stale":
            state = "fresh_after_suspension"
        elif prior.previous_state in {"carried_forward", "snapshot_unchanged"}:
            state = "fresh_after_carry"
        else:
            state = "fresh"
        memory[identity] = _PriceMemory(price, value_date, state)
        result.append(
            _DayReturn(
                member,
                weights[identity],
                target,
                raw_return,
                used_return,
                price,
                state,
                capped,
            )
        )
    return result


def _contribution_records(
    value_date: date,
    day_returns: list[_DayReturn],
    end_weights: dict[Identity, float],
) -> list[CollectorContribution]:
    return [
        CollectorContribution(
            value_date=value_date,
            stable_variant_id=item.member.stable_variant_id,
            cm_product_id=item.member.cm_product_id,
            variant_key=item.member.variant_key,
            target_weight=item.target_weight,
            weight_before=item.weight_before,
            raw_return=item.raw_return,
            used_return=item.used_return,
            contribution=item.weight_before * item.used_return,
            weight_after=end_weights[item.member.identity],
            valuation_price=item.valuation_price,
            price_state=item.price_state,
            capped=item.capped,
        )
        for item in day_returns
    ]


def _daily_value(
    value_date: date,
    index_value: float,
    daily_return: float,
    day_returns: list[_DayReturn],
    end_weights: dict[Identity, float],
    rebalance: CollectorRebalance,
    methodology_version: str,
    whole_market_carried_forward: bool,
) -> CollectorDailyValue:
    carried = {"carried_forward", "snapshot_unchanged"}
    return CollectorDailyValue(
        value_date=value_date,
        index_value=index_value,
        daily_return=daily_return,
        status="active",
        constituent_count=len(day_returns),
        fresh_count=sum(
            item.price_state
            in {
                "initialized",
                "fresh",
                "fresh_after_carry",
                "fresh_after_suspension",
                "spike_capped",
            }
            for item in day_returns
        ),
        capped_count=sum(item.capped for item in day_returns),
        carried_count=sum(item.price_state in carried for item in day_returns),
        suspended_count=sum(item.price_state == "suspended_stale" for item in day_returns),
        capped_weight_share=sum(item.weight_before for item in day_returns if item.capped),
        carried_weight_share=sum(
            item.weight_before for item in day_returns if item.price_state in carried
        ),
        suspended_weight_share=sum(
            item.weight_before for item in day_returns if item.price_state == "suspended_stale"
        ),
        largest_end_weight=max(end_weights.values()),
        whole_market_carried_forward=whole_market_carried_forward,
        rebalance_effective_date=rebalance.effective_date,
        selection_as_of=rebalance.selection_as_of,
        methodology_version=methodology_version,
    )


def _empty_daily_value(
    value_date: date,
    rebalance: CollectorRebalance,
    methodology_version: str,
) -> CollectorDailyValue:
    return CollectorDailyValue(
        value_date=value_date,
        index_value=None,
        daily_return=None,
        status="empty_eligible_universe",
        constituent_count=0,
        fresh_count=0,
        capped_count=0,
        carried_count=0,
        suspended_count=0,
        capped_weight_share=0.0,
        carried_weight_share=0.0,
        suspended_weight_share=0.0,
        largest_end_weight=0.0,
        whole_market_carried_forward=False,
        rebalance_effective_date=rebalance.effective_date,
        selection_as_of=rebalance.selection_as_of,
        methodology_version=methodology_version,
    )


def _equal_weights(members: dict[Identity, CollectorMember]) -> dict[Identity, float]:
    if not members:
        return {}
    target = 1.0 / len(members)
    return {identity: target for identity in members}


def _prior_lookback_count(
    calendar_dates: list[date], effective_date: date, lookback_days: int
) -> int:
    start = date.fromordinal(effective_date.toordinal() - lookback_days)
    return sum(start <= value < effective_date for value in calendar_dates)


def _assert_weight_total(weights: dict[Identity, float], value_date: date) -> None:
    total = sum(weights.values())
    if not math.isclose(total, 1.0, rel_tol=0, abs_tol=1e-12):
        raise AssertionError(f"collector weights sum to {total} on {value_date}")


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _is_positive_finite(value: Any) -> bool:
    return _positive_float(value) is not None


def _positive_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None
