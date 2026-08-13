from __future__ import annotations

from collections import Counter

from indexengine.methodology import Methodology


def test_every_game_has_one_singles_and_one_sealed_index() -> None:
    definitions = Methodology.load().indexes
    universes_by_game = Counter(
        (definition.game_key, definition.universe) for definition in definitions
    )

    assert len(definitions) == 20
    assert len({definition.game_key for definition in definitions}) == 10
    assert set(universes_by_game.values()) == {1}
    assert {universe for _, universe in universes_by_game} == {"singles", "sealed"}
    assert {
        tuple(definition.language_scope) for definition in definitions
    } == {("ALL_CARDMARKET_EUROPE",)}
    assert {
        definition.language_scope_status for definition in definitions
    } == {"resolved_all_cardmarket_europe_languages"}
