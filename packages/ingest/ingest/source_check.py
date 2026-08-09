from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import click
import requests
from core.settings import Settings

from ingest.cardmarket import catalogue_urls, game_config, priceguide_url


class SourceFetcher(Protocol):
    def fetch(self, url: str) -> bytes: ...


class HttpSourceFetcher:
    def __init__(self, user_agent: str) -> None:
        self.session = requests.Session()
        self.user_agent = user_agent

    def fetch(self, url: str) -> bytes:
        last_error: requests.RequestException | None = None
        for delay in (0, 5, 30):
            if delay:
                time.sleep(delay)
            try:
                response = self.session.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=120,
                )
                response.raise_for_status()
                return response.content
            except requests.RequestException as exc:
                last_error = exc
        raise RuntimeError(f"failed to fetch {url}: {last_error}")


@dataclass(frozen=True)
class SourceCheck:
    game: str
    source_created_at: str
    price_records: int
    catalogue_records: int
    matched_price_records: int
    catalogue_coverage: float
    status: str


def _object_payload(raw: bytes, expected_key: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Cardmarket payload must be a JSON object")
    if not isinstance(payload.get("createdAt"), str) or not payload["createdAt"]:
        raise ValueError("Cardmarket payload is missing createdAt")
    if "version" not in payload:
        raise ValueError("Cardmarket payload is missing version")
    if not isinstance(payload.get(expected_key), list):
        raise ValueError(f"Cardmarket payload is missing {expected_key}")
    return payload


def _product_ids(records: list[object], label: str) -> set[int]:
    result: set[int] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("idProduct"), int):
            raise ValueError(f"{label} contains a record without integer idProduct")
        product_id = record["idProduct"]
        if product_id in result:
            raise ValueError(f"{label} contains duplicate idProduct {product_id}")
        result.add(product_id)
    if not result:
        raise ValueError(f"{label} is empty")
    return result


def _require_fields(records: list[object], fields: set[str], label: str) -> None:
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"{label} record {position} is not an object")
        missing = fields - record.keys()
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"{label} record {position} is missing {names}")


def check_game(game: str, fetcher: SourceFetcher) -> SourceCheck:
    config = game_config(game)
    price_payload = _object_payload(fetcher.fetch(priceguide_url(game)), "priceGuides")
    catalogue_payloads = [
        _object_payload(fetcher.fetch(url), "products") for url in catalogue_urls(game)
    ]

    prices = price_payload["priceGuides"]
    products = [item for payload in catalogue_payloads for item in payload["products"]]
    price_ids = _product_ids(prices, f"{config.display_name} price guide")
    product_ids = _product_ids(products, f"{config.display_name} catalogue")

    required_price_fields = {"idProduct", "idCategory"}
    required_product_fields = {"idProduct", "name", "idCategory", "categoryName"}
    _require_fields(prices, required_price_fields, f"{config.display_name} price guide")
    _require_fields(products, required_product_fields, f"{config.display_name} catalogue")
    base_fields = {"avg", "low", "avg1", "avg7", "avg30"}
    variant_fields = {f"avg-{config.variant_suffix}", f"low-{config.variant_suffix}"}
    if not any(isinstance(record, dict) and base_fields.issubset(record) for record in prices):
        raise ValueError(f"{config.display_name} base price schema changed")
    if not any(isinstance(record, dict) and variant_fields.issubset(record) for record in prices):
        raise ValueError(f"{config.display_name} variant price schema changed")
    for position, record in enumerate(prices):
        if isinstance(record, dict) and not (
            "avg" in record or f"avg-{config.variant_suffix}" in record
        ):
            raise ValueError(f"{config.display_name} price record {position} has no price family")

    matched = len(price_ids & product_ids)
    coverage = matched / len(price_ids)
    if coverage < 0.95:
        raise ValueError(
            f"{config.display_name} catalogue coverage is {coverage:.2%}, expected at least 95%"
        )

    created_at = max(
        str(price_payload["createdAt"]),
        *(str(payload["createdAt"]) for payload in catalogue_payloads),
    )
    return SourceCheck(
        game=game,
        source_created_at=created_at,
        price_records=len(price_ids),
        catalogue_records=len(product_ids),
        matched_price_records=matched,
        catalogue_coverage=round(coverage, 6),
        status="pass",
    )


@click.command()
@click.option("--game", "games", multiple=True, help="Game key; defaults to CM_GAMES.")
def main(games: tuple[str, ...]) -> None:
    settings = Settings.from_env()
    selected_games = list(games) or settings.cm_games
    fetcher = HttpSourceFetcher(settings.cm_user_agent)
    checks = [asdict(check_game(game, fetcher)) for game in selected_games]
    click.echo(json.dumps({"checks": checks}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
