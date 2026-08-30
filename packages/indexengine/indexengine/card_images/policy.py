from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

PolicyState = Literal["approved", "pending", "blocked", "blocked_credentials"]


@dataclass(frozen=True)
class ProviderPolicy:
    provider: str
    games: tuple[str, ...]
    metadata_access: PolicyState
    artwork_publication: PolicyState
    may_hotlink: bool | None
    may_mirror: bool | None
    attribution_required: bool | None
    reviewed_at: str | None
    evidence: tuple[str, ...]

    @property
    def legal_status(self) -> Literal["approved", "pending", "blocked"]:
        if self.artwork_publication == "approved":
            return "approved"
        if self.artwork_publication == "pending":
            return "pending"
        return "blocked"


def load_publication_policy(path: Path) -> dict[str, ProviderPolicy]:
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("card-image publication policy must use version 1")
    providers = payload.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ValueError("card-image publication policy has no providers")
    result: dict[str, ProviderPolicy] = {}
    valid_states = {"approved", "pending", "blocked", "blocked_credentials"}
    for provider, raw in providers.items():
        if not isinstance(raw, dict):
            raise ValueError(f"publication policy for {provider} must be an object")
        metadata_access = str(raw.get("metadata_access", "pending"))
        artwork_publication = str(raw.get("artwork_publication", "pending"))
        if metadata_access not in valid_states or artwork_publication not in valid_states:
            raise ValueError(f"publication policy for {provider} has an invalid state")
        games = raw.get("games")
        evidence = raw.get("evidence", [])
        if not isinstance(games, list) or not all(isinstance(item, str) for item in games):
            raise ValueError(f"publication policy for {provider} has invalid games")
        if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
            raise ValueError(f"publication policy for {provider} has invalid evidence")
        result[str(provider)] = ProviderPolicy(
            provider=str(provider),
            games=tuple(games),
            metadata_access=metadata_access,  # type: ignore[arg-type]
            artwork_publication=artwork_publication,  # type: ignore[arg-type]
            may_hotlink=_optional_bool(raw.get("may_hotlink")),
            may_mirror=_optional_bool(raw.get("may_mirror")),
            attribution_required=_optional_bool(raw.get("attribution_required")),
            reviewed_at=_optional_text(raw.get("reviewed_at")),
            evidence=tuple(evidence),
        )
    return result


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("publication policy booleans must be true, false, or null")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
