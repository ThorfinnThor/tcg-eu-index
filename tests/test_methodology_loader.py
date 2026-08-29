from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from indexengine.methodology import Methodology, MethodologyConfigError

REPO_ROOT = Path(__file__).resolve().parents[1]
V14_PATH = REPO_ROOT / "packages/indexengine/methodologies/v1.4.0.yaml"
V15_PATH = REPO_ROOT / "packages/indexengine/methodologies/v1.5.0-preview.1.yaml"


def _v15_payload() -> dict[str, Any]:
    payload = yaml.safe_load(V15_PATH.read_text())
    assert isinstance(payload, dict)
    return payload


def _write_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "methodology.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def test_archived_v14_is_byte_for_byte_copy_of_active_configuration() -> None:
    active = REPO_ROOT / "packages/indexengine/methodology.yaml"

    assert V14_PATH.read_bytes() == active.read_bytes()


def test_loader_parses_archived_v14_schema() -> None:
    methodology = Methodology.load(V14_PATH)

    assert methodology.schema_version == 1
    assert methodology.methodology_version == "1.4.0"
    assert methodology.families == {}
    assert len(methodology.indexes) == 20
    assert all(definition.target_size is not None for definition in methodology.indexes)
    assert all(definition.public for definition in methodology.indexes)


def test_loader_parses_typed_v15_schema_with_nullable_targets() -> None:
    methodology = Methodology.load(V15_PATH)

    assert methodology.schema_version == 2
    assert methodology.methodology_state == "private_shadow"
    assert methodology.source is not None
    assert methodology.source.provider == "cardmarket"
    assert methodology.calculation is not None
    assert methodology.calculation.price_fallback is None
    assert methodology.activity is not None
    assert methodology.activity.eligibility_gate_enabled is False
    assert len(methodology.families) == 2
    assert methodology.families["collector_singles"].target_size is None
    assert methodology.families["collector_singles"].min_latest_avg30_eur == 10.0
    assert methodology.families["collector_sealed"].min_latest_avg30_eur == 30.0
    assert methodology.families["collector_singles"].constituent_identity == (
        "cm_product_id",
        "variant_key",
    )
    assert len(methodology.indexes) == 20
    assert all(definition.target_size is None for definition in methodology.indexes)
    assert all(not definition.public for definition in methodology.indexes)
    assert methodology.output is not None
    assert methodology.output.public_alias_enabled is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["indexes"][0].update({"family": "missing"}),
            "unknown family",
        ),
        (
            lambda payload: payload["indexes"][1].update({"code": payload["indexes"][0]["code"]}),
            "duplicate index code",
        ),
        (
            lambda payload: payload["families"]["collector_singles"].update(
                {"min_latest_avg30_eur": -1}
            ),
            "expected a number >= 0",
        ),
        (
            lambda payload: payload["output"].update({"public_alias_enabled": True}),
            "must be false for private_shadow",
        ),
    ],
)
def test_invalid_v15_configuration_fails_clearly(
    tmp_path: Path, mutation: Any, message: str
) -> None:
    payload = _v15_payload()
    mutation(payload)

    with pytest.raises(MethodologyConfigError, match=message):
        Methodology.load(_write_payload(tmp_path, payload))


def test_unknown_schema_field_is_rejected(tmp_path: Path) -> None:
    payload = _v15_payload()
    payload["unexpected"] = True

    with pytest.raises(MethodologyConfigError, match="unsupported field"):
        Methodology.load(_write_payload(tmp_path, payload))
