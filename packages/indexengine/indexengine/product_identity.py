from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class CollectorProductMetadata:
    cm_product_id: int
    name: str
    set_name: str | None
    collector_number: str | None
    cm_expansion_id: int | None
    image_url: str | None
    image_source: str | None
    tcgplayer_product_url: str | None
    metadata_status: str


def build_collector_product_metadata(
    products: pl.DataFrame,
    sets: pl.DataFrame,
) -> dict[int, CollectorProductMetadata]:
    """Build the presentation identity without changing constituent economics."""
    set_names = _set_names(sets)
    result: dict[int, CollectorProductMetadata] = {}
    for row in products.iter_rows(named=True):
        product_id = int(row["cm_product_id"])
        expansion_id = _optional_int(row.get("cm_expansion_id"))
        result[product_id] = CollectorProductMetadata(
            cm_product_id=product_id,
            name=_display_name(row, product_id),
            set_name=set_names.get(expansion_id) if expansion_id is not None else None,
            collector_number=_optional_text(row.get("collector_number")),
            cm_expansion_id=expansion_id,
            image_url=_https_url(row.get("image_url")),
            image_source=_optional_text(row.get("image_source")),
            tcgplayer_product_url=_tcgplayer_url(row.get("tcgplayer_product_url")),
            metadata_status=_optional_text(row.get("metadata_status")) or "catalogue_only",
        )
    return result


def _set_names(sets: pl.DataFrame) -> dict[int, str]:
    if sets.is_empty() or not {"cm_expansion_id", "name"}.issubset(sets.columns):
        return {}
    return {
        int(row["cm_expansion_id"]): str(row["name"])
        for row in sets.select("cm_expansion_id", "name").iter_rows(named=True)
        if row["cm_expansion_id"] is not None and row["name"] is not None
    }


def _display_name(row: dict[str, object], product_id: int) -> str:
    return (
        _optional_text(row.get("display_name"))
        or _optional_text(row.get("name"))
        or f"Cardmarket product {product_id}"
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    return int(str(value)) if value is not None else None


def _https_url(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    if not text.startswith("https://"):
        raise ValueError("collector product image URL must use HTTPS")
    return text


def _tcgplayer_url(value: object) -> str | None:
    text = _https_url(value)
    if text is not None and not text.startswith("https://www.tcgplayer.com/"):
        raise ValueError("TCGplayer product URL must use www.tcgplayer.com HTTPS")
    return text
