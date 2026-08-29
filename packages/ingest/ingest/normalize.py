from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
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
from core.store import ObjectStore

from ingest.cardmarket import game_config
from ingest.manifest import Manifest, manifest_key, validate_manifest
from ingest.product_metadata import catalogue_identity

logger = logging.getLogger(__name__)
ALLOWED_PRODUCT_KINDS = {"single", "sealed", "other"}

PRODUCT_COLUMNS = [
    "stable_product_id",
    "game_key",
    "cm_product_id",
    "cm_metacard_id",
    "cm_category_id",
    "cm_expansion_id",
    "name",
    "display_name",
    "collector_number",
    "image_url",
    "image_source",
    "tcgplayer_product_url",
    "metadata_status",
    "product_kind",
    "raw_category",
    "source_date_added",
    "first_seen",
    "last_seen",
]
SET_COLUMNS = [
    "stable_set_id",
    "game_key",
    "cm_expansion_id",
    "name",
    "release_date",
    "first_seen",
    "last_seen",
]
VARIANT_COLUMNS = [
    "stable_variant_id",
    "stable_product_id",
    "game_key",
    "cm_product_id",
    "variant_key",
    "product_kind",
    "first_seen",
    "last_seen",
]


@dataclass(frozen=True)
class NormalizedCatalogue:
    games: list[dict[str, Any]]
    sets: list[dict[str, Any]]
    products: list[dict[str, Any]]
    variants: list[dict[str, Any]]
    unknown_categories: set[str]


@dataclass(frozen=True)
class GameNormalizationResult:
    game: str
    run_date: str
    status: str
    catalogue_products: int
    catalogue_sets: int
    catalogue_variants: int
    price_rows: int
    classification_coverage: float
    unknown_categories: list[str]
    changed_outputs: list[str]


def stable_product_id(game: str, cm_product_id: int) -> str:
    return f"cardmarket:{game}:product:{cm_product_id}"


def stable_set_id(game: str, cm_expansion_id: int) -> str:
    return f"cardmarket:{game}:expansion:{cm_expansion_id}"


def stable_variant_id(game: str, cm_product_id: int, variant_key: str) -> str:
    return f"{stable_product_id(game, cm_product_id)}:{variant_key}"


def load_category_map(path: Path = Path("packages/ingest/category_map.yaml")) -> dict[str, str]:
    payload = yaml.safe_load(path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError("category map must be an object")
    unknown_kinds = set(payload) - ALLOWED_PRODUCT_KINDS
    if unknown_kinds:
        raise ValueError(f"unsupported product kinds: {', '.join(sorted(unknown_kinds))}")

    mapping: dict[str, str] = {}
    for product_kind, labels in payload.items():
        if not isinstance(labels, list):
            raise ValueError(f"category map entry {product_kind!r} must be a list")
        for label in labels:
            normalized = str(label).strip().casefold()
            previous = mapping.get(normalized)
            if previous is not None and previous != product_kind:
                raise ValueError(f"category {label!r} maps to both {previous} and {product_kind}")
            mapping[normalized] = str(product_kind)
    return mapping


def _records(raw: bytes) -> list[dict[str, Any]]:
    payload = json.loads(raw)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("Cardmarket payload must be a JSON object")
    for key in ("data", "products", "priceGuide", "priceGuides"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise ValueError("unsupported Cardmarket JSON shape; update ADR 001 before mapping it")


def _first(record: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _source_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text.startswith("0000-00-00") else text


def classify(raw_category: str | None, mapping: Mapping[str, str]) -> str:
    if raw_category is None:
        return "other"
    return mapping.get(raw_category.strip().casefold(), "other")


def normalize_catalogue(
    game: str,
    raw: bytes,
    run_date: date,
    category_mapping: Mapping[str, str],
) -> NormalizedCatalogue:
    records = _records(raw)
    products: list[dict[str, Any]] = []
    sets_by_key: dict[int, dict[str, Any]] = {}
    unknown: set[str] = set()
    seen_product_ids: set[int] = set()
    observed_on = run_date.isoformat()

    for record in records:
        product_id = int(_first(record, "idProduct", "productId", "cm_product_id", "id"))
        if product_id in seen_product_ids:
            raise ValueError(f"duplicate Cardmarket product id {product_id} for {game}")
        seen_product_ids.add(product_id)

        expansion_id = _optional_int(
            _first(record, "idExpansion", "expansionId", "cm_expansion_id")
        )
        raw_category = str(
            _first(record, "categoryName", "category", "productType", "type", default="")
        ).strip()
        kind = classify(raw_category, category_mapping)
        if not raw_category or raw_category.casefold() not in category_mapping:
            unknown.add(raw_category or "(missing)")

        if expansion_id is not None:
            sets_by_key[expansion_id] = {
                "stable_set_id": stable_set_id(game, expansion_id),
                "game_key": game,
                "cm_expansion_id": expansion_id,
                "name": str(
                    _first(
                        record,
                        "expansionName",
                        "setName",
                        "set",
                        default=f"Expansion {expansion_id}",
                    )
                ),
                "release_date": _first(record, "releaseDate", "dateRelease"),
                "first_seen": observed_on,
                "last_seen": observed_on,
            }

        source_name = str(
            _first(record, "name", "productName", default=f"Product {product_id}")
        )
        identity = catalogue_identity(source_name)
        products.append(
            {
                "stable_product_id": stable_product_id(game, product_id),
                "game_key": game,
                "cm_product_id": product_id,
                "cm_metacard_id": _optional_int(_first(record, "idMetacard")),
                "cm_category_id": _optional_int(_first(record, "idCategory")),
                "cm_expansion_id": expansion_id,
                "name": source_name,
                "display_name": identity.display_name,
                "collector_number": identity.collector_number,
                "image_url": None,
                "image_source": None,
                "tcgplayer_product_url": None,
                "metadata_status": identity.metadata_status,
                "product_kind": kind,
                "raw_category": raw_category,
                "source_date_added": _source_date(_first(record, "dateAdded")),
                "first_seen": observed_on,
                "last_seen": observed_on,
            }
        )

    if not products:
        raise ValueError(f"Cardmarket catalogue for {game} is empty")
    return NormalizedCatalogue(
        games=[
            {
                "stable_game_id": f"cardmarket:game:{game}",
                "cm_game_key": game,
                "name": game_config(game).display_name,
            }
        ],
        sets=sorted(sets_by_key.values(), key=lambda item: int(item["cm_expansion_id"])),
        products=sorted(products, key=lambda item: int(item["cm_product_id"])),
        variants=[],
        unknown_categories=unknown,
    )


def normalize_prices(
    game: str,
    raw: bytes,
    value_date: date,
    product_kinds: Mapping[int, str] | None = None,
) -> pl.DataFrame:
    records = _records(raw)
    variant_suffix = game_config(game).variant_suffix
    product_kinds = product_kinds or {}
    rows: list[dict[str, Any]] = []
    seen_product_ids: set[int] = set()

    for record in records:
        product_id = int(_first(record, "idProduct", "productId", "cm_product_id", "id"))
        if product_id in seen_product_ids:
            raise ValueError(f"duplicate Cardmarket price product id {product_id} for {game}")
        seen_product_ids.add(product_id)
        product_kind = product_kinds.get(product_id, "other")
        common = {
            "stable_product_id": stable_product_id(game, product_id),
            "game_key": game,
            "cm_product_id": product_id,
            "cm_category_id": _optional_int(_first(record, "idCategory")),
            "product_kind": product_kind,
            "value_date": value_date,
        }

        base_avg = _first(record, "avg", "price_avg", "avgPrice", "average")
        base_low = _first(record, "low", "price_low", "lowPrice")
        if base_avg is not None or base_low is not None:
            rows.append(
                {
                    **common,
                    "stable_variant_id": stable_variant_id(game, product_id, "nonfoil"),
                    "variant_key": "nonfoil",
                    "price_low": base_low,
                    "price_avg": base_avg,
                    "avg1": _first(record, "avg1", "avg1Price"),
                    "avg7": _first(record, "avg7", "avg7Price"),
                    "avg30": _first(record, "avg30", "avg30Price"),
                }
            )

        variant_avg = _first(record, f"avg-{variant_suffix}", "foilAvg", "priceFoil")
        variant_low = _first(record, f"low-{variant_suffix}", "foilLow")
        if variant_avg is not None or variant_low is not None:
            rows.append(
                {
                    **common,
                    "stable_variant_id": stable_variant_id(game, product_id, "foil"),
                    "variant_key": "foil",
                    "price_low": variant_low,
                    "price_avg": variant_avg,
                    "avg1": _first(record, f"avg1-{variant_suffix}"),
                    "avg7": _first(record, f"avg7-{variant_suffix}"),
                    "avg30": _first(record, f"avg30-{variant_suffix}"),
                }
            )

    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def variant_records(game: str, prices: pl.DataFrame, run_date: date) -> list[dict[str, Any]]:
    if prices.is_empty():
        return []
    observed_on = run_date.isoformat()
    records = []
    identities = prices.select(
        "stable_variant_id",
        "stable_product_id",
        "game_key",
        "cm_product_id",
        "variant_key",
        "product_kind",
    ).unique()
    for row in identities.iter_rows(named=True):
        records.append({**row, "first_seen": observed_on, "last_seen": observed_on})
    return sorted(records, key=lambda item: str(item["stable_variant_id"]))


def _read_parquet_records(store: ObjectStore, key: str) -> list[dict[str, Any]]:
    if not store.exists(key):
        return []
    return pl.read_parquet(BytesIO(store.read_bytes(key))).to_dicts()


def _merge_catalogue_records(
    existing: list[dict[str, Any]],
    current: list[dict[str, Any]],
    identity_key: str,
) -> list[dict[str, Any]]:
    merged = {str(item[identity_key]): dict(item) for item in existing}
    for item in current:
        identity = str(item[identity_key])
        previous = merged.get(identity)
        if previous is None:
            merged[identity] = dict(item)
            continue
        updated = dict(previous)
        updated.update(item)
        updated["first_seen"] = min(str(previous["first_seen"]), str(item["first_seen"]))
        updated["last_seen"] = max(str(previous["last_seen"]), str(item["last_seen"]))
        merged[identity] = updated
    return [merged[key] for key in sorted(merged)]


def _parquet_bytes(
    records: list[dict[str, Any]],
    columns: list[str],
    sort_by: str,
) -> bytes:
    normalized = [{column: record.get(column) for column in columns} for record in records]
    frame = (
        pl.DataFrame(normalized, infer_schema_length=None).sort(sort_by)
        if normalized
        else pl.DataFrame()
    )
    buffer = BytesIO()
    frame.write_parquet(buffer, compression="zstd", statistics=True)
    return buffer.getvalue()


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n"


def _write_if_changed(
    store: ObjectStore,
    key: str,
    body: bytes,
    content_type: str,
) -> bool:
    if store.exists(key) and store.read_bytes(key) == body:
        return False
    store.write_bytes(key, body, content_type)
    return True


def _output_metadata(key: str, body: bytes, row_count: int) -> dict[str, object]:
    return {
        "key": key,
        "row_count": row_count,
        "sha256": sha256_hex(body),
        "size": len(body),
    }


def _classification_coverage(
    products: list[dict[str, Any]], category_mapping: Mapping[str, str]
) -> float:
    known = sum(
        1 for product in products if str(product["raw_category"]).casefold() in category_mapping
    )
    return known / len(products) if products else 0.0


def _merge_price_month(existing: pl.DataFrame, current: pl.DataFrame) -> pl.DataFrame:
    if existing.is_empty():
        combined = current
    else:
        combined = pl.concat([existing, current], how="diagonal_relaxed")
    return combined.unique(
        ["cm_product_id", "variant_key", "value_date"], keep="last"
    ).sort(["cm_product_id", "variant_key", "value_date"])


def run_normalize(
    run_date: date,
    settings: Settings,
    store: ObjectStore | None = None,
    category_map_path: Path = Path("packages/ingest/category_map.yaml"),
) -> list[GameNormalizationResult]:
    store = store or R2Client(settings)
    manifest = Manifest.from_bytes(store.read_bytes(manifest_key(run_date)))
    if manifest.run_date != run_date.isoformat():
        raise RuntimeError(
            f"manifest run_date {manifest.run_date!r} does not match requested {run_date}"
        )
    errors = validate_manifest(store, manifest, settings.cm_games)
    if errors:
        raise RuntimeError("archive validation failed: " + "; ".join(errors))

    category_mapping = load_category_map(category_map_path)
    category_map_sha = sha256_hex(category_map_path.read_bytes())
    results: list[GameNormalizationResult] = []

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
        product_kinds = {
            int(product["cm_product_id"]): str(product["product_kind"])
            for product in normalized.products
        }
        prices = normalize_prices(game, price_raw, run_date, product_kinds)
        current_variants = variant_records(game, prices, run_date)

        catalogue_prefix = f"derived/catalogue/{game}"
        products_key = f"{catalogue_prefix}/products.parquet"
        sets_key = f"{catalogue_prefix}/sets.parquet"
        variants_key = f"{catalogue_prefix}/variants.parquet"
        products = _merge_catalogue_records(
            _read_parquet_records(store, products_key),
            normalized.products,
            "stable_product_id",
        )
        sets = _merge_catalogue_records(
            _read_parquet_records(store, sets_key),
            normalized.sets,
            "stable_set_id",
        )
        variants = _merge_catalogue_records(
            _read_parquet_records(store, variants_key),
            current_variants,
            "stable_variant_id",
        )
        products_body = _parquet_bytes(products, PRODUCT_COLUMNS, "stable_product_id")
        sets_body = _parquet_bytes(sets, SET_COLUMNS, "stable_set_id")
        variants_body = _parquet_bytes(variants, VARIANT_COLUMNS, "stable_variant_id")

        price_key = f"derived/prices/{game}/{run_date:%Y-%m}.parquet"
        existing_prices = (
            pl.read_parquet(BytesIO(store.read_bytes(price_key)))
            if store.exists(price_key)
            else pl.DataFrame()
        )
        price_month = _merge_price_month(existing_prices, prices)
        price_buffer = BytesIO()
        price_month.write_parquet(price_buffer, compression="zstd", statistics=True)
        price_body = price_buffer.getvalue()

        coverage = _classification_coverage(normalized.products, category_mapping)
        unknown_categories = sorted(normalized.unknown_categories)
        quality_key = f"derived/quality/category-coverage/{run_date.isoformat()}-{game}.json"
        quality_body = _json_bytes(
            {
                "schema_version": 1,
                "game": game,
                "run_date": run_date.isoformat(),
                "catalogue_products": len(normalized.products),
                "classification_coverage": round(coverage, 8),
                "unknown_categories": unknown_categories,
                "category_map_sha256": category_map_sha,
                "status": "pass" if coverage >= 0.99 else "fail",
            }
        )
        if unknown_categories:
            logger.warning(
                "unknown_categories",
                extra={
                    "extra": {
                        "game": game,
                        "categories": unknown_categories,
                        "coverage": coverage,
                    }
                },
            )

        output_bodies = {
            products_key: (products_body, "application/vnd.apache.parquet", len(products)),
            sets_key: (sets_body, "application/vnd.apache.parquet", len(sets)),
            variants_key: (variants_body, "application/vnd.apache.parquet", len(variants)),
            price_key: (price_body, "application/vnd.apache.parquet", price_month.height),
            quality_key: (quality_body, "application/json", 1),
        }
        changed_outputs: list[str] = []
        for key, (body, content_type, _) in output_bodies.items():
            if _write_if_changed(store, key, body, content_type):
                changed_outputs.append(key)
        if coverage < 0.99:
            raise RuntimeError(
                f"{game} category classification coverage {coverage:.2%} is below 99%"
            )

        normalized_manifest_key = f"{catalogue_prefix}/manifest.json"
        normalized_manifest = {
            "schema_version": 1,
            "game": game,
            "generated_for": run_date.isoformat(),
            "source": {
                "catalogue_key": catalogue_file.key,
                "catalogue_sha256": catalogue_file.sha256_uncompressed,
                "priceguide_key": price_file.key,
                "priceguide_sha256": price_file.sha256_uncompressed,
                "category_map_sha256": category_map_sha,
            },
            "classification_coverage": round(coverage, 8),
            "unknown_categories": unknown_categories,
            "outputs": {
                key: _output_metadata(key, body, row_count)
                for key, (body, _, row_count) in output_bodies.items()
            },
        }
        normalized_manifest_body = _json_bytes(normalized_manifest)
        if _write_if_changed(
            store,
            normalized_manifest_key,
            normalized_manifest_body,
            "application/json",
        ):
            changed_outputs.append(normalized_manifest_key)

        run_key = f"derived/ingest_runs/{run_date.isoformat()}-{game}.json"
        run_note = {
            "schema_version": 1,
            "game": game,
            "run_date": run_date.isoformat(),
            "status": "ok",
            "snapshot_sha": price_file.sha256_uncompressed,
            "catalogue_sha": catalogue_file.sha256_uncompressed,
            "catalogue_products": len(normalized.products),
            "catalogue_sets": len(normalized.sets),
            "catalogue_variants": len(current_variants),
            "price_rows": prices.height,
            "classification_coverage": round(coverage, 8),
            "normalized_manifest_key": normalized_manifest_key,
            "normalized_manifest_sha256": sha256_hex(normalized_manifest_body),
        }
        if _write_if_changed(store, run_key, _json_bytes(run_note), "application/json"):
            changed_outputs.append(run_key)

        result = GameNormalizationResult(
            game=game,
            run_date=run_date.isoformat(),
            status="ok",
            catalogue_products=len(normalized.products),
            catalogue_sets=len(normalized.sets),
            catalogue_variants=len(current_variants),
            price_rows=prices.height,
            classification_coverage=round(coverage, 8),
            unknown_categories=unknown_categories,
            changed_outputs=changed_outputs,
        )
        results.append(result)
        logger.info("normalization_complete", extra={"extra": asdict(result)})

    return results


@click.command()
@click.option("--date", "date_value", default="today")
def main(date_value: str) -> None:
    configure_logging()
    results = run_normalize(parse_run_date(date_value), Settings.from_env())
    click.echo(_json_bytes({"results": [asdict(result) for result in results]}).decode(), nl=False)


if __name__ == "__main__":
    main()
