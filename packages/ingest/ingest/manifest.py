from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from core.r2 import gunzip_body, sha256_hex


@dataclass(frozen=True)
class ManifestFile:
    game: str
    kind: str
    key: str
    sha256_uncompressed: str
    size_uncompressed: int
    fetched_at: str
    headers: dict[str, str]
    source_created_at: str | None = None
    unchanged_from_previous: bool = False


@dataclass(frozen=True)
class Manifest:
    run_date: str
    files: list[ManifestFile]
    schema_version: int = 1

    def to_json_bytes(self) -> bytes:
        return json.dumps(asdict(self), indent=2, sort_keys=True).encode()

    @classmethod
    def from_bytes(cls, body: bytes) -> Manifest:
        payload = json.loads(body)
        return cls(
            run_date=payload["run_date"],
            files=[ManifestFile(**item) for item in payload["files"]],
            schema_version=payload.get("schema_version", 1),
        )

    @property
    def games(self) -> set[str]:
        return {file.game for file in self.files}


def manifest_key(run_date: date) -> str:
    return f"manifests/{run_date.isoformat()}.json"


def latest_pointer(manifest: Manifest) -> dict[str, Any]:
    return {
        "date": manifest.run_date,
        "files": [
            {
                "game": file.game,
                "kind": file.kind,
                "sha256_uncompressed": file.sha256_uncompressed,
                "key": file.key,
            }
            for file in manifest.files
        ],
    }


def _payload_records(payload: Any, kind: str) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    keys = ("priceGuides", "data") if kind == "priceguide" else ("products",)
    for key in keys:
        records = payload.get(key)
        if isinstance(records, list):
            return records
    return None


def validate_manifest_structure(manifest: Manifest, expected_games: list[str]) -> list[str]:
    errors: list[str] = []
    parsed_run_date: date | None = None
    try:
        parsed_run_date = date.fromisoformat(manifest.run_date)
    except (TypeError, ValueError):
        errors.append(f"invalid run_date {manifest.run_date!r}")
    if manifest.schema_version != 1:
        errors.append(f"unsupported manifest schema_version {manifest.schema_version}")
    identities = [(file.game, file.kind) for file in manifest.files]
    if len(identities) != len(set(identities)):
        errors.append("duplicate game/kind entries")
    for game in expected_games:
        for kind in ("priceguide", "catalogue"):
            if not any(file.game == game and file.kind == kind for file in manifest.files):
                errors.append(f"missing {kind} for {game}")
    expected_identities = {
        (game, kind) for game in expected_games for kind in ("priceguide", "catalogue")
    }
    for file in manifest.files:
        if (file.game, file.kind) not in expected_identities:
            errors.append(f"unexpected manifest entry {file.game}/{file.kind}")
        if parsed_run_date is not None:
            expected_key = (
                f"cardmarket/{file.kind}/{file.game}/{parsed_run_date:%Y}/"
                f"{parsed_run_date:%m}/{manifest.run_date}.json.gz"
            )
            if file.key != expected_key:
                errors.append(f"{file.key}: expected key {expected_key}")
        if len(file.sha256_uncompressed) != 64:
            errors.append(f"{file.key}: invalid sha256")
        if file.size_uncompressed <= 0:
            errors.append(f"{file.key}: invalid uncompressed size")
        try:
            datetime.fromisoformat(file.fetched_at)
        except (TypeError, ValueError):
            errors.append(f"{file.key}: invalid fetched_at")
    return errors


def validate_manifest(
    store: Any,
    manifest: Manifest,
    expected_games: list[str],
    selected_keys: set[str] | None = None,
) -> list[str]:
    errors = validate_manifest_structure(manifest, expected_games)
    for file in manifest.files:
        if selected_keys is not None and file.key not in selected_keys:
            continue
        try:
            compressed = store.read_bytes(file.key)
            raw = gunzip_body(compressed)
        except Exception as exc:
            errors.append(f"{file.key}: unreadable gzip/json: {exc}")
            continue
        if sha256_hex(raw) != file.sha256_uncompressed:
            errors.append(f"{file.key}: sha256 mismatch")
        if len(raw) != file.size_uncompressed:
            errors.append(f"{file.key}: uncompressed size mismatch")
        try:
            payload = json.loads(raw)
            records = _payload_records(payload, file.kind)
            if records is None:
                errors.append(f"{file.key}: missing {file.kind} records")
            elif file.kind == "priceguide" and len(records) < 1_000:
                errors.append(f"{file.key}: price guide below 1000 records")
        except Exception as exc:
            errors.append(f"{file.key}: invalid json: {exc}")
    return errors
