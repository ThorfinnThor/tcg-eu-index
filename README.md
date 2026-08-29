# TCG Europe Index

European sale-price indexes for ten active trading card games under development. The current v1.4 preview retains reproducible Top-500 singles and Top-100 sealed price-leader series. The new v1.5 collector singles series includes every eligible Cardmarket variant with positive `avg30` of at least EUR 10; it has no target count, ranking, quota, or concentration cap. Cardmarket defines `avg30` as the average sale price over the last 30 days. The public daily feed is aggregated and does not contain individual sold-article or order records.

The v1.5 singles calculation remains a versioned private shadow until the 60-day and human-cutover controls pass. A bounded, `noindex` public preview projects its values, aggregate diagnostics, and monthly card composition without enabling an official public alias. The v1.5 sealed family is explicitly deferred because the bulk source does not provide rolling sold-price fields for sealed products.
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
npm --prefix apps/web run typecheck:worker
npm --prefix apps/web run build:vinext
npm --prefix apps/web run deploy:dry-run
npm --prefix apps/web run test:e2e
```

## Cloudflare deployment

The Next.js 16 application is packaged for Cloudflare Workers with vinext. Static public data and the versioned methodology are served through the Workers Assets binding; API routes and dynamic pages execute in the Worker runtime.

```bash
npm ci --prefix apps/web
npm --prefix apps/web run build
npm --prefix apps/web run build:vinext
npm --prefix apps/web run deploy:dry-run
npm --prefix apps/web run deploy:vinext
```

`apps/web/wrangler.jsonc` defines the assets, cache, observability, and rate-limit bindings. Configure `NEXT_PUBLIC_SITE_URL` and `NEWSLETTER_ENDPOINT` as Worker variables, and store `NEWSLETTER_API_KEY` as a Wrangler secret. Cloudflare Workers Builds can use `apps/web` as the root directory, `npm run build && npm run build:vinext` as the build command, and `npm run deploy:vinext` as the deploy command.

Marketplace buttons support optional affiliate wrapping through `NEXT_PUBLIC_EBAY_AFFILIATE_URL_TEMPLATE` and `NEXT_PUBLIC_TCGPLAYER_AFFILIATE_URL_TEMPLATE`. Each template must produce HTTPS and may contain `{url}` for the encoded destination and `{custom_id}` for the stable Cardmarket variant identifier. Until a template is configured, the buttons remain ordinary non-affiliate marketplace searches. Affiliate activation requires approved eBay Partner Network and TCGplayer Impact accounts plus a visible disclosure.

Verify the current official Cardmarket downloads without writing data:

```bash
uv run --package tcg-eu-index-ingest python -m ingest.source_check
```

The public source paths and confirmed JSON schema are recorded in `docs/adr/001-source-schema.md`. The scheduled workflow retains each source-check result as a GitHub artifact for 14 days.

## Daily source archive

The private Cardmarket archive uses GitHub Actions and Cloudflare R2. It is not a runtime dependency of the Cloudflare Worker site, and Supabase is not required. Activate it only after following `docs/adr/runbook-archiver.md`.

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

No fixture index values or constituents are published. A checksum-verified preview export publishes provisional aggregate values, current reference prices, and daily composition changes from a dedicated `derived/preview` R2 prefix. Official publication remains pending until enough verified daily snapshots exist for the methodology's observation windows and the cutover review passes.

Each new daily calculation also updates a small aggregate readiness receipt for the static site. It contains archive-day counts and gate states only, never card prices. After all gates pass, prepare an isolated review candidate with `scripts/prepare_cutover.py`; the command cannot write into the public source directories and never publishes automatically.

The Sunday audit publishes a separate aggregate archive-health receipt with coverage, gap counts, verified-file totals, free-tier projections, and gapless launch dates. Detailed R2 object information remains confined to the private workflow artifact.

## Private normalization

Every successful daily archive run also normalizes the verified catalogue and prices into private R2 Parquet datasets. The daily workflow now calculates the enabled v1.5 collector singles definitions into methodology-versioned private R2 objects. Sealed definitions are skipped, not emitted as zero-member indexes. No raw or normalized per-card feed is exposed by the web application.

The same workflow preserves the separate v1.4 calculation and preview outputs. The v1.5 collector runner uses monthly frozen all-eligible singles membership and writes enriched constituent identity fields for presentation. Public export or alias switching is still a separate human action.

Private shadow outputs include chain-linked values, constituent contributions, rebalance audits, and aggregate analytics for movers, breadth, drawdown, and listing-price volatility. No raw per-card price history is published. Preview history and composition archives remain separate from the later official history and are carried into the cutover candidate as labelled preparation-phase files.

The daily archive exports a checksum-verified public projection for the ten enabled
singles collector indexes. Collector routes are enabled in Cloudflare with
`COLLECTOR_PREVIEW_UI_ENABLED=true`, remain excluded from search indexing, and do not
expose raw eligibility diagnostics or per-card price history. Monthly compositions
are checksum-verified and served in pages of 250 variants so every qualifying card
remains reachable without loading a game's entire basket into one Worker response.
The public overview presents only these singles collector previews; the former
fixed-size and sealed series are no longer shown there. The card table offers
price-range views (`EUR 10-100`, `100-1,000`, `1,000-10,000`, and `10,000+`) and an
on-demand search across the complete game index. These are presentation filters over
one benchmark, not separately calculated sub-index series.

## Editorial and optional user features

Once real indexes are published, the Monday workflow generates the prior week's report and charts in a draft pull request. Drafts are excluded from the public export until an editor changes the status to `published` and supplies `publishedAt`.

Newsletter signup activates only when `NEWSLETTER_ENDPOINT` is configured on Cloudflare Workers. Portfolio CSV files remain in the visitor's browser; the tool validates up to 5,000 rows and never fabricates a daily collection series when only cost basis and current reference values are available.

Replay an archived range in production:

```bash
uv run python scripts/backfill.py \
  --since YYYY-MM-DD \
  --until YYYY-MM-DD
```

Add `--store-root /path/to/archive` for a local object-store fixture. A successful replay also recalculates the shadow indexes through the final date. The normalized contracts and stable identity format are recorded in `docs/adr/010-r2-normalized-data.md`; the shadow-index contract is recorded in `docs/adr/011-private-shadow-index-engine.md`.
