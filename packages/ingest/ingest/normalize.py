from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import click
import polars as pl
import yaml
from core.logging import configure_logging
from core.r2 import R2Client, gunzip_body, sha256_hex
from core.settings import Settings, parse_run_date

from ingest.manifest import Manifest, manifest_key, validate_manifest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizedCatalogue:
    games: list[dict[str, Any]]
    sets: list[dict[str, Any]]
    products: list[dict[str, Any]]
    variants: list[dict[str, Any]]
    unknown_categories: set[str]


def load_category_map(path: Path = Path("packages/ingest/category_map.yaml")) -> dict[str, str]:
    payload = yaml.safe_load(path.read_text()) or {}
    mapping: dict[str, str] = {}
    for product_kind, labels in payload.items():
        for label in labels:
            mapping[str(label).strip().lower()] = product_kind
    return mapping


def _records(raw: bytes) -> list[dict[str, Any]]:
    payload = json.loads(raw)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    for key in ("data", "products", "priceGuide"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise ValueError("unsupported Cardmarket JSON shape; paste sample into ADR 001 and map it")


def _first(record: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


def classify(raw_category: str | None, mapping: dict[str, str]) -> str:
    if raw_category is None:
        return "other"
    return mapping.get(raw_category.strip().lower(), "other")


def normalize_catalogue(
    game: str,
    raw: bytes,
    run_date: date,
    category_mapping: dict[str, str],
) -> NormalizedCatalogue:
    records = _records(raw)
    products: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    sets_by_key: dict[int, dict[str, Any]] = {}
    unknown: set[str] = set()

    for record in records:
        product_id = int(_first(record, "idProduct", "productId", "cm_product_id", "id"))
        expansion_id = _first(record, "idExpansion", "expansionId", "cm_expansion_id")
        set_name = _first(record, "expansionName", "setName", "set", default=None)
        raw_category = str(_first(record, "category", "productType", "type", default=""))
        kind = classify(raw_category, category_mapping)
        if kind == "other" and raw_category:
            unknown.add(raw_category)
        if expansion_id is not None:
            sets_by_key[int(expansion_id)] = {
                "game_key": game,
                "cm_expansion_id": int(expansion_id),
                "name": set_name or f"Expansion {expansion_id}",
                "release_date": _first(record, "releaseDate", "dateRelease"),
            }
        products.append(
            {
                "game_key": game,
                "cm_product_id": product_id,
                "cm_expansion_id": int(expansion_id) if expansion_id is not None else None,
                "name": str(_first(record, "name", "productName", default=f"Product {product_id}")),
                "product_kind": kind,
                "raw_category": raw_category,
                "first_seen": run_date.isoformat(),
                "last_seen": run_date.isoformat(),
            }
        )
        variants.append({"cm_product_id": product_id, "variant_key": "nonfoil"})
        if any(key in record for key in ("foilSell", "foilLow", "foilAvg", "priceFoil")):
            variants.append({"cm_product_id": product_id, "variant_key": "foil"})

    return NormalizedCatalogue(
        games=[{"cm_game_key": game, "name": game.replace("-", " ").title()}],
        sets=list(sets_by_key.values()),
        products=products,
        variants=variants,
        unknown_categories=unknown,
    )


def normalize_prices(game: str, raw: bytes, value_date: date) -> pl.DataFrame:
    records = _records(raw)
    rows: list[dict[str, Any]] = []
    for record in records:
        product_id = int(_first(record, "idProduct", "productId", "cm_product_id", "id"))
        base = {
            "game_key": game,
            "cm_product_id": product_id,
            "variant_key": "nonfoil",
            "value_date": value_date,
            "price_low": _first(record, "low", "price_low", "lowPrice"),
            "price_avg": _first(record, "avg", "price_avg", "avgPrice", "average"),
            "avg1": _first(record, "avg1", "avg1Price", default=None),
            "avg7": _first(record, "avg7", "avg7Price", default=None),
            "avg30": _first(record, "avg30", "avg30Price", default=None),
        }
        rows.append(base)
        foil_avg = _first(record, "foilAvg", "priceFoil", default=None)
        if foil_avg is not None:
            foil = dict(base)
            foil["variant_key"] = "foil"
            foil["price_avg"] = foil_avg
            foil["price_low"] = _first(record, "foilLow", default=foil_avg)
            rows.append(foil)
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def run_normalize(run_date: date, settings: Settings, store: Any | None = None) -> None:
    store = store or R2Client(settings)
    manifest = Manifest.from_bytes(store.read_bytes(manifest_key(run_date)))
    errors = validate_manifest(store, manifest, settings.cm_games)
    if errors:
        raise RuntimeError("; ".join(errors))
    category_mapping = load_category_map()

    for game in settings.cm_games:
        catalogue_file = next(
            file for file in manifest.files if file.game == game and file.kind == "catalogue"
        )
        price_file = next(
            file for file in manifest.files if file.game == game and file.kind == "priceguide"
        )
        catalogue_raw = gunzip_body(store.read_bytes(catalogue_file.key))
        price_raw = gunzip_body(store.read_bytes(price_file.key))
        normalized = normalize_catalogue(game, catalogue_raw, run_date, category_mapping)
        if normalized.unknown_categories:
            logger.warning(
                "unknown_categories",
                extra={
                    "extra": {
                        "game": game,
                        "categories": sorted(normalized.unknown_categories),
                    }
                },
            )
        prices = normalize_prices(game, price_raw, run_date)
        if not prices.is_empty():
            parquet_key = f"derived/prices/{game}/{run_date:%Y-%m}.parquet"
            existing = (
                pl.read_parquet(BytesIO(store.read_bytes(parquet_key)))
                if store.exists(parquet_key)
                else pl.DataFrame()
            )
            combined = (
                pl.concat([existing, prices], how="diagonal")
                .unique(["cm_product_id", "variant_key", "value_date"], keep="last")
                .sort(["cm_product_id", "variant_key", "value_date"])
            )
            buffer = BytesIO()
            combined.write_parquet(buffer)
            store.write_bytes(parquet_key, buffer.getvalue(), "application/octet-stream")
        run_note = {
            "game": game,
            "snapshot_sha": sha256_hex(price_raw),
            "catalogue_products": len(normalized.products),
            "price_rows": prices.height,
        }
        store.write_bytes(
            f"derived/ingest_runs/{run_date.isoformat()}-{game}.json",
            json.dumps(run_note, indent=2, sort_keys=True).encode(),
            "application/json",
        )


@click.command()
@click.option("--date", "date_value", default="today")
def main(date_value: str) -> None:
    configure_logging()
    run_normalize(parse_run_date(date_value), Settings.from_env())


if __name__ == "__main__":
    main()
