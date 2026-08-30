# Card-image pipeline runbook

## Local readiness audit

```bash
UV_CACHE_DIR=/private/tmp/tcg-uv-cache uv run python -m indexengine.card_images.cli audit \
  --collector-root apps/web/source-data/collector \
  --output-root reports/images
```

The command is deterministic for the same collector projection. Review `missing-prerequisites.csv` before implementing another provider. The audit also writes `all-rows.csv`: one row for every current non-sealed variant across every game, including its image status and whether a public image URL is present. This is the complete inventory, not a sample.

## Scryfall snapshot

Use a local object store for development:

```bash
UV_CACHE_DIR=/private/tmp/tcg-uv-cache uv run python -m indexengine.card_images.cli sync-scryfall \
  --local-store /private/tmp/tcg-card-images
```

Without `--local-store`, the command uses the configured R2 bucket. The job downloads Scryfall's bulk file once, validates the record count, writes immutable raw and normalized objects, and only then updates the `latest.json` pointer. Re-running an existing snapshot is idempotent.

## Offline Magic matching

```bash
UV_CACHE_DIR=/private/tmp/tcg-uv-cache uv run python -m indexengine.card_images.cli match-magic \
  --dataset-version 2026-08-29 \
  --snapshot scryfall-20260830090538 \
  --local-store /private/tmp/tcg-card-images \
  --collector-root apps/web/source-data/collector \
  --report-root reports/images
```

This step reads only the pinned local snapshot. It performs no provider request and never publishes a name-only match.

## Production activation checklist

1. Review current Scryfall and underlying artwork terms for this commercial/affiliate-funded use.
2. Record reviewer, review date, evidence URLs, attribution, retention, and takedown process in `publication-policy.yaml`.
3. Change `artwork_publication` to `approved` only after that review.
4. Run the automated match and safety checks over every Magic row. Separately, manually verify at least 100 unique products, including two-faced cards, tokens, promos, and unusual layouts. The manual sample is a visual QA control; it is not a cap on the number of cards that may be published.
5. Upload the validated snapshot and match bundle to R2.
6. Enable `CARD_IMAGES_ENABLED=true` and `CARD_IMAGES_MAGIC=true` for the calculation job.
7. Recalculate and export the collector preview.
8. Verify that price/index history checksums are unchanged apart from additive image fields.
9. Confirm image CSP, placeholders, lazy loading, mobile layout, and a deliberate image 404 in staging.

## Deterministic activation QA

Generate the 100-product review sample and release-gate report from the same pinned snapshot:

```bash
UV_CACHE_DIR=/private/tmp/tcg-uv-cache uv run python -m indexengine.card_images.cli qa-magic \
  --dataset-version 2026-08-29 \
  --snapshot scryfall-20260830090538 \
  --local-store /private/tmp/tcg-card-images \
  --collector-root apps/web/source-data/collector \
  --report-root reports/images
```

`all-matches.csv` contains the match outcome for every Magic row, including exact, ambiguous, and provider-missing results. It contains Cardmarket product links, but no direct artwork URL. `qa-sample.csv` contains 100 unique Cardmarket products selected across multi-face cards, unusual layouts, foil variants, languages, and a deterministic coverage fill. It is only the human-review subset and does not limit publication of rows that pass the full automated gates. It contains links to the external Cardmarket and Scryfall product pages, but no direct artwork URL.

The daily archive workflow must rematerialize card-image statuses after exporting a fresh collector projection. In CI, `materialize-web` reads the validated public manifest from R2. For local development, pass `--local-store /private/tmp/tcg-card-images`. This prevents the archive export from silently replacing exact or legally blocked statuses with missing prerequisites.

Manual decisions belong in a separate versioned YAML file with `version`, `dataset_version`, and a `reviews` list containing `source_row_key` and `status: approved|rejected`. Pass it with `--reviews`. Use `--require-ready` only for an activation run; it fails until every gate, including legal policy and all sample reviews, passes.

## Rollback

Disable `CARD_IMAGES_MAGIC` and rerun the collector calculation/export. Existing provider snapshots and match artifacts remain immutable for investigation. To roll back only a bad provider update, repoint `provider-snapshots/scryfall/latest.json` to the last validated snapshot and rerun matching.
