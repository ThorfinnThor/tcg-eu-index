from ingest.product_metadata import catalogue_identity


def test_extracts_explicit_trailing_collector_number() -> None:
    identity = catalogue_identity("Roronoa Zoro (OP01-001)")

    assert identity.display_name == "Roronoa Zoro"
    assert identity.collector_number == "OP01-001"
    assert identity.metadata_status == "collector_number_from_catalogue_name"


def test_does_not_guess_numbers_or_strip_gameplay_labels() -> None:
    identity = catalogue_identity("Kakuna [Bug Bite | Primal Clash]")

    assert identity.display_name == "Kakuna [Bug Bite | Primal Clash]"
    assert identity.collector_number is None
    assert identity.metadata_status == "catalogue_only"


def test_decodes_catalogue_html_entities() -> None:
    identity = catalogue_identity("Whis&#39;s Coercion")

    assert identity.display_name == "Whis's Coercion"
