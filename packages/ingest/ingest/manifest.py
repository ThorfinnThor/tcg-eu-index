from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
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
    unchanged_from_previous: bool = False


@dataclass(frozen=True)
class Manifest:
    run_date: str
    files: list[ManifestFile]

    def to_json_bytes(self) -> bytes:
        return json.dumps(asdict(self), indent=2, sort_keys=True).encode()

    @classmethod
    def from_bytes(cls, body: bytes) -> Manifest:
        payload = json.loads(body)
        return cls(
            run_date=payload["run_date"],
            files=[ManifestFile(**item) for item in payload["files"]],
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


def validate_manifest(store: Any, manifest: Manifest, expected_games: list[str]) -> list[str]:
    errors: list[str] = []
    for game in expected_games:
        for kind in ("priceguide", "catalogue"):
            if not any(file.game == game and file.kind == kind for file in manifest.files):
                errors.append(f"missing {kind} for {game}")
    for file in manifest.files:
        try:
            compressed = store.read_bytes(file.key)
            raw = gunzip_body(compressed)
        except Exception as exc:
            errors.append(f"{file.key}: unreadable gzip/json: {exc}")
            continue
        if sha256_hex(raw) != file.sha256_uncompressed:
            errors.append(f"{file.key}: sha256 mismatch")
        if file.kind == "priceguide":
            try:
                payload = json.loads(raw)
                count = len(payload if isinstance(payload, list) else payload.get("data", []))
                if count < 1_000:
                    errors.append(f"{file.key}: price guide below 1000 records")
            except Exception as exc:
                errors.append(f"{file.key}: invalid json: {exc}")
    return errors
