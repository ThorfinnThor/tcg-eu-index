# Archiver Runbook

## Purpose

The archive preserves the official public Cardmarket price-guide and catalogue downloads before they are replaced. Cloudflare R2 is private durable storage; Vercel continues to serve the site from repository-generated JSON. Supabase is not part of this workflow.

## One-Time Setup

Create a private R2 bucket named `tcg-raw` and an R2 API token restricted to object read and write access for that bucket. In GitHub, open **Settings > Secrets and variables > Actions** and configure:

Repository secrets:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
```

Repository variables:

```text
R2_BUCKET=tcg-raw
CM_CONTACT_EMAIL=<operator email address>
ARCHIVE_ENABLED=false
```

`ALERT_DISCORD_WEBHOOK` is optional. Do not configure Cardmarket URL templates in production; the verified official URLs are defined in code.

## First Snapshot

1. Open **Actions > cardmarket-daily-archive > Run workflow**.
2. Leave `run_date` as `today` and run the workflow.
3. Confirm that the job is green and that its artifact contains `archive-result.json` and `manifest-latest.json`.
4. Confirm the manifest contains `priceguide` and `catalogue` objects for every configured game. Representative keys are:

```text
cardmarket/priceguide/onepiece/YYYY/MM/YYYY-MM-DD.json.gz
cardmarket/catalogue/onepiece/YYYY/MM/YYYY-MM-DD.json.gz
cardmarket/priceguide/pokemon/YYYY/MM/YYYY-MM-DD.json.gz
cardmarket/catalogue/pokemon/YYYY/MM/YYYY-MM-DD.json.gz
manifests/YYYY-MM-DD.json
```

The complete configured game list is `magic,yugioh,pokemon,onepiece,dragonballsuper,fleshandblood,digimon,lorcana,starwarsunlimited,riftbound`.

5. Set `ARCHIVE_INCEPTION_DATE` to the successful UTC date.
6. Run **cardmarket-archive-audit** manually and confirm it is green.
7. Change `ARCHIVE_ENABLED` to `true`.

The schedule remains inert while `ARCHIVE_ENABLED` is not exactly `true`.

## Daily Operation

`archive.yml` runs at 05:10, 08:10, 11:10, and 14:10 UTC. The first successful attempt validates and writes immutable gzipped snapshots, writes `manifests/YYYY-MM-DD.json` last as the completion marker, normalizes the verified catalogue and prices, recalculates the private shadow indexes, and commits `data/manifest-latest.json` as a visible heartbeat. Later attempts validate the completed archive and skip the expensive normalization and calculation when the repository heartbeat already records that date. A manual run can select `force_reprocess` after a normalization or engine change.

The expansion from two to ten games starts with the 2026-08-12 UTC snapshot. Earlier manifests intentionally retain their original two-game scope and are not rewritten. The weekly audit passes explicit per-game inception dates, so it validates the historical scope and still fails on any missing new-game snapshot from 2026-08-12 onward.

The manifest records checksums, byte sizes, source timestamps, fetch timestamps, and whether each payload is unchanged from the preceding day's snapshot.

`audit.yml` runs every Sunday. It verifies that every daily manifest exists from `ARCHIVE_INCEPTION_DATE` through the current UTC date and performs checksum, decompression, and schema checks on a deterministic 5% sample of archived files. Its GitHub Actions summary also reports:

- exact R2 object counts and stored bytes from one bucket listing,
- storage totals split across raw snapshots, manifests, normalized data, shadow indexes, and receipts,
- conservative monthly Class A and Class B operation projections for the four scheduled attempts per day,
- archive-window, target-size, quality-receipt, and language-scope gates for every index,
- the earliest possible full-lookback and monthly rebalance dates assuming no archive gaps.

The operation figures are deliberately labeled projections. The S3-compatible R2 API does not expose account billing counters; Cloudflare's dashboard remains authoritative. The watchdog uses the R2 Standard monthly free allocation documented in [Cloudflare's R2 pricing](https://developers.cloudflare.com/r2/pricing/), warns at 80% of those limits, and does not convert a cost warning into an archive-integrity failure.

Replay normalization after a code or category-map change:

```bash
uv run python scripts/backfill.py \
  --since YYYY-MM-DD \
  --until YYYY-MM-DD
```

Each successful game/day produces `derived/ingest_runs/YYYY-MM-DD-<game>.json`. A category coverage below 99% fails normalization before its completion manifest and ingest receipt are written.

Each successful calculation produces `derived/calc_runs/YYYY-MM-DD.json`. An `accumulating` result is expected before the full lookback and target-size gates pass. It is not a pipeline failure and does not publish shadow values to the web application.

The first successful calculation for a date also writes `apps/web/source-data/readiness.json` from the aggregate calculation receipt. The heartbeat commit includes this file. It exposes only archive-day counts, target counts, and pass/fail gates; no raw or normalized price is copied into the repository.

## Cutover Rehearsal

The review tool can be exercised before launch. It requires a successful archive-audit JSON file and writes only into a new, empty review directory:

```bash
uv run python scripts/prepare_cutover.py \
  --date YYYY-MM-DD \
  --audit-report archive-audit.json \
  --output-root work/cutover/YYYY-MM-DD
```

Before all gates pass, the command exits non-zero and writes only `cutover-review.json` with the blockers. Once every gate passes, it additionally creates a checksummed `candidate/` tree containing aggregate history, constituent lifecycle data, rebalances, analytics, and metadata patches. The tool refuses output paths inside `apps/web/source-data` and `apps/web/public/data`. It never changes an index to `published`; human sign-off and a separate reviewed commit remain mandatory.

## Missed Day

Cardmarket daily downloads are point-in-time. A missed day is treated as a permanent incident:

1. Open a GitHub issue recording the date, affected game or file, and cause.
2. Do not fabricate a snapshot.
3. Keep the failed audit artifact with the incident.
4. Any future calculation must treat the documented date as missing, not as an unchanged observation.

Run a production audit locally only with the R2 credentials exported:

```bash
uv run python scripts/verify_archive.py \
  --since YYYY-MM-DD \
  --sample-rate 0.05 \
  --output archive-audit.json \
  --summary-output archive-audit.md
```

## Conflict

If a source returns different bytes for an already archived date, the original object is preserved and the candidate is stored beside it as `YYYY-MM-DD.conflict-N.json.gz`. The run fails before writing the daily manifest. Inspect both payloads and retain the GitHub Actions receipt; never overwrite the original object.

## Backup Trigger

The four GitHub schedules are sufficient initially. Add an independent external trigger only after the archive has operated reliably and a second scheduler is justified.

## Alerts

When `ALERT_DISCORD_WEBHOOK` is configured, the archiver reports failed downloads or validation as critical and unchanged source payloads as warnings. GitHub Actions failure notifications remain the primary alert when no webhook is configured.
