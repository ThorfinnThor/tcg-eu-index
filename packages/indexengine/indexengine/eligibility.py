from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Literal

import polars as pl
from core.r2 import sha256_hex

from indexengine.activity import score_trading_activity_proxy
from indexengine.methodology import (
    IndexDefinition,
    Methodology,
    MethodologyConfigError,
    MethodologyFamily,
)
from indexengine.quality import score_data_quality

DataState = Literal["official", "shadow"]


@dataclass(frozen=True)
class CollectorVariantDiagnostic:
    cm_product_id: int
    variant_key: str
    stable_variant_id: str
    eligible: bool
    exclusion_reasons: tuple[str, ...]
    reference_price: float | None
    history_days: int
    valuation_observation_ratio: float
    selection_price_observation_ratio: float
    suspect_zero_ratio: float
    price_update_frequency: float
    inverse_dispersion: float
    data_quality_score: float
    activity_days: int
    activity_ratio: float
    observable_activity_days: int
    last_positive_avg1_date: date | None
    days_since_positive_avg1: int | None
    repeated_positive_avg1_days: int

    @property
    def identity(self) -> tuple[int, str]:
        return self.cm_product_id, self.variant_key


@dataclass(frozen=True)
class CollectorEligibilityResult:
    index_code: str
    methodology_version: str
    effective_date: date
    data_state: DataState
    required_history_days: int
    quality_calendar_days: int
    activity_observable_days: int
    excluded_unchanged_days: int
    diagnostics: tuple[CollectorVariantDiagnostic, ...]
    eligible_variants: tuple[CollectorVariantDiagnostic, ...]
    snapshot_sha256: str


def evaluate_collector_eligibility(
    prices: pl.DataFrame,
    products: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    effective_date: date,
    *,
    calendar_dates: list[date] | None = None,
    unchanged_dates: set[date] | None = None,
    data_state: DataState = "official",
) -> CollectorEligibilityResult:
    """Evaluate every v1.5 product variant without ranking, caps, or deduplication."""
    family = _collector_family(definition, methodology)
    quality = methodology.quality
    activity = methodology.activity
    source = methodology.source
    if quality is None or activity is None or source is None:
        raise MethodologyConfigError("collector eligibility requires v1.5 quality/activity/source")
    if activity.eligibility_gate_enabled:
        raise MethodologyConfigError(
            "trading activity proxy is diagnostic-only in collector preview methodologies"
        )

    lookback_start = effective_date - timedelta(days=quality.selection_lookback_days)
    product_kind = "sealed" if family.universe == "sealed" else "single"
    window = prices.filter(
        (pl.col("value_date") >= lookback_start)
        & (pl.col("value_date") < effective_date)
        & (pl.col("product_kind") == product_kind)
    )
    if "game_key" in window.columns:
        window = window.filter(pl.col("game_key") == definition.game_key)
    if "stable_variant_id" not in window.columns and not window.is_empty():
        window = window.with_columns(
            (
                pl.lit(f"cardmarket:{definition.game_key}:product:")
                + pl.col("cm_product_id").cast(pl.String)
                + pl.lit(":")
                + pl.col("variant_key")
            ).alias("stable_variant_id")
        )

    quality_dates = _quality_dates(window, lookback_start, effective_date, calendar_dates)
    unchanged = unchanged_dates or set()
    activity_dates = [
        value
        for value in quality_dates
        if not (activity.exclude_unchanged_snapshots and value in unchanged)
    ]
    quality_scores = score_data_quality(
        window,
        len(quality_dates),
        valuation_field=family.valuation_price_field,
        selection_price_field=family.reference_price_field,
    )
    activity_scores = score_trading_activity_proxy(
        window,
        activity_dates,
        effective_date,
        signal_field=activity.signal_field,
    )
    activity_by_identity = {
        (int(row["cm_product_id"]), str(row["variant_key"])): row
        for row in activity_scores.iter_rows(named=True)
    }
    required_history_days = (
        quality.shadow_min_history_days
        if data_state == "shadow"
        else quality.official_min_history_days
    )
    seasoning_cutoff = effective_date - timedelta(days=quality.seasoning_days)
    catalogue_dates = _catalogue_dates(products)
    diagnostics: list[CollectorVariantDiagnostic] = []
    for row in quality_scores.iter_rows(named=True):
        identity = int(row["cm_product_id"]), str(row["variant_key"])
        activity_row = activity_by_identity.get(identity, {})
        reference_price = _positive_finite(row.get("latest_selection_price"))
        reasons: list[str] = []
        added_on = catalogue_dates.get(identity[0])
        if added_on is None:
            reasons.append("missing_seasoning_date")
        elif added_on > seasoning_cutoff:
            reasons.append("seasoning_days")
        if int(row["history_days"]) < required_history_days:
            reasons.append("history_days")
        if float(row["valuation_observation_ratio"]) < quality.min_valuation_observation_ratio:
            reasons.append("valuation_observation_ratio")
        if (
            float(row["selection_price_observation_ratio"])
            < quality.min_selection_price_observation_ratio
        ):
            reasons.append("selection_price_observation_ratio")
        if float(row["suspect_zero_ratio"]) > quality.max_suspect_zero_ratio:
            reasons.append("suspect_zero_ratio")
        if reference_price is None:
            reasons.append("latest_avg30_not_positive")
        elif reference_price < family.min_latest_avg30_eur:
            reasons.append("latest_avg30_below_threshold")

        last_signal = activity_row.get("last_positive_signal_date")
        diagnostic = CollectorVariantDiagnostic(
            cm_product_id=identity[0],
            variant_key=identity[1],
            stable_variant_id=str(row["stable_variant_id"]),
            eligible=not reasons,
            exclusion_reasons=tuple(reasons),
            reference_price=reference_price,
            history_days=int(row["history_days"]),
            valuation_observation_ratio=float(row["valuation_observation_ratio"]),
            selection_price_observation_ratio=float(row["selection_price_observation_ratio"]),
            suspect_zero_ratio=float(row["suspect_zero_ratio"]),
            price_update_frequency=float(row["price_update_frequency"]),
            inverse_dispersion=float(row["inverse_dispersion"]),
            data_quality_score=float(row["data_quality_score"]),
            activity_days=int(activity_row.get("activity_days", 0)),
            activity_ratio=float(activity_row.get("activity_ratio", 0.0)),
            observable_activity_days=len(activity_dates),
            last_positive_avg1_date=(last_signal if isinstance(last_signal, date) else None),
            days_since_positive_avg1=_optional_int(activity_row.get("days_since_positive_signal")),
            repeated_positive_avg1_days=int(activity_row.get("repeated_positive_signal_days", 0)),
        )
        diagnostics.append(diagnostic)

    ordered = tuple(sorted(diagnostics, key=lambda item: item.stable_variant_id))
    eligible = tuple(item for item in ordered if item.eligible)
    snapshot_body = json.dumps(
        {
            "activity_observable_dates": [value.isoformat() for value in activity_dates],
            "data_state": data_state,
            "diagnostics": [_snapshot_record(item) for item in ordered],
            "effective_date": effective_date.isoformat(),
            "index_code": definition.code,
            "methodology_version": methodology.methodology_version,
            "quality_calendar_dates": [value.isoformat() for value in quality_dates],
            "required_history_days": required_history_days,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return CollectorEligibilityResult(
        index_code=definition.code,
        methodology_version=methodology.methodology_version,
        effective_date=effective_date,
        data_state=data_state,
        required_history_days=required_history_days,
        quality_calendar_days=len(quality_dates),
        activity_observable_days=len(activity_dates),
        excluded_unchanged_days=len(set(quality_dates) & unchanged),
        diagnostics=ordered,
        eligible_variants=eligible,
        snapshot_sha256=sha256_hex(snapshot_body),
    )


def eligibility_as_dict(result: CollectorEligibilityResult) -> dict[str, object]:
    return {
        "index_code": result.index_code,
        "methodology_version": result.methodology_version,
        "effective_date": result.effective_date.isoformat(),
        "data_state": result.data_state,
        "required_history_days": result.required_history_days,
        "quality_calendar_days": result.quality_calendar_days,
        "activity_observable_days": result.activity_observable_days,
        "excluded_unchanged_days": result.excluded_unchanged_days,
        "eligible_count": len(result.eligible_variants),
        "diagnostics": [_snapshot_record(item) for item in result.diagnostics],
        "snapshot_sha256": result.snapshot_sha256,
    }


def _collector_family(
    definition: IndexDefinition, methodology: Methodology
) -> MethodologyFamily:
    if methodology.schema_version != 2 or definition.family is None:
        raise MethodologyConfigError("collector eligibility requires a schema v2 index family")
    try:
        family = methodology.families[definition.family]
    except KeyError as exc:
        raise MethodologyConfigError(
            f"index {definition.code} references an unknown family"
        ) from exc
    if family.membership_mode != "all_eligible_variants" or family.target_size is not None:
        raise MethodologyConfigError(
            f"index {definition.code} is not an uncapped all-eligible-variants family"
        )
    if not family.calculation_enabled:
        raise MethodologyConfigError(
            f"index {definition.code} is deferred because family source status is "
            f"{family.source_status!r}"
        )
    return family


def _quality_dates(
    window: pl.DataFrame,
    lookback_start: date,
    effective_date: date,
    calendar_dates: list[date] | None,
) -> list[date]:
    source = calendar_dates
    if source is None:
        source = [] if window.is_empty() else window["value_date"].to_list()
    return sorted(
        {
            value
            for value in source
            if isinstance(value, date) and lookback_start <= value < effective_date
        }
    )


def _catalogue_dates(products: pl.DataFrame) -> dict[int, date | None]:
    if products.is_empty() or "cm_product_id" not in products.columns:
        return {}
    columns = ["cm_product_id"]
    columns.extend(
        column for column in ("source_date_added", "first_seen") if column in products.columns
    )
    result: dict[int, date | None] = {}
    for row in products.select(columns).iter_rows(named=True):
        parsed: date | None = None
        for column in ("source_date_added", "first_seen"):
            raw = row.get(column)
            try:
                parsed = date.fromisoformat(str(raw)[:10]) if raw else None
            except ValueError:
                parsed = None
            if parsed is not None:
                break
        result[int(row["cm_product_id"])] = parsed
    return result


def _positive_finite(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _snapshot_record(item: CollectorVariantDiagnostic) -> dict[str, object]:
    record = asdict(item)
    if item.last_positive_avg1_date is not None:
        record["last_positive_avg1_date"] = item.last_positive_avg1_date.isoformat()
    for key, value in tuple(record.items()):
        if isinstance(value, float):
            record[key] = round(value, 12)
    return record
