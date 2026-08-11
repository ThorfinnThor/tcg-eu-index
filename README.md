# TCG Europe Index

Public, repository-managed listing-price benchmarks for the European One Piece and Pokemon card markets.

## Local development

Requirements: Python 3.12 with `uv`, and Node.js 20 or newer.

```bash
uv sync --all-packages
npm ci --prefix apps/web
npm run dev
```

The web app is available at <http://localhost:3000>. Static public JSON is generated from `apps/web/source-data` before development and production builds.

## Checks

```bash
uv run ruff check .
uv run mypy
uv run pytest
npm --prefix apps/web run data:export
npm --prefix apps/web run data:validate
npm --prefix apps/web run lint
npm --prefix apps/web run test
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e
```

Verify the current official Cardmarket downloads without writing data:

```bash
uv run --package tcg-eu-index-ingest python -m ingest.source_check
```

The public source paths and confirmed JSON schema are recorded in `docs/adr/001-source-schema.md`. The scheduled workflow retains each source-check result as a GitHub artifact for 14 days.

## Daily source archive

The private Cardmarket archive uses GitHub Actions and Cloudflare R2. It is not a runtime dependency of the Vercel site, and Supabase is not required. Activate it only after following `docs/adr/runbook-archiver.md`.

Audit a local archive fixture:

```bash
uv run python scripts/verify_archive.py \
  --store-root /path/to/archive \
  --since YYYY-MM-DD \
  --output archive-audit.json \
  --summary-output archive-audit.md
```

The audit includes archive integrity, exact object-storage usage, conservative R2 operation projections, and per-index readiness for the eventual human cutover review.

Production index values remain repository-managed until enough verified daily snapshots exist for the methodology's observation windows.

## Private normalization

Every successful daily archive run also normalizes the verified catalogue and prices into private R2 Parquet datasets. No raw or normalized per-card feed is exposed by the web application.

The same workflow then recomputes private shadow indexes. Shadow outputs remain in R2 and report `accumulating` until the methodology's observation and constituent gates pass. They do not replace the repository-managed public JSON automatically.

Private shadow outputs include chain-linked values, constituent contributions, rebalance audits, and aggregate analytics for movers, breadth, drawdown, and listing-price volatility. No raw per-card price history is published.

Replay an archived range in production:

```bash
uv run python scripts/backfill.py \
  --since YYYY-MM-DD \
  --until YYYY-MM-DD
```

Add `--store-root /path/to/archive` for a local object-store fixture. A successful replay also recalculates the shadow indexes through the final date. The normalized contracts and stable identity format are recorded in `docs/adr/010-r2-normalized-data.md`; the shadow-index contract is recorded in `docs/adr/011-private-shadow-index-engine.md`.
