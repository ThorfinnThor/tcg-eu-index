from __future__ import annotations

import json

from ingest.source_check import check_game


class FakeSourceFetcher:
    def fetch(self, url: str) -> bytes:
        if "priceGuide" in url:
            records = [
                {
                    "idProduct": 1,
                    "idCategory": 2,
                    "avg": 3.0,
                    "low": 2.0,
                    "avg1": 3.0,
                    "avg7": 3.0,
                    "avg30": 3.0,
                    "avg-foil": None,
                    "low-foil": None,
                }
            ]
            return json.dumps(
                {"version": 1, "createdAt": "2026-08-09T02:00:00+0200", "priceGuides": records}
            ).encode()

        records = (
            [{"idProduct": 1, "name": "Card", "idCategory": 2, "categoryName": "Single"}]
            if "products_singles_" in url
            else [{"idProduct": 2, "name": "Box", "idCategory": 3, "categoryName": "Box"}]
        )
        return json.dumps(
            {"version": 1, "createdAt": "2026-08-09T01:00:00+0200", "products": records}
        ).encode()


def test_source_check_validates_cross_file_coverage() -> None:
    result = check_game("onepiece", FakeSourceFetcher())
    assert result.status == "pass"
    assert result.price_records == 1
    assert result.catalogue_records == 2
    assert result.catalogue_coverage == 1.0
