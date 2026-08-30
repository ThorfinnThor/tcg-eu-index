from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from indexengine.card_images.contracts import Finish, source_row_key

_FINISHES = {
    "nonfoil",
    "foil",
    "holo",
    "reverse_holo",
    "cold_foil",
    "rainbow_foil",
    "gold_foil",
    "etched",
    "serialized",
    "other",
    "unknown",
}


@dataclass(frozen=True)
class ManualCardImageOverride:
    source_row_key: str
    game: str
    cardmarket_product_id: int
    finish: Finish
    provider: str
    provider_card_id: str
    provider_art_id: str | None
    reviewed_at: str
    evidence: tuple[str, ...]


def load_manual_overrides(path: Path) -> dict[tuple[str, str], ManualCardImageOverride]:
    """Load reviewed source-row to provider-art mappings from versioned YAML."""
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("manual card-image overrides must use version 1")
    raw_mappings = payload.get("mappings")
    if not isinstance(raw_mappings, list):
        raise ValueError("manual card-image overrides require a mappings list")

    overrides: dict[tuple[str, str], ManualCardImageOverride] = {}
    for index, raw in enumerate(raw_mappings, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"manual override {index} must be an object")
        game = _required_text(raw, "game", index)
        provider = _required_text(raw, "provider", index)
        provider_card_id = _required_text(raw, "provider_card_id", index)
        provider_art_id = _optional_text(raw.get("provider_art_id"))
        reviewed_at = _required_text(raw, "reviewed_at", index)
        finish_raw = _required_text(raw, "finish", index)
        if finish_raw not in _FINISHES:
            raise ValueError(f"manual override {index} has unsupported finish {finish_raw!r}")
        try:
            product_id = int(raw["cardmarket_product_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"manual override {index} requires a positive Cardmarket product ID"
            ) from exc
        if product_id <= 0:
            raise ValueError(
                f"manual override {index} requires a positive Cardmarket product ID"
            )
        raw_evidence = raw.get("evidence")
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise ValueError(f"manual override {index} requires review evidence")
        evidence = tuple(
            item for value in raw_evidence if (item := _optional_text(value)) is not None
        )
        if not evidence:
            raise ValueError(f"manual override {index} requires review evidence")

        row_key = source_row_key(game, product_id, finish_raw)
        key = (row_key, provider)
        if key in overrides:
            raise ValueError(
                f"duplicate manual override for {game} product {product_id} "
                f"finish {finish_raw} and provider {provider}"
            )
        overrides[key] = ManualCardImageOverride(
            source_row_key=row_key,
            game=game,
            cardmarket_product_id=product_id,
            finish=cast(Finish, finish_raw),
            provider=provider,
            provider_card_id=provider_card_id,
            provider_art_id=provider_art_id,
            reviewed_at=reviewed_at,
            evidence=evidence,
        )
    return overrides


def _required_text(raw: dict[object, object], field: str, index: int) -> str:
    value = _optional_text(raw.get(field))
    if value is None:
        raise ValueError(f"manual override {index} requires {field}")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
