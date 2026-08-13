# TCG Europe Index

European listing-price indexes for ten active trading card games under development. Public values remain unavailable while the Cardmarket observation history accumulates.

Every covered game has separate singles and sealed-product indexes. The same daily source archive feeds both universes.
The language universe includes every language represented in the official Cardmarket Europe catalogue because the confirmed downloads do not expose a reliable language field.

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

The daily archive covers Magic: The Gathering, Yu-Gi-Oh!, Pokemon, One Piece, Dragon Ball Super, Flesh and Blood, Digimon, Disney Lorcana, Star Wars: Unlimited, and Riftbound.

Audit a local archive fixture:

```bash
uv run python scripts/verify_archive.py \
  --store-root /path/to/archive \
  --since YYYY-MM-DD \
  --output archive-audit.json \
  --summary-output archive-audit.md
```

The audit includes archive integrity, exact object-storage usage, conservative R2 operation projections, and per-index readiness for the eventual human cutover review.

No fixture index values or constituents are published. Production values remain pending until enough verified daily snapshots exist for the methodology's observation windows and the cutover review passes.

Each new daily calculation also updates a small aggregate readiness receipt for the static site. It contains archive-day counts and gate states only, never card prices. After all gates pass, prepare an isolated review candidate with `scripts/prepare_cutover.py`; the command cannot write into the public source directories and never publishes automatically.

The Sunday audit publishes a separate aggregate archive-health receipt with coverage, gap counts, verified-file totals, free-tier projections, and gapless launch dates. Detailed R2 object information remains confined to the private workflow artifact.

## Private normalization

Every successful daily archive run also normalizes the verified catalogue and prices into private R2 Parquet datasets. No raw or normalized per-card feed is exposed by the web application.

The same workflow then recomputes private shadow indexes. Shadow outputs remain in R2 and report `accumulating` until the methodology's observation and constituent gates pass. They do not replace the repository-managed public JSON automatically.

Private shadow outputs include chain-linked values, constituent contributions, rebalance audits, and aggregate analytics for movers, breadth, drawdown, and listing-price volatility. No raw per-card price history is published.

## Editorial and optional user features

Once real indexes are published, the Monday workflow generates the prior week's report and charts in a draft pull request. Drafts are excluded from the public export until an editor changes the status to `published` and supplies `publishedAt`.

Newsletter signup activates only when `NEWSLETTER_ENDPOINT` is configured on Vercel. Portfolio CSV files remain in the visitor's browser; the tool validates up to 5,000 rows and never fabricates a daily collection series when only cost basis and current reference values are available.

Replay an archived range in production:

```bash
uv run python scripts/backfill.py \
  --since YYYY-MM-DD \
  --until YYYY-MM-DD
```

Add `--store-root /path/to/archive` for a local object-store fixture. A successful replay also recalculates the shadow indexes through the final date. The normalized contracts and stable identity format are recorded in `docs/adr/010-r2-normalized-data.md`; the shadow-index contract is recorded in `docs/adr/011-private-shadow-index-engine.md`.
