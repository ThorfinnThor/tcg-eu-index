from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ALL_CARDMARKET_EUROPE_LANGUAGES = "ALL_CARDMARKET_EUROPE"


class MethodologyConfigError(ValueError):
    """Raised when a methodology file is not a supported configuration."""


@dataclass(frozen=True)
class MethodologyFamily:
    key: str
    universe: str
    membership_mode: str
    constituent_identity: tuple[str, ...]
    target_size: int | None
    min_latest_avg30_eur: float
    reference_price_field: str
    valuation_price_field: str
    price_fallback: str | None
    selection_rank: str | None
    concentration_caps: dict[str, float] | None
    price_band_targets: dict[str, float] | None
    calculation_enabled: bool = True
    source_status: str = "available"


@dataclass(frozen=True)
class MethodologySource:
    provider: str
    reference_price_field: str
    activity_signal_field: str


@dataclass(frozen=True)
class MethodologyCalculation:
    valuation_price_field: str
    price_fallback: str | None
    weighting: str
    rebalance: str
    rebalance_effective_day: str
    daily_constituent_return_cap: float
    carry_forward_max_days: int
    stale_policy: str


@dataclass(frozen=True)
class MethodologyQuality:
    selection_lookback_days: int
    seasoning_days: int
    official_min_history_days: int
    shadow_min_history_days: int
    min_valuation_observation_ratio: float
    min_selection_price_observation_ratio: float
    max_suspect_zero_ratio: float
    score_name: str


@dataclass(frozen=True)
class MethodologyActivity:
    proxy_name: str
    signal_field: str
    lookback_days: int
    exclude_source_gaps: bool
    exclude_unchanged_snapshots: bool
    eligibility_gate_enabled: bool
    candidate_min_ratio: dict[str, float]
    candidate_max_days_since_signal: dict[str, int]


@dataclass(frozen=True)
class MethodologyOutput:
    index_prefix: str
    diagnostics_prefix: str
    series_id: str
    public_alias_enabled: bool


@dataclass(frozen=True)
class MethodologyCalibration:
    alternate_valuation_fields: tuple[str, ...]
    require_activity_proxy_validation: bool
    require_human_cutover: bool
    splice_with_prior_methodology: bool


@dataclass(frozen=True)
class IndexDefinition:
    code: str
    name: str
    game_key: str
    universe: str
    target_size: int | None
    base_date: str
    base_value: float
    status: str
    language_scope: list[str]
    family: str | None = None
    public: bool = True

    @property
    def language_scope_status(self) -> str:
        if self.language_scope == [ALL_CARDMARKET_EUROPE_LANGUAGES]:
            return "resolved_all_cardmarket_europe_languages"
        return "pending_source_field"

    def required_target_size(self) -> int:
        """Return the legacy fixed target, or fail before legacy-only code runs."""
        if self.target_size is None:
            raise MethodologyConfigError(
                f"index {self.code} has nullable target_size; use its family membership mode"
            )
        return self.target_size


@dataclass(frozen=True)
class Methodology:
    methodology_version: str
    price_field_primary: str
    price_field_fallback: str
    min_price_eur: dict[str, float]
    seasoning_days: int
    min_history_days: int
    min_observation_ratio: float
    price_floor_observation_ratio: float
    max_suspect_zero_ratio: float
    daily_return_cap: float
    carry_forward_max_days: int
    rebalance: str
    selection_lookback_days: int
    selection_rank: str
    ranking_price_field: str
    indexes: list[IndexDefinition]
    schema_version: int = 1
    methodology_state: str = "active"
    source: MethodologySource | None = None
    calculation: MethodologyCalculation | None = None
    quality: MethodologyQuality | None = None
    activity: MethodologyActivity | None = None
    families: dict[str, MethodologyFamily] = field(default_factory=dict)
    output: MethodologyOutput | None = None
    calibration: MethodologyCalibration | None = None

    @classmethod
    def load(cls, path: Path = Path("packages/indexengine/methodology.yaml")) -> Methodology:
        payload = _read_payload(path)
        schema_version = payload.get("schema_version", 1)
        if schema_version == 1:
            return _load_v14(payload, path)
        if schema_version == 2:
            return _load_v15(payload, path)
        raise MethodologyConfigError(
            f"{path}: unsupported schema_version {schema_version!r}; expected 1 or 2"
        )

    def index_by_code(self, code: str) -> IndexDefinition:
        for definition in self.indexes:
            if definition.code == code:
                return definition
        raise KeyError(code)


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text())
    except OSError as exc:
        raise MethodologyConfigError(f"{path}: cannot read methodology file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise MethodologyConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise MethodologyConfigError(f"{path}: root must be a mapping")
    return payload


def _reject_unknown(payload: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise MethodologyConfigError(f"{path}: unsupported field(s): {', '.join(unknown)}")


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MethodologyConfigError(f"{path}: expected a mapping")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise MethodologyConfigError(f"{path}: expected a non-empty string")
    return value


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MethodologyConfigError(f"{path}: expected a number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise MethodologyConfigError(f"{path}: expected a number >= {minimum}")
    return result


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MethodologyConfigError(f"{path}: expected an integer")
    if minimum is not None and value < minimum:
        raise MethodologyConfigError(f"{path}: expected an integer >= {minimum}")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise MethodologyConfigError(f"{path}: expected a boolean")
    return value


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        raise MethodologyConfigError(f"{path}: expected a non-empty list of strings")
    return value


def _load_v14(payload: dict[str, Any], path: Path) -> Methodology:
    _reject_unknown(
        payload,
        {
            "methodology_version",
            "price_field_primary",
            "price_field_fallback",
            "min_price_eur",
            "seasoning_days",
            "min_history_days",
            "min_observation_ratio",
            "price_floor_observation_ratio",
            "max_suspect_zero_ratio",
            "daily_return_cap",
            "carry_forward_max_days",
            "rebalance",
            "selection_lookback_days",
            "selection_rank",
            "ranking_price_field",
            "indexes",
        },
        str(path),
    )
    indexes_payload = payload.get("indexes")
    if not isinstance(indexes_payload, list):
        raise MethodologyConfigError(f"{path}: indexes must be a list")
    indexes = [
        _parse_v14_index(item, f"{path}:indexes[{number}]")
        for number, item in enumerate(indexes_payload)
    ]
    _validate_unique_codes(indexes, path)
    min_prices = _mapping(payload.get("min_price_eur"), f"{path}:min_price_eur")
    return Methodology(
        methodology_version=_string(
            payload.get("methodology_version"), f"{path}:methodology_version"
        ),
        price_field_primary=_string(
            payload.get("price_field_primary"), f"{path}:price_field_primary"
        ),
        price_field_fallback=_string(
            payload.get("price_field_fallback"), f"{path}:price_field_fallback"
        ),
        min_price_eur={
            key: _number(value, f"{path}:min_price_eur.{key}", minimum=0)
            for key, value in min_prices.items()
        },
        seasoning_days=_integer(payload.get("seasoning_days"), f"{path}:seasoning_days", minimum=0),
        min_history_days=_integer(
            payload.get("min_history_days"), f"{path}:min_history_days", minimum=0
        ),
        min_observation_ratio=_number(
            payload.get("min_observation_ratio"), f"{path}:min_observation_ratio", minimum=0
        ),
        price_floor_observation_ratio=_number(
            payload.get("price_floor_observation_ratio"),
            f"{path}:price_floor_observation_ratio",
            minimum=0,
        ),
        max_suspect_zero_ratio=_number(
            payload.get("max_suspect_zero_ratio"), f"{path}:max_suspect_zero_ratio", minimum=0
        ),
        daily_return_cap=_number(
            payload.get("daily_return_cap"), f"{path}:daily_return_cap", minimum=0
        ),
        carry_forward_max_days=_integer(
            payload.get("carry_forward_max_days"), f"{path}:carry_forward_max_days", minimum=0
        ),
        rebalance=_string(payload.get("rebalance"), f"{path}:rebalance"),
        selection_lookback_days=_integer(
            payload.get("selection_lookback_days"), f"{path}:selection_lookback_days", minimum=1
        ),
        selection_rank=_string(payload.get("selection_rank"), f"{path}:selection_rank"),
        ranking_price_field=_string(
            payload.get("ranking_price_field"), f"{path}:ranking_price_field"
        ),
        indexes=indexes,
    )


def _parse_v14_index(value: Any, path: str) -> IndexDefinition:
    item = _mapping(value, path)
    _reject_unknown(
        item,
        {
            "code",
            "name",
            "game_key",
            "universe",
            "target_size",
            "base_date",
            "base_value",
            "status",
            "language_scope",
        },
        path,
    )
    universe = _string(item.get("universe"), f"{path}.universe")
    if universe not in {"singles", "sealed"}:
        raise MethodologyConfigError(f"{path}.universe: unsupported universe {universe!r}")
    return IndexDefinition(
        code=_string(item.get("code"), f"{path}.code"),
        name=_string(item.get("name"), f"{path}.name"),
        game_key=_string(item.get("game_key"), f"{path}.game_key"),
        universe=universe,
        target_size=_integer(item.get("target_size"), f"{path}.target_size", minimum=1),
        base_date=_string(item.get("base_date"), f"{path}.base_date"),
        base_value=_number(item.get("base_value"), f"{path}.base_value", minimum=0),
        status=_string(item.get("status"), f"{path}.status"),
        language_scope=_string_list(item.get("language_scope"), f"{path}.language_scope"),
    )


def _load_v15(payload: dict[str, Any], path: Path) -> Methodology:
    _reject_unknown(
        payload,
        {
            "schema_version",
            "methodology_version",
            "methodology_state",
            "base_value",
            "source",
            "calculation",
            "quality",
            "activity",
            "families",
            "indexes",
            "output",
            "calibration",
        },
        str(path),
    )
    if payload.get("schema_version") != 2:
        raise MethodologyConfigError(f"{path}: schema_version must be 2 for the v1.5 schema")
    state = _string(payload.get("methodology_state"), f"{path}:methodology_state")
    if state not in {"private_shadow", "active"}:
        raise MethodologyConfigError(f"{path}:methodology_state: unsupported state {state!r}")
    base_value = _number(payload.get("base_value"), f"{path}:base_value", minimum=0)
    source = _parse_source(_mapping(payload.get("source"), f"{path}:source"), f"{path}:source")
    calculation = _parse_calculation(
        _mapping(payload.get("calculation"), f"{path}:calculation"), f"{path}:calculation"
    )
    quality = _parse_quality(_mapping(payload.get("quality"), f"{path}:quality"), f"{path}:quality")
    activity = _parse_activity(
        _mapping(payload.get("activity"), f"{path}:activity"), f"{path}:activity"
    )
    families = _parse_families(
        _mapping(payload.get("families"), f"{path}:families"), f"{path}:families"
    )
    indexes_payload = payload.get("indexes")
    if not isinstance(indexes_payload, list):
        raise MethodologyConfigError(f"{path}:indexes must be a list")
    indexes = [
        _parse_v15_index(item, f"{path}:indexes[{number}]", families, state, base_value)
        for number, item in enumerate(indexes_payload)
    ]
    _validate_unique_codes(indexes, path)
    output = _parse_output(_mapping(payload.get("output"), f"{path}:output"), f"{path}:output")
    calibration = _parse_calibration(
        _mapping(payload.get("calibration"), f"{path}:calibration"), f"{path}:calibration"
    )
    if state == "private_shadow" and output.public_alias_enabled:
        raise MethodologyConfigError(
            f"{path}:output.public_alias_enabled: must be false for private_shadow"
        )
    by_universe = _families_by_universe(families)
    return Methodology(
        methodology_version=_string(
            payload.get("methodology_version"), f"{path}:methodology_version"
        ),
        price_field_primary=source.reference_price_field,
        price_field_fallback=calculation.price_fallback or "",
        min_price_eur={
            universe: family.min_latest_avg30_eur for universe, family in by_universe.items()
        },
        seasoning_days=quality.seasoning_days,
        min_history_days=quality.official_min_history_days,
        min_observation_ratio=quality.min_valuation_observation_ratio,
        price_floor_observation_ratio=quality.min_selection_price_observation_ratio,
        max_suspect_zero_ratio=quality.max_suspect_zero_ratio,
        daily_return_cap=calculation.daily_constituent_return_cap,
        carry_forward_max_days=calculation.carry_forward_max_days,
        rebalance=calculation.rebalance,
        selection_lookback_days=quality.selection_lookback_days,
        selection_rank="all_eligible_variants",
        ranking_price_field=source.reference_price_field,
        indexes=indexes,
        schema_version=2,
        methodology_state=state,
        source=source,
        calculation=calculation,
        quality=quality,
        activity=activity,
        families=families,
        output=output,
        calibration=calibration,
    )


def _parse_source(item: dict[str, Any], path: str) -> MethodologySource:
    _reject_unknown(item, {"provider", "reference_price_field", "activity_signal_field"}, path)
    result = MethodologySource(
        _string(item.get("provider"), f"{path}.provider"),
        _string(item.get("reference_price_field"), f"{path}.reference_price_field"),
        _string(item.get("activity_signal_field"), f"{path}.activity_signal_field"),
    )
    if (
        result.provider != "cardmarket"
        or result.reference_price_field != "avg30"
        or result.activity_signal_field != "avg1"
    ):
        raise MethodologyConfigError(
            f"{path}: only Cardmarket avg30/avg1 source fields are supported"
        )
    return result


def _parse_calculation(item: dict[str, Any], path: str) -> MethodologyCalculation:
    _reject_unknown(
        item,
        {
            "valuation_price_field",
            "price_fallback",
            "weighting",
            "rebalance",
            "rebalance_effective_day",
            "daily_constituent_return_cap",
            "carry_forward_max_days",
            "stale_policy",
        },
        path,
    )
    fallback = item.get("price_fallback")
    if fallback is not None and not isinstance(fallback, str):
        raise MethodologyConfigError(f"{path}.price_fallback: expected string or null")
    result = MethodologyCalculation(
        _string(item.get("valuation_price_field"), f"{path}.valuation_price_field"),
        fallback,
        _string(item.get("weighting"), f"{path}.weighting"),
        _string(item.get("rebalance"), f"{path}.rebalance"),
        _string(item.get("rebalance_effective_day"), f"{path}.rebalance_effective_day"),
        _number(
            item.get("daily_constituent_return_cap"),
            f"{path}.daily_constituent_return_cap",
            minimum=0,
        ),
        _integer(item.get("carry_forward_max_days"), f"{path}.carry_forward_max_days", minimum=0),
        _string(item.get("stale_policy"), f"{path}.stale_policy"),
    )
    if (
        result.valuation_price_field,
        result.weighting,
        result.rebalance,
        result.rebalance_effective_day,
        result.stale_policy,
    ) != (
        "avg30",
        "equal_weight_at_monthly_rebalance",
        "monthly",
        "first_observable_source_day",
        "suspend_at_last_valid_price",
    ) or result.price_fallback is not None:
        raise MethodologyConfigError(f"{path}: unsupported calculation policy")
    return result


def _parse_quality(item: dict[str, Any], path: str) -> MethodologyQuality:
    _reject_unknown(
        item,
        {
            "selection_lookback_days",
            "seasoning_days",
            "official_min_history_days",
            "shadow_min_history_days",
            "min_valuation_observation_ratio",
            "min_selection_price_observation_ratio",
            "max_suspect_zero_ratio",
            "score_name",
        },
        path,
    )
    return MethodologyQuality(
        _integer(item.get("selection_lookback_days"), f"{path}.selection_lookback_days", minimum=1),
        _integer(item.get("seasoning_days"), f"{path}.seasoning_days", minimum=0),
        _integer(
            item.get("official_min_history_days"), f"{path}.official_min_history_days", minimum=0
        ),
        _integer(item.get("shadow_min_history_days"), f"{path}.shadow_min_history_days", minimum=0),
        _number(
            item.get("min_valuation_observation_ratio"),
            f"{path}.min_valuation_observation_ratio",
            minimum=0,
        ),
        _number(
            item.get("min_selection_price_observation_ratio"),
            f"{path}.min_selection_price_observation_ratio",
            minimum=0,
        ),
        _number(item.get("max_suspect_zero_ratio"), f"{path}.max_suspect_zero_ratio", minimum=0),
        _string(item.get("score_name"), f"{path}.score_name"),
    )


def _parse_activity(item: dict[str, Any], path: str) -> MethodologyActivity:
    _reject_unknown(
        item,
        {
            "proxy_name",
            "signal_field",
            "lookback_days",
            "exclude_source_gaps",
            "exclude_unchanged_snapshots",
            "eligibility_gate_enabled",
            "candidate_min_ratio",
            "candidate_max_days_since_signal",
        },
        path,
    )
    ratios = _mapping(item.get("candidate_min_ratio"), f"{path}.candidate_min_ratio")
    max_days = _mapping(
        item.get("candidate_max_days_since_signal"), f"{path}.candidate_max_days_since_signal"
    )
    if set(ratios) != {"singles", "sealed"} or set(max_days) != {"singles", "sealed"}:
        raise MethodologyConfigError(
            f"{path}: candidate activity settings must define singles and sealed"
        )
    return MethodologyActivity(
        _string(item.get("proxy_name"), f"{path}.proxy_name"),
        _string(item.get("signal_field"), f"{path}.signal_field"),
        _integer(item.get("lookback_days"), f"{path}.lookback_days", minimum=1),
        _bool(item.get("exclude_source_gaps"), f"{path}.exclude_source_gaps"),
        _bool(item.get("exclude_unchanged_snapshots"), f"{path}.exclude_unchanged_snapshots"),
        _bool(item.get("eligibility_gate_enabled"), f"{path}.eligibility_gate_enabled"),
        {
            key: _number(value, f"{path}.candidate_min_ratio.{key}", minimum=0)
            for key, value in ratios.items()
        },
        {
            key: _integer(value, f"{path}.candidate_max_days_since_signal.{key}", minimum=0)
            for key, value in max_days.items()
        },
    )


def _parse_families(item: dict[str, Any], path: str) -> dict[str, MethodologyFamily]:
    if not item:
        raise MethodologyConfigError(f"{path}: at least one family is required")
    families: dict[str, MethodologyFamily] = {}
    for key, value in item.items():
        family_path = f"{path}.{key}"
        family = _mapping(value, family_path)
        _reject_unknown(
            family,
            {
                "universe",
                "membership_mode",
                "constituent_identity",
                "target_size",
                "min_latest_avg30_eur",
                "reference_price_field",
                "valuation_price_field",
                "price_fallback",
                "selection_rank",
                "concentration_caps",
                "price_band_targets",
                "calculation_enabled",
                "source_status",
            },
            family_path,
        )
        universe = _string(family.get("universe"), f"{family_path}.universe")
        if universe not in {"singles", "sealed"}:
            raise MethodologyConfigError(
                f"{family_path}.universe: unsupported universe {universe!r}"
            )
        identity = _string_list(
            family.get("constituent_identity"), f"{family_path}.constituent_identity"
        )
        if tuple(identity) != ("cm_product_id", "variant_key"):
            raise MethodologyConfigError(
                f"{family_path}.constituent_identity: expected [cm_product_id, variant_key]"
            )
        target = family.get("target_size")
        if target is not None:
            target = _integer(target, f"{family_path}.target_size", minimum=1)
        for nullable_field in (
            "price_fallback",
            "selection_rank",
            "concentration_caps",
            "price_band_targets",
        ):
            if family.get(nullable_field) is not None:
                raise MethodologyConfigError(
                    f"{family_path}.{nullable_field}: only null is supported for collector families"
                )
        calculation_enabled = _bool(
            family.get("calculation_enabled", True),
            f"{family_path}.calculation_enabled",
        )
        source_status = _string(
            family.get("source_status", "available"), f"{family_path}.source_status"
        )
        if calculation_enabled and source_status != "available":
            raise MethodologyConfigError(
                f"{family_path}: enabled families require source_status 'available'"
            )
        if not calculation_enabled and source_status != "rolling_sold_price_unavailable":
            raise MethodologyConfigError(
                f"{family_path}: deferred families require source_status "
                "'rolling_sold_price_unavailable'"
            )
        result = MethodologyFamily(
            key=key,
            universe=universe,
            membership_mode=_string(
                family.get("membership_mode"), f"{family_path}.membership_mode"
            ),
            constituent_identity=tuple(identity),
            target_size=target,
            min_latest_avg30_eur=_number(
                family.get("min_latest_avg30_eur"), f"{family_path}.min_latest_avg30_eur", minimum=0
            ),
            reference_price_field=_string(
                family.get("reference_price_field"), f"{family_path}.reference_price_field"
            ),
            valuation_price_field=_string(
                family.get("valuation_price_field"), f"{family_path}.valuation_price_field"
            ),
            price_fallback=None,
            selection_rank=None,
            concentration_caps=None,
            price_band_targets=None,
            calculation_enabled=calculation_enabled,
            source_status=source_status,
        )
        if (
            result.membership_mode != "all_eligible_variants"
            or result.reference_price_field != "avg30"
            or result.valuation_price_field != "avg30"
        ):
            raise MethodologyConfigError(f"{family_path}: unsupported collector family policy")
        families[key] = result
    return families


def _parse_v15_index(
    value: Any, path: str, families: dict[str, MethodologyFamily], state: str, base_value: float
) -> IndexDefinition:
    item = _mapping(value, path)
    _reject_unknown(item, {"code", "name", "game_key", "family", "public", "language_scope"}, path)
    code = _string(item.get("code"), f"{path}.code")
    if any(character.isdigit() for character in code):
        raise MethodologyConfigError(f"{path}.code: v1.5 collector codes must not contain numbers")
    family_key = _string(item.get("family"), f"{path}.family")
    if family_key not in families:
        raise MethodologyConfigError(f"{path}.family: unknown family {family_key!r}")
    family = families[family_key]
    public = item.get("public")
    if not isinstance(public, bool):
        raise MethodologyConfigError(f"{path}.public: expected a boolean")
    if state == "private_shadow" and public:
        raise MethodologyConfigError(f"{path}.public: must be false for private_shadow")
    return IndexDefinition(
        code,
        _string(item.get("name"), f"{path}.name"),
        _string(item.get("game_key"), f"{path}.game_key"),
        family.universe,
        family.target_size,
        "",
        base_value,
        state,
        _string_list(item.get("language_scope"), f"{path}.language_scope"),
        family_key,
        public,
    )


def _parse_output(item: dict[str, Any], path: str) -> MethodologyOutput:
    _reject_unknown(
        item, {"index_prefix", "diagnostics_prefix", "series_id", "public_alias_enabled"}, path
    )
    return MethodologyOutput(
        _string(item.get("index_prefix"), f"{path}.index_prefix"),
        _string(item.get("diagnostics_prefix"), f"{path}.diagnostics_prefix"),
        _string(item.get("series_id"), f"{path}.series_id"),
        _bool(item.get("public_alias_enabled"), f"{path}.public_alias_enabled"),
    )


def _parse_calibration(item: dict[str, Any], path: str) -> MethodologyCalibration:
    _reject_unknown(
        item,
        {
            "alternate_valuation_fields",
            "require_activity_proxy_validation",
            "require_human_cutover",
            "splice_with_prior_methodology",
        },
        path,
    )
    fields = _string_list(
        item.get("alternate_valuation_fields"), f"{path}.alternate_valuation_fields"
    )
    return MethodologyCalibration(
        tuple(fields),
        _bool(
            item.get("require_activity_proxy_validation"),
            f"{path}.require_activity_proxy_validation",
        ),
        _bool(item.get("require_human_cutover"), f"{path}.require_human_cutover"),
        _bool(item.get("splice_with_prior_methodology"), f"{path}.splice_with_prior_methodology"),
    )


def _families_by_universe(families: dict[str, MethodologyFamily]) -> dict[str, MethodologyFamily]:
    result: dict[str, MethodologyFamily] = {}
    for family in families.values():
        if (
            family.universe in result
            and result[family.universe].min_latest_avg30_eur != family.min_latest_avg30_eur
        ):
            raise MethodologyConfigError(
                f"families: conflicting thresholds for universe {family.universe!r}"
            )
        result[family.universe] = family
    return result


def _validate_unique_codes(indexes: list[IndexDefinition], path: Path) -> None:
    seen: set[str] = set()
    for definition in indexes:
        if definition.code in seen:
            raise MethodologyConfigError(f"{path}: duplicate index code {definition.code!r}")
        seen.add(definition.code)
