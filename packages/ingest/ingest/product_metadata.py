from __future__ import annotations

import html
import re
from dataclasses import dataclass

_TRAILING_COLLECTOR_NUMBER = re.compile(
    r"\s*\(((?=[A-Z0-9 ./_-]*\d)[A-Z0-9]+(?:[ ./_-][A-Z0-9]+)+)\)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CatalogueIdentity:
    display_name: str
    collector_number: str | None
    metadata_status: str


def catalogue_identity(raw_name: str) -> CatalogueIdentity:
    """Normalize the public catalogue label and extract only explicit trailing card codes.

    Cardmarket's downloadable product catalogue has no dedicated collector-number or
    image field. Some games include a printed card code in the product name, such as
    ``Roronoa Zoro (OP01-001)``. We retain provenance by marking that limited case and
    never guess a number from an expansion or product ID.
    """
    normalized = " ".join(html.unescape(raw_name).split())
    match = _TRAILING_COLLECTOR_NUMBER.search(normalized)
    if match is None:
        return CatalogueIdentity(
            display_name=normalized,
            collector_number=None,
            metadata_status="catalogue_only",
        )
    display_name = normalized[: match.start()].strip()
    return CatalogueIdentity(
        display_name=display_name or normalized,
        collector_number=match.group(1),
        metadata_status="collector_number_from_catalogue_name",
    )
