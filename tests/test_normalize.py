from __future__ import annotations

import json
from datetime import date

from ingest.cardmarket import catalogue_urls, combine_catalogues, priceguide_url
from ingest.normalize import load_category_map, normalize_catalogue, normalize_prices


def payload(key: str, records: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"version": 1, "createdAt": "2026-08-09T02:49:05+0200", key: records}
    ).encode()


def test_official_download_urls_use_verified_game_ids() -> None:
    assert priceguide_url("onepiece").endswith("/priceGuide/price_guide_18.json")
    assert priceguide_url("pokemon").endswith("/priceGuide/price_guide_6.json")
    assert catalogue_urls("onepiece")[0].endswith("/productList/products_singles_18.json")
    assert catalogue_urls("pokemon")[1].endswith("/productList/products_nonsingles_6.json")


def test_combine_catalogues_preserves_both_product_groups() -> None:
    combined = combine_catalogues(
        [
            payload("products", [{"idProduct": 1}]),
            payload("products", [{"idProduct": 2}]),
        ]
    )
    assert [row["idProduct"] for row in json.loads(combined)["products"]] == [1, 2]


def test_normalize_official_catalogue_schema() -> None:
    raw = payload(
        "products",
        [
            {
                "idProduct": 690368,
                "name": "Roronoa Zoro (OP01-001)",
                "idCategory": 1621,
                "categoryName": "One Piece Single",
                "idExpansion": 5229,
                "idMetacard": 415369,
                "dateAdded": "2022-12-28 22:11:43",
            }
        ],
    )
    result = normalize_catalogue("onepiece", raw, date(2026, 8, 9), load_category_map())
    assert result.products[0]["product_kind"] == "single"
    assert result.products[0]["raw_category"] == "One Piece Single"
    assert result.sets[0]["cm_expansion_id"] == 5229
    assert result.unknown_categories == set()


def test_normalize_one_piece_foil_prices() -> None:
    raw = payload(
        "priceGuides",
        [
            {
                "idProduct": 690368,
                "avg": 2.48,
                "low": 0.5,
                "avg1": 2.5,
                "avg7": 2.85,
                "avg30": 2.77,
                "avg-foil": 9.5,
                "low-foil": 8.0,
                "avg1-foil": 9.1,
                "avg7-foil": 9.2,
                "avg30-foil": 9.3,
            }
        ],
    )
    rows = normalize_prices("onepiece", raw, date(2026, 8, 9)).to_dicts()
    assert rows[0]["variant_key"] == "nonfoil"
    assert rows[1] == {
        "game_key": "onepiece",
        "cm_product_id": 690368,
        "variant_key": "foil",
        "value_date": date(2026, 8, 9),
        "price_low": 8.0,
        "price_avg": 9.5,
        "avg1": 9.1,
        "avg7": 9.2,
        "avg30": 9.3,
    }


def test_normalize_pokemon_holo_prices_to_internal_foil_variant() -> None:
    raw = payload(
        "priceGuides",
        [{"idProduct": 100, "avg": 3.2, "low": 2.0, "avg-holo": 5.4, "low-holo": 4.8}],
    )
    rows = normalize_prices("pokemon", raw, date(2026, 8, 9)).to_dicts()
    assert rows[1]["variant_key"] == "foil"
    assert rows[1]["price_avg"] == 5.4


def test_normalize_holo_only_product_does_not_create_empty_nonfoil_row() -> None:
    raw = payload(
        "priceGuides",
        [{"idProduct": 101, "idCategory": 1, "avg-holo": 8.2, "low-holo": 7.0}],
    )
    rows = normalize_prices("pokemon", raw, date(2026, 8, 9)).to_dicts()
    assert len(rows) == 1
    assert rows[0]["variant_key"] == "foil"
    assert rows[0]["price_avg"] == 8.2
