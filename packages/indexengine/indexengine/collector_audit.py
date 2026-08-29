from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import click
import polars as pl
from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings
from core.store import ObjectStore
from ingest.manifest import Manifest

from indexengine.collector_calc import (
    CollectorContribution,
    CollectorDailyValue,
    CollectorRebalance,
    build_monthly_collector_rebalances,
    calculate_collector_chain_linked,
)
from indexengine.eligibility import CollectorVariantDiagnostic, evaluate_collector_eligibility
from indexengine.methodology import IndexDefinition, Methodology, MethodologyConfigError


def build_collector_methodology_audit(
    store: ObjectStore,
    methodology: Methodology,
    through_date: date,
) -> dict[str, object]:
    """Build an aggregate-only S4 audit from normalized private R2 inputs."""
    if methodology.schema_version != 2 or methodology.calibration is None:
        raise MethodologyConfigError("collector methodology audit requires schema v2 calibration")
    if "avg7" not in methodology.calibration.alternate_valuation_fields:
        raise MethodologyConfigError("collector methodology audit requires avg7 calibration")

    alternate = _with_valuation_field(methodology, "avg7")
    reports: list[dict[str, object]] = []
    games = sorted({definition.game_key for definition in methodology.indexes})
    archive_days_by_game: dict[str, int] = {}
    for game in games:
        definitions = [item for item in methodology.indexes if item.game_key == game]
        prices = _load_prices(store, game, through_date)
        products = _load_products(store, game)
        calendar_dates, unchanged_dates = _archive_calendar(store, game, through_date)
        archive_days_by_game[game] = len(calendar_dates)
        for definition in definitions:
            family = methodology.families[cast(str, definition.family)]
            if family.calculation_enabled:
                reports.append(
                    _audit_definition(
                        store,
                        prices,
                        products,
                        calendar_dates,
                        unchanged_dates,
                        definition,
                        methodology,
                        alternate,
                        through_date,
                    )
                )
            else:
                reports.append(
                    _deferred_definition_report(
                        store,
                        prices,
                        calendar_dates,
                        unchanged_dates,
                        definition,
                        methodology,
                        through_date,
                    )
                )

    complete_monthly_histories = sum(
        int(cast(dict[str, Any], item["turnover"])["observations"] > 0) for item in reports
    )
    sealed_without_avg30 = [
        str(item["index_code"])
        for item in reports
        if item["universe"] == "sealed"
        and cast(dict[str, Any], cast(dict[str, Any], item["price_fields"])["avg30"])[
            "positive_rate"
        ]
        == 0
    ]
    deferred_indexes = [
        str(item["index_code"])
        for item in reports
        if item["calculation_status"] == "deferred"
    ]
    enabled_sealed_without_avg30 = [
        code for code in sealed_without_avg30 if code not in deferred_indexes
    ]
    methodology_correction_required = bool(enabled_sealed_without_avg30)
    decision = {
        "new_preview_methodology_version_required": methodology_correction_required,
        "methodology_correction_required_before_publication": methodology_correction_required,
        "canonical_valuation_field": "avg30",
        "alternate_valuation_field": "avg7",
        "activity_gate_enabled": False,
        "publication_state": "remain_private_shadow",
        "audit_status": (
            "preliminary_blocked"
            if methodology_correction_required
            else (
                "preliminary_complete_with_deferred_family"
                if deferred_indexes
                else "preliminary_complete"
            )
        ),
        "publication_scope": "enabled_families_only",
        "deferred_indexes": deferred_indexes,
        "source_blockers": {
            "sealed_indexes_without_positive_avg30": sealed_without_avg30,
        },
        "reason": _decision_reason(methodology_correction_required, bool(deferred_indexes)),
    }
    return {
        "schema_version": 1,
        "methodology_version": methodology.methodology_version,
        "through_date": through_date.isoformat(),
        "data_scope": "private_normalized_r2_aggregate_audit",
        "privacy": {
            "contains_raw_prices": False,
            "contains_product_identities": False,
            "contains_aggregate_metrics_only": True,
        },
        "coverage": {
            "games": len(games),
            "indexes": len(reports),
            "enabled_indexes": len(reports) - len(deferred_indexes),
            "deferred_indexes": len(deferred_indexes),
            "archive_days_by_game": archive_days_by_game,
            "indexes_with_monthly_turnover_observations": complete_monthly_histories,
        },
        "decision": decision,
        "indexes": reports,
    }


def render_collector_audit_summary(report: dict[str, object]) -> str:
    decision = cast(dict[str, object], report["decision"])
    lines = [
        "# Collector methodology S4 audit",
        "",
        f"Through: `{report['through_date']}`",
        f"Methodology: `{report['methodology_version']}`",
        "",
        "This report contains aggregate metrics only. It contains no raw prices or "
        "product identities.",
        "",
        "## Decision",
        "",
        "- New preview version required now: "
        f"`{decision['new_preview_methodology_version_required']}`",
        "- Methodology correction required before publication: "
        f"`{decision['methodology_correction_required_before_publication']}`",
        f"- Canonical valuation: `{decision['canonical_valuation_field']}`",
        f"- Activity gate enabled: `{decision['activity_gate_enabled']}`",
        f"- Publication: `{decision['publication_state']}`",
        f"- Audit status: `{decision['audit_status']}`",
        "",
        str(decision["reason"]),
        "",
        "## Index evidence",
        "",
        "| Index | Status | Days | Members | AVG30 return | AVG7 return | Return corr. | "
        "Turnover obs. | Max cap weight | Max carried | Max suspended | v1.4 overlap |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in cast(list[dict[str, Any]], report["indexes"]):
        canonical = cast(dict[str, Any], item["canonical"])
        alternate = cast(dict[str, Any], item["alternate"])
        comparison = cast(dict[str, Any], item["valuation_comparison"])
        turnover = cast(dict[str, Any], item["turnover"])
        missing = cast(dict[str, Any], item["missing_data"])
        legacy = cast(dict[str, Any], item["legacy_comparison"])
        lines.append(
            f"| {item['index_code']} | {item['calculation_status']} | "
            f"{item['archive_days']} | "
            f"{canonical['latest_constituent_count']} | {_pct(canonical['period_return'])} | "
            f"{_pct(alternate['period_return'])} | {_number(comparison['return_correlation'])} | "
            f"{turnover['observations']} | {_pct(canonical['max_capped_weight_share'])} | "
            f"{_pct(missing['max_carried_weight_share'])} | "
            f"{_pct(missing['max_suspended_weight_share'])} | "
            f"{_pct(legacy['collector_member_overlap_ratio'])} |"
        )
    lines.extend(
        [
            "",
            "AVG1 remains a Trading Activity Proxy only. Candidate-gate pass rates in the JSON "
            "are counterfactual diagnostics and do not affect membership.",
        ]
    )
    return "\n".join(lines) + "\n"


def _audit_definition(
    store: ObjectStore,
    prices: pl.DataFrame,
    products: pl.DataFrame,
    calendar_dates: list[date],
    unchanged_dates: set[date],
    definition: IndexDefinition,
    methodology: Methodology,
    alternate: Methodology,
    through_date: date,
) -> dict[str, object]:
    canonical_rebalances = build_monthly_collector_rebalances(
        prices,
        products,
        definition,
        methodology,
        calendar_dates,
        unchanged_dates=unchanged_dates,
        data_state="shadow",
    )
    alternate_rebalances = build_monthly_collector_rebalances(
        prices,
        products,
        definition,
        alternate,
        calendar_dates,
        unchanged_dates=unchanged_dates,
        data_state="shadow",
    )
    canonical_values, canonical_contributions = calculate_collector_chain_linked(
        prices,
        definition,
        methodology,
        canonical_rebalances,
        calendar_dates,
        unchanged_dates=unchanged_dates,
    )
    alternate_values, alternate_contributions = calculate_collector_chain_linked(
        prices,
        definition,
        alternate,
        alternate_rebalances,
        calendar_dates,
        unchanged_dates=unchanged_dates,
    )
    effective_date = through_date + timedelta(days=1)
    diagnostics = evaluate_collector_eligibility(
        prices,
        products,
        definition,
        methodology,
        effective_date,
        calendar_dates=calendar_dates,
        unchanged_dates=unchanged_dates,
        data_state="shadow",
    ).diagnostics
    eligible = tuple(item for item in diagnostics if item.eligible)
    legacy = _legacy_comparison(
        store,
        definition,
        canonical_rebalances,
        canonical_values,
        through_date,
    )
    report = {
        "index_code": definition.code,
        "game_key": definition.game_key,
        "universe": definition.universe,
        "calculation_status": "enabled",
        "archive_days": len(calendar_dates),
        "excluded_unchanged_days": len(set(calendar_dates) & unchanged_dates),
        "price_fields": _price_field_report(prices, definition, methodology, through_date),
        "data_quality": _data_quality_report(diagnostics),
        "activity_proxy": _activity_report(eligible, definition, methodology),
        "canonical": _series_report(
            canonical_rebalances,
            canonical_values,
            canonical_contributions,
        ),
        "alternate": _series_report(
            alternate_rebalances,
            alternate_values,
            alternate_contributions,
        ),
        "valuation_comparison": _series_comparison(canonical_values, alternate_values),
        "turnover": _turnover_report(canonical_rebalances),
        "missing_data": _missing_data_report(canonical_values),
        "legacy_comparison": legacy,
    }
    report["review_flags"] = _review_flags(report)
    return report


def _deferred_definition_report(
    store: ObjectStore,
    prices: pl.DataFrame,
    calendar_dates: list[date],
    unchanged_dates: set[date],
    definition: IndexDefinition,
    methodology: Methodology,
    through_date: date,
) -> dict[str, object]:
    family = methodology.families[cast(str, definition.family)]
    empty_rebalances: list[CollectorRebalance] = []
    empty_values: list[CollectorDailyValue] = []
    empty_contributions: list[CollectorContribution] = []
    report: dict[str, object] = {
        "index_code": definition.code,
        "game_key": definition.game_key,
        "universe": definition.universe,
        "calculation_status": "deferred",
        "source_status": family.source_status,
        "archive_days": len(calendar_dates),
        "excluded_unchanged_days": len(set(calendar_dates) & unchanged_dates),
        "price_fields": _price_field_report(prices, definition, methodology, through_date),
        "data_quality": {
            "diagnostic_variants": 0,
            "eligible_variants": 0,
            "score_all": _distribution([]),
            "score_eligible": _distribution([]),
            "exclusion_reason_counts": {"family_deferred": 1},
        },
        "activity_proxy": {
            "semantics": "not_evaluated_for_deferred_family",
            "hard_gate_enabled": False,
            "eligible_variants": 0,
            "counterfactual_candidate_pass_count": 0,
            "counterfactual_candidate_pass_rate": 0.0,
        },
        "canonical": _series_report(
            empty_rebalances, empty_values, empty_contributions
        ),
        "alternate": _series_report(
            empty_rebalances, empty_values, empty_contributions
        ),
        "valuation_comparison": _series_comparison(empty_values, empty_values),
        "turnover": _turnover_report(empty_rebalances),
        "missing_data": _missing_data_report(empty_values),
        "legacy_comparison": _legacy_comparison(
            store, definition, empty_rebalances, empty_values, through_date
        ),
        "review_flags": [
            "family_deferred",
            "sold_price_avg30_source_unavailable",
            "monthly_turnover_not_yet_observable",
        ],
    }
    return report


def _decision_reason(
    methodology_correction_required: bool, deferred_family_present: bool
) -> str:
    if methodology_correction_required:
        return (
            "At least one sealed index has no positive sold-price AVG30 observations. "
            "The sealed family cannot be published under the current source contract, and a "
            "versioned source or methodology correction is required. Listing-price fallback "
            "remains prohibited. Singles keep AVG30 as canonical, activity remains "
            "diagnostic-only, and final launch review must be repeated after at least 60 "
            "observable days and two monthly compositions."
        )
    if deferred_family_present:
        return (
            "The sealed family is explicitly deferred because the bulk source does not expose "
            "rolling sold-price AVG30 observations for non-singles. Lifetime SELL, TREND, "
            "listing prices, and per-product page scraping are not substituted. Singles keep "
            "AVG30 as canonical, activity remains diagnostic-only, and final launch review "
            "must be repeated after at least 60 observable days and two monthly compositions."
        )
    return (
        "No contract change is justified by the currently available history. Activity remains "
        "diagnostic-only, AVG30 remains canonical, and final launch review must be repeated "
        "after at least 60 observable days and two monthly compositions."
    )


def _with_valuation_field(methodology: Methodology, field: str) -> Methodology:
    if methodology.calculation is None:
        raise MethodologyConfigError("collector calibration requires calculation configuration")
    families = {
        key: replace(family, valuation_price_field=field)
        for key, family in methodology.families.items()
    }
    return replace(
        methodology,
        calculation=replace(methodology.calculation, valuation_price_field=field),
        families=families,
    )


def _load_prices(store: ObjectStore, game: str, through_date: date) -> pl.DataFrame:
    keys = sorted(
        key
        for key in store.list_keys(f"derived/prices/{game}")
        if key.endswith(".parquet") and Path(key).stem <= through_date.strftime("%Y-%m")
    )
    if not keys:
        raise RuntimeError(f"no normalized price history for {game} through {through_date}")
    frames = [pl.read_parquet(BytesIO(store.read_bytes(key))) for key in keys]
    return pl.concat(frames, how="diagonal_relaxed").filter(pl.col("value_date") <= through_date)


def _load_products(store: ObjectStore, game: str) -> pl.DataFrame:
    key = f"derived/catalogue/{game}/products.parquet"
    if not store.exists(key):
        raise RuntimeError(f"missing normalized catalogue {key}")
    return pl.read_parquet(BytesIO(store.read_bytes(key)))


def _archive_calendar(
    store: ObjectStore,
    game: str,
    through_date: date,
) -> tuple[list[date], set[date]]:
    dates: list[date] = []
    unchanged: set[date] = set()
    for key in sorted(store.list_keys("manifests")):
        if not key.endswith(".json"):
            continue
        manifest = Manifest.from_bytes(store.read_bytes(key))
        manifest_date = date.fromisoformat(manifest.run_date)
        if manifest_date > through_date:
            continue
        price_file = next(
            (item for item in manifest.files if item.game == game and item.kind == "priceguide"),
            None,
        )
        if price_file is None:
            continue
        dates.append(manifest_date)
        if price_file.unchanged_from_previous:
            unchanged.add(manifest_date)
    return sorted(set(dates)), unchanged


def _price_field_report(
    prices: pl.DataFrame,
    definition: IndexDefinition,
    methodology: Methodology,
    through_date: date,
) -> dict[str, object]:
    if methodology.quality is None:
        raise MethodologyConfigError("price-field audit requires quality configuration")
    start = through_date - timedelta(days=methodology.quality.selection_lookback_days - 1)
    product_kind = "sealed" if definition.universe == "sealed" else "single"
    frame = prices.filter(
        (pl.col("product_kind") == product_kind)
        & (pl.col("value_date") >= start)
        & (pl.col("value_date") <= through_date)
    )
    return {field: _field_distribution(frame, field) for field in ("avg1", "avg7", "avg30")}


def _field_distribution(frame: pl.DataFrame, field: str) -> dict[str, object]:
    if frame.is_empty() or field not in frame.columns:
        return {
            "rows": frame.height,
            "positive_rate": 0.0,
            "null_or_nonpositive_rate": 1.0 if frame.height else 0.0,
            "p10_positive": None,
            "median_positive": None,
            "p90_positive": None,
        }
    values = frame.select(pl.col(field).cast(pl.Float64, strict=False).alias(field))
    positive = values.filter(pl.col(field).is_not_null() & (pl.col(field) > 0))[field]
    return {
        "rows": frame.height,
        "positive_rate": positive.len() / frame.height if frame.height else 0.0,
        "null_or_nonpositive_rate": 1 - positive.len() / frame.height if frame.height else 0.0,
        "p10_positive": _series_quantile(positive, 0.1),
        "median_positive": _series_quantile(positive, 0.5),
        "p90_positive": _series_quantile(positive, 0.9),
    }


def _data_quality_report(diagnostics: tuple[CollectorVariantDiagnostic, ...]) -> dict[str, object]:
    scores = [item.data_quality_score for item in diagnostics]
    eligible_scores = [item.data_quality_score for item in diagnostics if item.eligible]
    exclusions = Counter(reason for item in diagnostics for reason in item.exclusion_reasons)
    return {
        "diagnostic_variants": len(diagnostics),
        "eligible_variants": len(eligible_scores),
        "score_all": _distribution(scores),
        "score_eligible": _distribution(eligible_scores),
        "exclusion_reason_counts": dict(sorted(exclusions.items())),
    }


def _activity_report(
    eligible: tuple[CollectorVariantDiagnostic, ...],
    definition: IndexDefinition,
    methodology: Methodology,
) -> dict[str, object]:
    if methodology.activity is None:
        raise MethodologyConfigError("activity report requires activity configuration")
    ratio_threshold = methodology.activity.candidate_min_ratio[definition.universe]
    lag_threshold = methodology.activity.candidate_max_days_since_signal[definition.universe]
    candidate_pass = [
        item
        for item in eligible
        if item.activity_ratio >= ratio_threshold
        and item.days_since_positive_avg1 is not None
        and item.days_since_positive_avg1 <= lag_threshold
    ]
    activity_days = sum(item.activity_days for item in eligible)
    repeated = sum(item.repeated_positive_avg1_days for item in eligible)
    return {
        "semantics": "aggregate_positive_avg1_day_proxy_not_transaction_count_or_liquidity",
        "hard_gate_enabled": False,
        "eligible_variants": len(eligible),
        "counterfactual_candidate_ratio": ratio_threshold,
        "counterfactual_candidate_max_days_since_signal": lag_threshold,
        "counterfactual_candidate_pass_count": len(candidate_pass),
        "counterfactual_candidate_pass_rate": (
            len(candidate_pass) / len(eligible) if eligible else 0.0
        ),
        "median_activity_ratio": _median([item.activity_ratio for item in eligible]),
        "repeated_positive_signal_rate": repeated / activity_days if activity_days else 0.0,
    }


def _series_report(
    rebalances: list[CollectorRebalance],
    values: list[CollectorDailyValue],
    contributions: list[CollectorContribution],
) -> dict[str, object]:
    active_values = [item for item in values if item.index_value is not None]
    returns = [float(item.daily_return) for item in active_values if item.daily_return is not None]
    latest_count = len(rebalances[-1].constituents) if rebalances else 0
    period_return = None
    if len(active_values) >= 2:
        first = cast(float, active_values[0].index_value)
        last = cast(float, active_values[-1].index_value)
        period_return = last / first - 1 if first else None
    return {
        "rebalance_count": len(rebalances),
        "latest_constituent_count": latest_count,
        "value_days": len(active_values),
        "period_return": period_return,
        "annualized_volatility": (
            statistics.stdev(returns) * math.sqrt(365) if len(returns) >= 2 else None
        ),
        "max_drawdown": _max_drawdown(active_values),
        "largest_target_weight": 1 / latest_count if latest_count else None,
        "largest_drifted_weight": max(
            (item.largest_end_weight for item in active_values), default=0.0
        ),
        "capped_constituent_days": sum(item.capped_count for item in active_values),
        "max_capped_weight_share": max(
            (item.capped_weight_share for item in active_values), default=0.0
        ),
        "contribution_rows": len(contributions),
    }


def _series_comparison(
    canonical: list[CollectorDailyValue], alternate: list[CollectorDailyValue]
) -> dict[str, object]:
    left = {
        item.value_date: item.daily_return
        for item in canonical
        if item.index_value is not None and item.daily_return is not None
    }
    right = {
        item.value_date: item.daily_return
        for item in alternate
        if item.index_value is not None and item.daily_return is not None
    }
    dates = sorted(set(left) & set(right))
    return {
        "overlap_days": len(dates),
        "return_correlation": _correlation(
            [left[value] for value in dates],
            [right[value] for value in dates],
        ),
    }


def _turnover_report(rebalances: list[CollectorRebalance]) -> dict[str, object]:
    observations = []
    for previous, current in pairwise(rebalances):
        old = {item.stable_variant_id for item in previous.constituents}
        new = {item.stable_variant_id for item in current.constituents}
        old_weight = 1 / len(old) if old else 0.0
        new_weight = 1 / len(new) if new else 0.0
        equal_weight_turnover = 0.5 * sum(
            abs((new_weight if identity in new else 0.0) - (old_weight if identity in old else 0.0))
            for identity in old | new
        )
        observations.append(
            {
                "effective_date": current.effective_date.isoformat(),
                "entrants": len(new - old),
                "exits": len(old - new),
                "equal_weight_one_way_turnover": equal_weight_turnover,
            }
        )
    values = [cast(float, item["equal_weight_one_way_turnover"]) for item in observations]
    return {
        "observations": len(observations),
        "mean_equal_weight_one_way_turnover": statistics.mean(values) if values else None,
        "max_equal_weight_one_way_turnover": max(values, default=None),
        "monthly": observations,
    }


def _missing_data_report(values: list[CollectorDailyValue]) -> dict[str, object]:
    active = [item for item in values if item.index_value is not None]
    return {
        "days_with_carry": sum(item.carried_count > 0 for item in active),
        "days_with_suspension": sum(item.suspended_count > 0 for item in active),
        "max_carried_weight_share": max(
            (item.carried_weight_share for item in active), default=0.0
        ),
        "max_suspended_weight_share": max(
            (item.suspended_weight_share for item in active), default=0.0
        ),
        "whole_market_carried_days": sum(item.whole_market_carried_forward for item in active),
    }


def _legacy_comparison(
    store: ObjectStore,
    definition: IndexDefinition,
    rebalances: list[CollectorRebalance],
    values: list[CollectorDailyValue],
    through_date: date,
) -> dict[str, object]:
    legacy_code = _legacy_code(definition.code)
    rebalance_key = f"derived/preview/indexes/{legacy_code}/rebalances.json"
    values_key = f"derived/preview/indexes/{legacy_code}/daily-values.parquet"
    if not rebalances or not store.exists(rebalance_key):
        return {
            "legacy_index_code": legacy_code,
            "collector_member_overlap_ratio": None,
            "legacy_member_overlap_ratio": None,
            "return_overlap_days": 0,
            "return_correlation": None,
        }
    payload = cast(dict[str, Any], json.loads(store.read_bytes(rebalance_key)))
    candidates = [
        item
        for item in cast(list[dict[str, Any]], payload.get("rebalances", []))
        if date.fromisoformat(str(item["effective_date"])) <= through_date
    ]
    latest = candidates[-1] if candidates else None
    legacy_members = {
        str(item["stable_variant_id"])
        for item in cast(list[dict[str, Any]], latest.get("constituents", []) if latest else [])
    }
    collector_members = {item.stable_variant_id for item in rebalances[-1].constituents}
    overlap = collector_members & legacy_members
    legacy_returns: dict[date, float] = {}
    if store.exists(values_key):
        frame = pl.read_parquet(BytesIO(store.read_bytes(values_key)))
        legacy_returns = {
            _as_date(row["value_date"]): float(row["daily_return"])
            for row in frame.select("value_date", "daily_return").iter_rows(named=True)
            if row["daily_return"] is not None and _as_date(row["value_date"]) <= through_date
        }
    collector_returns = {
        item.value_date: item.daily_return
        for item in values
        if item.index_value is not None and item.daily_return is not None
    }
    dates = sorted(set(collector_returns) & set(legacy_returns))
    return {
        "legacy_index_code": legacy_code,
        "collector_member_overlap_ratio": (
            len(overlap) / len(collector_members) if collector_members else None
        ),
        "legacy_member_overlap_ratio": (
            len(overlap) / len(legacy_members) if legacy_members else None
        ),
        "return_overlap_days": len(dates),
        "return_correlation": _correlation(
            [collector_returns[value] for value in dates],
            [legacy_returns[value] for value in dates],
        ),
    }


def _review_flags(report: dict[str, object]) -> list[str]:
    canonical = cast(dict[str, Any], report["canonical"])
    alternate = cast(dict[str, Any], report["alternate"])
    activity = cast(dict[str, Any], report["activity_proxy"])
    turnover = cast(dict[str, Any], report["turnover"])
    missing = cast(dict[str, Any], report["missing_data"])
    price_fields = cast(dict[str, Any], report["price_fields"])
    flags: list[str] = []
    if cast(dict[str, Any], price_fields["avg30"])["positive_rate"] == 0:
        flags.append("sold_price_avg30_source_unavailable")
    if canonical["latest_constituent_count"] == 0:
        flags.append("empty_canonical_eligible_universe")
    if alternate["latest_constituent_count"] == 0:
        flags.append("avg7_alternate_unavailable")
    if turnover["observations"] == 0:
        flags.append("monthly_turnover_not_yet_observable")
    if canonical["max_capped_weight_share"] > 0.05:
        flags.append("capped_weight_share_above_5pct_review_heuristic")
    if missing["max_suspended_weight_share"] > 0:
        flags.append("suspended_weight_present")
    if (
        activity["eligible_variants"] > 0
        and activity["counterfactual_candidate_pass_count"] == 0
    ):
        flags.append("counterfactual_activity_gate_would_exclude_all")
    return flags


def _legacy_code(code: str) -> str:
    if code.endswith("SCOL"):
        return f"{code[:-4]}SLD"
    if code.endswith("COL"):
        return f"{code[:-3]}500"
    raise ValueError(f"unsupported collector code {code}")


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p10": _list_quantile(ordered, 0.1),
        "median": _list_quantile(ordered, 0.5),
        "p90": _list_quantile(ordered, 0.9),
    }


def _series_quantile(values: pl.Series, fraction: float) -> float | None:
    if values.is_empty():
        return None
    result = values.quantile(fraction, interpolation="nearest")
    return None if result is None else float(result)


def _list_quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return values[min(round((len(values) - 1) * fraction), len(values) - 1)]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _max_drawdown(values: list[CollectorDailyValue]) -> float | None:
    peak = -math.inf
    worst = 0.0
    observed = False
    for item in values:
        if item.index_value is None:
            continue
        observed = True
        peak = max(peak, item.index_value)
        worst = min(worst, item.index_value / peak - 1 if peak > 0 else 0.0)
    return worst if observed else None


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_sum * right_sum)
    return numerator / denominator if denominator else None


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _pct(value: object) -> str:
    return "—" if not isinstance(value, (int, float)) else f"{value * 100:.2f}%"


def _number(value: object) -> str:
    return "—" if not isinstance(value, (int, float)) else f"{value:.3f}"


@click.command()
@click.option("--through", "through_value", required=True, help="Last archive date, YYYY-MM-DD")
@click.option("--store-root", default=None, help="Local object-store root; omit for R2")
@click.option(
    "--methodology",
    "methodology_path",
    type=click.Path(path_type=Path),
    default=Path("packages/indexengine/methodologies/v1.5.0-preview.2.yaml"),
)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--summary-output", type=click.Path(path_type=Path), required=True)
def main(
    through_value: str,
    store_root: str | None,
    methodology_path: Path,
    output: Path,
    summary_output: Path,
) -> None:
    settings = Settings.from_env()
    store: ObjectStore = LocalObjectStore(Path(store_root)) if store_root else R2Client(settings)
    report = build_collector_methodology_audit(
        store,
        Methodology.load(methodology_path),
        date.fromisoformat(through_value),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(render_collector_audit_summary(report))
    click.echo(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
