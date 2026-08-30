from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from indexengine.card_images.contracts import (
    CanonicalCardIdentity,
    Finish,
    normalize_card_name,
    source_row_key,
)

_SYNTHETIC_SET = re.compile(r"^Expansion\s+\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class ImageReadinessRow:
    game: str
    total_rows: int
    unique_cardmarket_products: int
    with_set_name: int
    with_set_code: int
    with_collector_number: int
    with_language: int
    with_artwork_variant: int
    with_provider_card_id: int
    parsed_identifier_candidates: int
    missing_prerequisite: int


@dataclass(frozen=True)
class ImageReadinessResult:
    schema_version: int
    generated_for: str
    games: tuple[ImageReadinessRow, ...]


def audit_public_collector(
    collector_root: Path,
    output_root: Path,
) -> ImageReadinessResult:
    """Audit the latest published singles composition for every collector game."""
    index_payload = _json_object(collector_root / "index.json")
    generated_for = str(index_payload["generated_for"])
    game_results: list[ImageReadinessRow] = []
    missing_rows: list[dict[str, str]] = []
    parsed_rows: list[dict[str, str]] = []
    all_rows: list[dict[str, str]] = []
    for index in sorted(index_payload["indexes"], key=lambda item: str(item["game_key"])):
        code = str(index["code"])
        if code.endswith("SCOL"):
            continue
        game = str(index["game_key"])
        members = latest_composition_rows(collector_root, code)
        counters: Counter[str] = Counter()
        unique_products: set[int] = set()
        for member in members:
            product_id = int(member["cm_product_id"])
            unique_products.add(product_id)
            set_name = _real_set_name(member.get("set_name"))
            collector_number = _optional_text(member.get("collector_number"))
            metadata_status = str(member.get("metadata_status", ""))
            set_code = _optional_text(member.get("set_code"))
            language = _optional_text(member.get("language"))
            artwork_variant = _optional_text(member.get("artwork_variant"))
            provider_card_id = _optional_text(member.get("provider_card_id"))
            counters["with_set_name"] += set_name is not None
            counters["with_set_code"] += set_code is not None
            counters["with_collector_number"] += collector_number is not None
            counters["with_language"] += language is not None
            counters["with_artwork_variant"] += artwork_variant is not None
            counters["with_provider_card_id"] += provider_card_id is not None
            parsed = "from_catalogue_name" in metadata_status
            counters["parsed_identifier_candidates"] += parsed
            missing = _missing_prerequisites(
                game,
                set_name=set_name,
                set_code=set_code,
                collector_number=collector_number,
                artwork_variant=artwork_variant,
                provider_card_id=provider_card_id,
            )
            counters["missing_prerequisite"] += bool(missing)
            row_key = source_row_key(
                game,
                product_id,
                str(member.get("variant_key", "unknown")),
            )
            image = member.get("image")
            image_status = (
                str(image.get("status", "invalid"))
                if isinstance(image, dict)
                else "not_materialized"
            )
            all_rows.append(
                {
                    "game": game,
                    "source_row_key": row_key,
                    "cardmarket_product_id": str(product_id),
                    "cardmarket_name_raw": str(member.get("name", "")),
                    "variant_key": str(member.get("variant_key", "unknown")),
                    "image_status": image_status,
                    "has_public_image_url": str(bool(member.get("image_url"))).lower(),
                }
            )
            if missing:
                missing_rows.append(
                    {
                        "game": game,
                        "source_row_key": row_key,
                        "cardmarket_product_id": str(product_id),
                        "cardmarket_name_raw": str(member.get("name", "")),
                        "missing_fields": ",".join(missing),
                        "recommended_next_step": _next_step(game, missing),
                    }
                )
            if parsed and collector_number:
                parsed_rows.append(
                    {
                        "game": game,
                        "source_row_key": row_key,
                        "cardmarket_product_id": str(product_id),
                        "cardmarket_name_raw": str(member.get("name", "")),
                        "raw_match": collector_number,
                        "parser": f"{game}_catalogue_name",
                        "parser_version": "1.0.0",
                        "confidence": "candidate_only",
                    }
                )
        game_results.append(
            ImageReadinessRow(
                game=game,
                total_rows=len(members),
                unique_cardmarket_products=len(unique_products),
                with_set_name=counters["with_set_name"],
                with_set_code=counters["with_set_code"],
                with_collector_number=counters["with_collector_number"],
                with_language=counters["with_language"],
                with_artwork_variant=counters["with_artwork_variant"],
                with_provider_card_id=counters["with_provider_card_id"],
                parsed_identifier_candidates=counters["parsed_identifier_candidates"],
                missing_prerequisite=counters["missing_prerequisite"],
            )
        )
    result = ImageReadinessResult(1, generated_for, tuple(game_results))
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "readiness.json", asdict(result))
    (output_root / "readiness.md").write_text(_markdown(result))
    _write_csv(
        output_root / "missing-prerequisites.csv",
        missing_rows,
        (
            "game",
            "source_row_key",
            "cardmarket_product_id",
            "cardmarket_name_raw",
            "missing_fields",
            "recommended_next_step",
        ),
    )
    _write_csv(
        output_root / "parsed-identifiers-to-review.csv",
        parsed_rows,
        (
            "game",
            "source_row_key",
            "cardmarket_product_id",
            "cardmarket_name_raw",
            "raw_match",
            "parser",
            "parser_version",
            "confidence",
        ),
    )
    _write_csv(
        output_root / "all-rows.csv",
        all_rows,
        (
            "game",
            "source_row_key",
            "cardmarket_product_id",
            "cardmarket_name_raw",
            "variant_key",
            "image_status",
            "has_public_image_url",
        ),
    )
    return result


def latest_composition_rows(collector_root: Path, code: str) -> list[dict[str, Any]]:
    composition = _json_object(collector_root / code / "composition.json")
    rebalances = composition.get("rebalances")
    if not isinstance(rebalances, list) or not rebalances:
        return []
    selected = sorted(rebalances, key=lambda item: str(item["effective_date"]))[-1]
    rows: list[dict[str, Any]] = []
    for page in sorted(selected["pages"], key=lambda item: int(item["page"])):
        payload = _json_object(collector_root / code / str(page["path"]))
        constituents = payload.get("constituents")
        if not isinstance(constituents, list):
            raise ValueError(f"collector composition page {page['path']} has no constituents")
        rows.extend(item for item in constituents if isinstance(item, dict))
    return rows


def magic_identities_from_public_collector(
    collector_root: Path,
    *,
    source_updated_at: str,
) -> list[CanonicalCardIdentity]:
    members = latest_composition_rows(collector_root, "MTEUCOL")
    identities: list[CanonicalCardIdentity] = []
    seen: set[str] = set()
    for member in members:
        product_id = int(member["cm_product_id"])
        finish_raw = str(member.get("variant_key", "unknown"))
        finish = finish_raw if finish_raw in {"foil", "nonfoil"} else "unknown"
        row_key = source_row_key("magic", product_id, finish_raw)
        if row_key in seen:
            continue
        seen.add(row_key)
        collector_number = _optional_text(member.get("collector_number"))
        set_name = _real_set_name(member.get("set_name"))
        identities.append(
            CanonicalCardIdentity(
                schema_version=1,
                game="magic",
                subgame=None,
                source_row_key=row_key,
                cardmarket_product_id=product_id,
                cardmarket_name_raw=str(member["name"]),
                name_normalized=normalize_card_name(str(member["name"])),
                set_name_raw=set_name,
                set_code_raw=_optional_text(member.get("set_code")),
                set_code_canonical=_optional_text(member.get("set_code")),
                set_provider_id=None,
                collector_number_raw=collector_number,
                collector_number_canonical=collector_number,
                language=_optional_text(member.get("language")),
                finish=cast(Finish, finish),
                source_variant_raw=None,
                edition=None,
                artwork_variant=None,
                source_updated_at=source_updated_at,
            )
        )
    identities.sort(key=lambda item: item.source_row_key)
    return identities


def identities_from_public_collector(
    collector_root: Path,
    code: str,
    game: str,
    *,
    source_updated_at: str,
) -> list[CanonicalCardIdentity]:
    """Build stable source identities for any collector singles index."""
    members = latest_composition_rows(collector_root, code)
    identities: list[CanonicalCardIdentity] = []
    seen: set[str] = set()
    for member in members:
        product_id = int(member["cm_product_id"])
        finish_raw = str(member.get("variant_key", "unknown"))
        finish = finish_raw if finish_raw in {"foil", "nonfoil"} else "unknown"
        row_key = source_row_key(game, product_id, finish_raw)
        if row_key in seen:
            continue
        seen.add(row_key)
        collector_number = _optional_text(member.get("collector_number"))
        set_code = _optional_text(member.get("set_code"))
        if set_code is None and collector_number and "-" in collector_number:
            set_code = collector_number.rsplit("-", 1)[0]
        set_name = _real_set_name(member.get("set_name"))
        name = str(member["name"])
        identities.append(
            CanonicalCardIdentity(
                schema_version=1,
                game=game,
                subgame=_optional_text(member.get("subgame")),
                source_row_key=row_key,
                cardmarket_product_id=product_id,
                cardmarket_name_raw=name,
                name_normalized=normalize_card_name(name),
                set_name_raw=set_name,
                set_code_raw=set_code,
                set_code_canonical=set_code,
                set_provider_id=(
                    str(member["cm_expansion_id"])
                    if member.get("cm_expansion_id") is not None
                    else None
                ),
                collector_number_raw=collector_number,
                collector_number_canonical=collector_number,
                language=_optional_text(member.get("language")),
                finish=cast(Finish, finish),
                source_variant_raw=finish_raw,
                edition=_optional_text(member.get("edition")),
                artwork_variant=None,
                source_updated_at=source_updated_at,
            )
        )
    identities.sort(key=lambda item: item.source_row_key)
    return identities


def _missing_prerequisites(
    game: str,
    *,
    set_name: str | None,
    set_code: str | None,
    collector_number: str | None,
    artwork_variant: str | None,
    provider_card_id: str | None,
) -> list[str]:
    if game == "magic":
        return []
    if provider_card_id:
        return []
    required = {
        "pokemon": ["set_code", "collector_number"],
        "yugioh": ["set_code", "artwork_variant"],
        "onepiece": ["collector_number", "artwork_variant"],
        "digimon": ["collector_number", "artwork_variant"],
        "lorcana": ["set_code", "collector_number"],
        "starwarsunlimited": ["set_code", "collector_number", "artwork_variant"],
        "fleshandblood": ["set_code", "collector_number", "artwork_variant"],
        "dragonballsuper": ["collector_number", "artwork_variant", "subgame"],
        "riftbound": ["set_code", "collector_number", "artwork_variant"],
    }.get(game, ["provider_card_id"])
    values = {
        "set_name": set_name,
        "set_code": set_code,
        "collector_number": collector_number,
        "artwork_variant": artwork_variant,
        "provider_card_id": provider_card_id,
        "subgame": None,
        "approved_credentials": None,
    }
    return [field for field in required if not values.get(field)]


def _next_step(game: str, missing: list[str]) -> str:
    if "artwork_variant" in missing:
        return "Enrich the exact printing/artwork variant before provider matching"
    if "set_code" in missing or "collector_number" in missing:
        return "Map the Cardmarket expansion and printed card number to the provider catalogue"
    return "Add an approved exact provider identifier"


def _real_set_name(value: object) -> str | None:
    text = _optional_text(value)
    if text is None or _SYNTHETIC_SET.fullmatch(text):
        return None
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    rows.sort(key=lambda item: (item["game"], item["source_row_key"]))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _markdown(result: ImageReadinessResult) -> str:
    lines = [
        "# Card image readiness",
        "",
        f"Generated for `{result.generated_for}`.",
        "",
        "| Game | Rows | Unique products | Real sets | Numbers | Missing prerequisites |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row.game} | {row.total_rows} | {row.unique_cardmarket_products} | "
        f"{row.with_set_name} | {row.with_collector_number} | {row.missing_prerequisite} |"
        for row in result.games
    )
    return "\n".join(lines) + "\n"
