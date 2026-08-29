import polars as pl
from indexengine.product_identity import build_collector_product_metadata


def test_builds_catalogue_identity_with_nullable_image() -> None:
    products = pl.DataFrame(
        [
            {
                "cm_product_id": 42,
                "cm_expansion_id": 7,
                "name": "Roronoa Zoro (OP01-001)",
                "display_name": "Roronoa Zoro",
                "collector_number": "OP01-001",
                "image_url": None,
                "image_source": None,
                "tcgplayer_product_url": "https://www.tcgplayer.com/product/123/test",
                "metadata_status": "collector_number_from_catalogue_name",
            }
        ]
    )
    sets = pl.DataFrame([{"cm_expansion_id": 7, "name": "Romance Dawn"}])

    metadata = build_collector_product_metadata(products, sets)[42]

    assert metadata.name == "Roronoa Zoro"
    assert metadata.set_name == "Romance Dawn"
    assert metadata.collector_number == "OP01-001"
    assert metadata.image_url is None
    assert metadata.tcgplayer_product_url == "https://www.tcgplayer.com/product/123/test"


def test_rejects_non_https_image_sources() -> None:
    products = pl.DataFrame(
        [{"cm_product_id": 42, "name": "Card", "image_url": "http://example.test/card.jpg"}]
    )

    try:
        build_collector_product_metadata(products, pl.DataFrame())
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("non-HTTPS image URL was accepted")
