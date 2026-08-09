# ADR 001: Cardmarket Source Schema

Status: accepted on 2026-08-09

## Decision

The platform uses only Cardmarket's official public JSON downloads. They require no API key. Game IDs and paths are defined in `packages/ingest/ingest/cardmarket.py`; optional environment templates are reserved for mirrors and fixtures.

Verified sources:

- Announcement: <https://news.cardmarket.com/en/DragonBallSuper/were-making-the-price-guide-and-product-catalogue-available-for-download>
- One Piece price guide page: <https://www.cardmarket.com/en/OnePiece/Data/Price-Guide>
- One Piece product list page: <https://www.cardmarket.com/en/OnePiece/Data/Product-List>
- One Piece price guide: <https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_18.json>
- Pokemon price guide: <https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json>
- One Piece catalogues: `products_singles_18.json` and `products_nonsingles_18.json`
- Pokemon catalogues: `products_singles_6.json` and `products_nonsingles_6.json`

Catalogue paths use the base `https://downloads.s3.cardmarket.com/productCatalog/productList/`. Singles and nonsingles are downloaded separately and combined before normalization.

## Confirmed schema

Price-guide payloads have top-level fields `version`, `createdAt`, and `priceGuides`. Every row contains `idProduct` and `idCategory`. Depending on the product category, a row exposes the nonfoil family (`avg`, `low`, `trend`, `avg1`, `avg7`, and `avg30`), a variant family, or both. The normalizer skips an unavailable family instead of creating an empty price row.

One Piece variant fields use the `-foil` suffix, including `avg-foil`, `low-foil`, `avg1-foil`, `avg7-foil`, and `avg30-foil`. Pokemon uses the corresponding `-holo` suffix. Both are normalized to the internal `foil` variant key.

Catalogue payloads have top-level fields `version`, `createdAt`, and `products`. Each product contains `idProduct`, `name`, `idCategory`, `categoryName`, and, where applicable, `idExpansion`, `idMetacard`, and `dateAdded`. The public catalogue does not provide expansion names, so the normalized fallback is `Expansion <idExpansion>`.

## Validation

`uv run --package tcg-eu-index-ingest python -m ingest.source_check` validates required fields, duplicate product IDs, and cross-file product coverage. `.github/workflows/source-check.yml` runs it daily and can also be started manually. A source check verifies availability and schema only; it does not publish index values.
