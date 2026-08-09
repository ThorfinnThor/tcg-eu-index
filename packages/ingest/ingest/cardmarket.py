from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

DOWNLOAD_ROOT = "https://downloads.s3.cardmarket.com/productCatalog"


@dataclass(frozen=True)
class CardmarketGame:
    key: str
    game_id: int
    display_name: str
    variant_suffix: str


GAMES: dict[str, CardmarketGame] = {
    "onepiece": CardmarketGame("onepiece", 18, "One Piece", "foil"),
    "pokemon": CardmarketGame("pokemon", 6, "Pokemon", "holo"),
}


def game_config(game: str) -> CardmarketGame:
    try:
        return GAMES[game]
    except KeyError as exc:
        supported = ", ".join(sorted(GAMES))
        raise ValueError(f"unsupported Cardmarket game {game!r}; supported: {supported}") from exc


def priceguide_url(game: str) -> str:
    config = game_config(game)
    return f"{DOWNLOAD_ROOT}/priceGuide/price_guide_{config.game_id}.json"


def catalogue_urls(game: str) -> tuple[str, str]:
    config = game_config(game)
    prefix = f"{DOWNLOAD_ROOT}/productList/products"
    return (
        f"{prefix}_singles_{config.game_id}.json",
        f"{prefix}_nonsingles_{config.game_id}.json",
    )


def combine_catalogues(payloads: list[bytes]) -> bytes:
    if len(payloads) != 2:
        raise ValueError("Cardmarket catalogue requires singles and nonsingles payloads")

    parsed: list[dict[str, Any]] = []
    for raw in payloads:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
            raise ValueError("Cardmarket catalogue payload is missing products")
        parsed.append(payload)

    products = [product for payload in parsed for product in payload["products"]]
    combined = {
        "version": parsed[0].get("version"),
        "createdAt": max(str(payload.get("createdAt", "")) for payload in parsed),
        "products": products,
    }
    return json.dumps(combined, separators=(",", ":"), ensure_ascii=False).encode()
