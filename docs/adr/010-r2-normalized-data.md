# ADR 010: Private Normalized Cardmarket Data

Status: accepted

The production normalization layer uses Cloudflare R2 as its canonical persistence layer. Supabase is not required for collection or normalization and remains an optional future admin or user-data store.

Daily data flow:

```text
official Cardmarket downloads
  -> immutable raw R2 snapshot and manifest
  -> validated deterministic normalization
  -> private catalogue and monthly price Parquet in R2
  -> later aggregate index calculation
  -> small public JSON contract
  -> Vercel build and CDN
```

Private normalized keys:

```text
derived/catalogue/<game>/products.parquet
derived/catalogue/<game>/sets.parquet
derived/catalogue/<game>/variants.parquet
derived/catalogue/<game>/manifest.json
derived/prices/<game>/YYYY-MM.parquet
derived/quality/category-coverage/YYYY-MM-DD-<game>.json
derived/ingest_runs/YYYY-MM-DD-<game>.json
```

Products, sets, and variants use deterministic Cardmarket-based string identities. Foil and nonfoil price families become separate variant rows only when that family contains a usable average or low price. Catalogue category classification must cover at least 99% of current products before the normalized manifest and successful ingest receipt are written.

The monthly price Parquet contains private per-product observations and is never published or packaged into the web app. Public pages continue to use small generated JSON files containing aggregate index values, selected constituents, analytics, and freshness metadata. No public endpoint may expose the raw or normalized daily card-price feed.

Reprocessing is idempotent. A repeated day deduplicates by product, variant, and date, produces byte-identical output, and skips writes when bytes have not changed. `scripts/backfill.py` replays any archived date range through the same code path.
