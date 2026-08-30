# Card-image repository findings

## Existing data flow

1. `packages/ingest` archives Cardmarket catalogue and priceguide snapshots in R2.
2. Catalogue normalization writes per-game `products.parquet` and `sets.parquet` objects.
3. `packages/indexengine/indexengine/collector_run.py` calculates the private collector series and enriches constituent rows with catalogue metadata.
4. Versioned private JSON objects are written below `derived/indexes/<methodology>/private_shadow/`.
5. `collector_preview.py` creates the bounded, paginated static projection under `apps/web/source-data/collector`.
6. The web build copies that projection to `apps/web/public/data/collector` and validates it before Next.js and Cloudflare builds.

The image pipeline therefore uses the existing JSON/R2 architecture. It does not introduce a database or alter prices, selection, weighting, or index history.

## Identity currently available

- Every public constituent has a Cardmarket product ID and a stable variant ID.
- Magic can be matched directly through Scryfall's `cardmarket_id` field.
- Downloaded Cardmarket catalogue rows do not expose image URLs or dependable provider set codes.
- Synthetic labels such as `Expansion 1253` are generated when no expansion name is present and are not treated as real set identity.
- Collector numbers parsed from Cardmarket names retain their raw string form but remain candidate-only metadata outside exact provider verification.

The generated readiness report at `reports/images/readiness.md` is the current measurement for all ten games.

## Integration points

- Provider snapshots: `provider-snapshots/<provider>/<snapshot-id>/` in R2 or a local object store.
- Matches: `image-matches/<dataset-version>/<game>/`.
- Active public image manifest: `derived/card-images/<game>/public-manifest.json`.
- Collector output: additive `image` object per constituent. Legacy `image_url` and `image_source` stay available during migration.
- UI: `CollectorCompositionTable` renders only `exact` or `manual` images and retains a fixed-aspect placeholder for every other status.

## Feature and legal gates

Runtime enrichment requires both:

```text
CARD_IMAGES_ENABLED=true
CARD_IMAGES_MAGIC=true
```

Those flags do not bypass publication policy. `packages/indexengine/config/card-images/publication-policy.yaml` remains the hard gate; an exact match with pending rights is exported as `blocked_legal`, without an image URL.

As of the 2026-08-30 Scryfall snapshot, the current Magic basket produces 13,725 exact Cardmarket-ID matches out of 14,608 variant rows (94.0%). Publication remains disabled because this affiliate-funded product still needs an explicit commercial image-rights review.
