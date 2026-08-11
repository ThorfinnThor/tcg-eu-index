# ADR 001: Cardmarket Source Schema

Status: amended on 2026-08-11

## Decision

The platform uses only Cardmarket's official public JSON downloads. They require no API key. Game IDs and paths are defined in `packages/ingest/ingest/cardmarket.py`; optional environment templates are reserved for mirrors and fixtures.

Verified sources:

- Announcement: <https://news.cardmarket.com/en/DragonBallSuper/were-making-the-price-guide-and-product-catalogue-available-for-download>
- One Piece price guide page: <https://www.cardmarket.com/en/OnePiece/Data/Price-Guide>
- One Piece product list page: <https://www.cardmarket.com/en/OnePiece/Data/Product-List>
- Price guides use `priceGuide/price_guide_<game-id>.json`.
- Catalogues use `productList/products_singles_<game-id>.json` and `productList/products_nonsingles_<game-id>.json`.

Verified game IDs on 2026-08-11:

| Key | Game | Cardmarket ID | Variant suffix |
|---|---|---:|---|
| `magic` | Magic: The Gathering | 1 | `foil` |
| `yugioh` | Yu-Gi-Oh! | 3 | `foil` |
| `pokemon` | Pokemon | 6 | `holo` |
| `dragonballsuper` | Dragon Ball Super | 13 | `foil` |
| `fleshandblood` | Flesh and Blood | 16 | `foil` |
| `digimon` | Digimon | 17 | `foil` |
| `onepiece` | One Piece | 18 | `foil` |
| `lorcana` | Disney Lorcana | 19 | `foil` |
| `starwarsunlimited` | Star Wars: Unlimited | 21 | `foil` |
| `riftbound` | Riftbound | 22 | `foil` |

Catalogue paths use the base `https://downloads.s3.cardmarket.com/productCatalog/productList/`. Singles and nonsingles are downloaded separately and combined before normalization.

## Confirmed schema

Price-guide payloads have top-level fields `version`, `createdAt`, and `priceGuides`. Every row contains `idProduct` and `idCategory`. Depending on the product category, a row exposes the nonfoil family (`avg`, `low`, `trend`, `avg1`, `avg7`, and `avg30`), a variant family, or both. The normalizer skips an unavailable family instead of creating an empty price row.

All configured games except Pokemon use the `-foil` suffix, including `avg-foil`, `low-foil`, `avg1-foil`, `avg7-foil`, and `avg30-foil`. Pokemon uses the corresponding `-holo` suffix. Both families are normalized to the internal `foil` variant key.

Catalogue payloads have top-level fields `version`, `createdAt`, and `products`. Each product contains `idProduct`, `name`, `idCategory`, `categoryName`, and, where applicable, `idExpansion`, `idMetacard`, and `dateAdded`. The public catalogue does not provide expansion names, so the normalized fallback is `Expansion <idExpansion>`.

## Validation

`uv run --package tcg-eu-index-ingest python -m ingest.source_check` validates required fields, duplicate product IDs, and cross-file product coverage. `.github/workflows/source-check.yml` runs it daily and can also be started manually. A source check verifies availability and schema only; it does not publish index values.
