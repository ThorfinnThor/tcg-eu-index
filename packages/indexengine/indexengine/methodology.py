from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IndexDefinition:
    code: str
    name: str
    game_key: str
    universe: str
    target_size: int
    base_date: str
    base_value: float
    status: str
    language_scope: list[str]


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
    buffer_retention_multiplier: float
    buffer_entry_multiplier: float
    indexes: list[IndexDefinition]

    @classmethod
    def load(cls, path: Path = Path("packages/indexengine/methodology.yaml")) -> Methodology:
        payload: dict[str, Any] = yaml.safe_load(path.read_text())
        return cls(
            methodology_version=str(payload["methodology_version"]),
            price_field_primary=str(payload["price_field_primary"]),
            price_field_fallback=str(payload["price_field_fallback"]),
            min_price_eur={key: float(value) for key, value in payload["min_price_eur"].items()},
            seasoning_days=int(payload["seasoning_days"]),
            min_history_days=int(payload["min_history_days"]),
            min_observation_ratio=float(payload["min_observation_ratio"]),
            price_floor_observation_ratio=float(payload["price_floor_observation_ratio"]),
            max_suspect_zero_ratio=float(payload["max_suspect_zero_ratio"]),
            daily_return_cap=float(payload["daily_return_cap"]),
            carry_forward_max_days=int(payload["carry_forward_max_days"]),
            rebalance=str(payload["rebalance"]),
            selection_lookback_days=int(payload["selection_lookback_days"]),
            buffer_retention_multiplier=float(payload["buffer_retention_multiplier"]),
            buffer_entry_multiplier=float(payload["buffer_entry_multiplier"]),
            indexes=[IndexDefinition(**item) for item in payload["indexes"]],
        )

    def index_by_code(self, code: str) -> IndexDefinition:
        for definition in self.indexes:
            if definition.code == code:
                return definition
        raise KeyError(code)
