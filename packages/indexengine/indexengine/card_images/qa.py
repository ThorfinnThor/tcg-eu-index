from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode

import yaml
from core.store import ObjectStore

from indexengine.card_images.contracts import (
    CanonicalCardIdentity,
    CardImageAsset,
    CardImageMatch,
    public_image_from_match,
)
from indexengine.card_images.pipeline import DEFAULT_POLICY
from indexengine.card_images.policy import load_publication_policy
from indexengine.card_images.readiness import magic_identities_from_public_collector
from indexengine.card_images.scryfall import (
    ScryfallCardRecord,
    load_scryfall_snapshot,
    match_magic_identities,
)

DEFAULT_RELEASE_GATES = Path(
    "packages/indexengine/config/card-images/release-gates.yaml"
)


@dataclass(frozen=True)
class ReleaseThresholds:
    minimum_exact_coverage: float
    maximum_ambiguous_ratio: float
    minimum_manual_sample: int


@dataclass(frozen=True)
class MagicQaCandidate:
    source_row_key: str
    cardmarket_product_id: int
    cardmarket_name: str
    finish: str
    provider_card_id: str
    provider_name: str
    set_code: str | None
    collector_number: str | None
    language: str | None
    layout: str | None
    face_count: int

    @property
    def tags(self) -> tuple[str, ...]:
        result: list[str] = []
        if self.face_count > 1:
            result.append("multi_face")
        if self.layout not in {None, "normal", "transform", "modal_dfc"}:
            result.append("special_layout")
        if self.finish == "foil":
            result.append("foil")
        if self.language not in {None, "en"}:
            result.append("non_english")
        if not result:
            result.append("standard")
        return tuple(result)


@dataclass(frozen=True)
class MagicQaResult:
    schema_version: int
    dataset_version: str
    provider_snapshot_id: str
    rows: int
    exact_matches: int
    exact_coverage_ratio: float
    ambiguous_matches: int
    ambiguous_ratio: float
    sample_size: int
    approved_sample_rows: int
    gates: dict[str, bool]
    publication_ready: bool


def build_magic_activation_qa(
    store: ObjectStore,
    collector_root: Path,
    dataset_version: str,
    output_root: Path,
    *,
    snapshot_id: str | None = None,
    policy_path: Path = DEFAULT_POLICY,
    gates_path: Path = DEFAULT_RELEASE_GATES,
    reviews_path: Path | None = None,
) -> MagicQaResult:
    """Build a deterministic, URL-safe activation sample and release-gate report."""
    policy = load_publication_policy(policy_path)["scryfall"]
    thresholds = load_release_thresholds(gates_path, "magic")
    snapshot = load_scryfall_snapshot(store, snapshot_id)
    identities = magic_identities_from_public_collector(
        collector_root,
        source_updated_at=dataset_version,
    )
    matches, assets = match_magic_identities(identities, snapshot, policy)
    identity_by_key = {identity.source_row_key: identity for identity in identities}
    record_by_id = {record.provider_card_id: record for record in snapshot.records}
    candidates = _qa_candidates(
        matches,
        assets,
        identity_by_key,
        record_by_id,
    )
    sample = select_magic_qa_sample(
        candidates,
        thresholds.minimum_manual_sample,
        seed=dataset_version,
    )
    reviews = load_manual_reviews(reviews_path, dataset_version)
    sample_keys = {item.source_row_key for item, _ in sample}
    unexpected_reviews = set(reviews) - sample_keys
    if unexpected_reviews:
        raise ValueError(
            "manual card-image reviews do not match the deterministic QA sample"
        )
    approved = sum(reviews.get(item.source_row_key) == "approved" for item, _ in sample)
    rows = len(matches)
    exact = sum(match.status == "exact" for match in matches)
    ambiguous = sum(match.status == "ambiguous" for match in matches)
    exact_ratio = exact / rows if rows else 0.0
    ambiguous_ratio = ambiguous / rows if rows else 0.0
    no_unresolved_urls = all(
        _public_url_is_safe(match, assets.get(match.asset_id) if match.asset_id else None)
        for match in matches
    )
    gates = {
        "exact_coverage": exact_ratio >= thresholds.minimum_exact_coverage,
        "ambiguous_ratio": ambiguous_ratio <= thresholds.maximum_ambiguous_ratio,
        "sample_size": len(sample) >= thresholds.minimum_manual_sample,
        "manual_sample_review": len(sample) >= thresholds.minimum_manual_sample
        and approved == len(sample),
        "legal_policy": policy.artwork_publication == "approved",
        "no_unresolved_public_urls": no_unresolved_urls,
    }
    result = MagicQaResult(
        schema_version=1,
        dataset_version=dataset_version,
        provider_snapshot_id=snapshot.snapshot_id,
        rows=rows,
        exact_matches=exact,
        exact_coverage_ratio=exact_ratio,
        ambiguous_matches=ambiguous,
        ambiguous_ratio=ambiguous_ratio,
        sample_size=len(sample),
        approved_sample_rows=approved,
        gates=gates,
        publication_ready=all(gates.values()),
    )
    output_root.mkdir(parents=True, exist_ok=True)
    _write_sample_csv(output_root / "qa-sample.csv", sample, reviews)
    (output_root / "qa-sample.md").write_text(_sample_markdown(result, sample))
    (output_root / "activation.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n"
    )
    (output_root / "activation.md").write_text(_activation_markdown(result, thresholds))
    return result


def load_release_thresholds(path: Path, game: str) -> ReleaseThresholds:
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("card-image release gates must use version 1")
    games = payload.get("games")
    raw = games.get(game) if isinstance(games, dict) else None
    if not isinstance(raw, dict):
        raise ValueError(f"card-image release gates are missing {game}")
    thresholds = ReleaseThresholds(
        minimum_exact_coverage=float(raw["minimum_exact_coverage"]),
        maximum_ambiguous_ratio=float(raw["maximum_ambiguous_ratio"]),
        minimum_manual_sample=int(raw["minimum_manual_sample"]),
    )
    if not 0 <= thresholds.minimum_exact_coverage <= 1:
        raise ValueError("minimum exact coverage must be between zero and one")
    if not 0 <= thresholds.maximum_ambiguous_ratio <= 1:
        raise ValueError("maximum ambiguous ratio must be between zero and one")
    if thresholds.minimum_manual_sample < 1:
        raise ValueError("minimum manual sample must be positive")
    return thresholds


def load_manual_reviews(path: Path | None, dataset_version: str) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"manual card-image review file does not exist: {path}")
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("manual card-image reviews must use version 1")
    if payload.get("dataset_version") != dataset_version:
        raise ValueError("manual card-image review dataset version mismatch")
    rows = payload.get("reviews")
    if not isinstance(rows, list):
        raise ValueError("manual card-image reviews must contain a review list")
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("source_row_key"), str):
            raise ValueError("manual card-image review has an invalid source row key")
        status = str(row.get("status", ""))
        if status not in {"approved", "rejected"}:
            raise ValueError("manual card-image review status must be approved or rejected")
        key = row["source_row_key"]
        if key in result:
            raise ValueError(f"duplicate manual card-image review {key}")
        result[key] = status
    return result


def select_magic_qa_sample(
    candidates: list[MagicQaCandidate],
    sample_size: int,
    *,
    seed: str,
) -> list[tuple[MagicQaCandidate, str]]:
    """Select unique products across risky layouts, finishes, and languages."""
    if sample_size < 1:
        raise ValueError("QA sample size must be positive")
    unique: dict[int, MagicQaCandidate] = {}
    for candidate in sorted(candidates, key=lambda item: _rank(seed, item.source_row_key)):
        unique.setdefault(candidate.cardmarket_product_id, candidate)
    pool = list(unique.values())
    selected: list[tuple[MagicQaCandidate, str]] = []
    selected_products: set[int] = set()
    quotas = (
        ("multi_face", min(15, sample_size)),
        ("special_layout", min(15, sample_size)),
        ("foil", min(25, sample_size)),
        ("non_english", min(10, sample_size)),
    )
    for tag, quota in quotas:
        tagged = sorted(
            (item for item in pool if tag in item.tags),
            key=lambda item: _rank(f"{seed}:{tag}", item.source_row_key),
        )
        added = 0
        for item in tagged:
            if item.cardmarket_product_id in selected_products:
                continue
            selected.append((item, tag))
            selected_products.add(item.cardmarket_product_id)
            added += 1
            if added >= quota or len(selected) >= sample_size:
                break
        if len(selected) >= sample_size:
            break
    for item in sorted(pool, key=lambda value: _rank(seed, value.source_row_key)):
        if len(selected) >= sample_size:
            break
        if item.cardmarket_product_id in selected_products:
            continue
        selected.append((item, "coverage_fill"))
        selected_products.add(item.cardmarket_product_id)
    return selected


def _qa_candidates(
    matches: list[CardImageMatch],
    assets: dict[str, CardImageAsset],
    identities: dict[str, CanonicalCardIdentity],
    records: dict[str, ScryfallCardRecord],
) -> list[MagicQaCandidate]:
    result: list[MagicQaCandidate] = []
    for match in matches:
        if match.status != "exact" or not match.asset_id or not match.provider_card_id:
            continue
        asset = assets[match.asset_id]
        identity = identities[match.source_row_key]
        record = records[match.provider_card_id]
        result.append(
            MagicQaCandidate(
                source_row_key=identity.source_row_key,
                cardmarket_product_id=identity.cardmarket_product_id,
                cardmarket_name=identity.cardmarket_name_raw,
                finish=identity.finish,
                provider_card_id=record.provider_card_id,
                provider_name=record.name_raw,
                set_code=record.set_code,
                collector_number=record.collector_number,
                language=record.language,
                layout=record.layout,
                face_count=len(asset.faces),
            )
        )
    return result


def _public_url_is_safe(match: CardImageMatch, asset: CardImageAsset | None) -> bool:
    public = public_image_from_match(match, asset)
    if public.status in {"exact", "manual"}:
        return public.normal_url is not None
    return public.normal_url is None


def _rank(seed: str, source_row_key: str) -> str:
    return hashlib.sha256(f"{seed}\x1f{source_row_key}".encode()).hexdigest()


def _cardmarket_url(candidate: MagicQaCandidate) -> str:
    query = {"idProduct": str(candidate.cardmarket_product_id)}
    if candidate.finish == "foil":
        query["isFoil"] = "Y"
    return f"https://www.cardmarket.com/en/Magic/Products?{urlencode(query)}"


def _write_sample_csv(
    path: Path,
    sample: list[tuple[MagicQaCandidate, str]],
    reviews: dict[str, str],
) -> None:
    fields = (
        "source_row_key",
        "sample_reason",
        "review_status",
        "cardmarket_product_id",
        "cardmarket_name",
        "finish",
        "provider_card_id",
        "provider_name",
        "set_code",
        "collector_number",
        "language",
        "layout",
        "face_count",
        "cardmarket_url",
        "scryfall_url",
    )
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for candidate, reason in sample:
            writer.writerow(
                {
                    **{
                        key: _csv_safe(value)
                        for key, value in asdict(candidate).items()
                    },
                    "sample_reason": reason,
                    "review_status": reviews.get(candidate.source_row_key, "pending"),
                    "cardmarket_url": _cardmarket_url(candidate),
                    "scryfall_url": f"https://scryfall.com/card/{candidate.provider_card_id}",
                }
            )


def _csv_safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _sample_markdown(
    result: MagicQaResult,
    sample: list[tuple[MagicQaCandidate, str]],
) -> str:
    reasons: dict[str, int] = {}
    for _, reason in sample:
        reasons[reason] = reasons.get(reason, 0) + 1
    lines = [
        "# Magic card-image QA sample",
        "",
        f"Dataset `{result.dataset_version}`, snapshot `{result.provider_snapshot_id}`.",
        "",
        "This deterministic sample contains no direct artwork URLs. Reviewers compare "
        "the linked Cardmarket product with the linked Scryfall card and record "
        "decisions in the versioned manual-review YAML.",
        "",
        "| Sample reason | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in sorted(reasons.items()))
    lines.extend(("", f"Total: {len(sample)} unique Cardmarket products.", ""))
    return "\n".join(lines)


def _activation_markdown(
    result: MagicQaResult,
    thresholds: ReleaseThresholds,
) -> str:
    lines = [
        "# Magic card-image activation",
        "",
        f"Publication ready: **{'yes' if result.publication_ready else 'no'}**.",
        "",
        f"Exact coverage: {result.exact_coverage_ratio:.2%} "
        f"(minimum {thresholds.minimum_exact_coverage:.2%}).",
        f"Ambiguous ratio: {result.ambiguous_ratio:.2%} "
        f"(maximum {thresholds.maximum_ambiguous_ratio:.2%}).",
        f"Manual sample: {result.approved_sample_rows}/{result.sample_size} approved "
        f"(minimum {thresholds.minimum_manual_sample}).",
        "",
        "| Gate | Status |",
        "|---|---|",
    ]
    lines.extend(
        f"| {gate.replace('_', ' ')} | {'pass' if passed else 'blocked'} |"
        for gate, passed in result.gates.items()
    )
    return "\n".join(lines) + "\n"
