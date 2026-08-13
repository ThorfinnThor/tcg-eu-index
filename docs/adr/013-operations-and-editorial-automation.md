# ADR 013: Operations and Editorial Automation

Status: accepted

## Public operational data

The weekly archive audit exports `apps/web/source-data/archive-health.json`. The contract contains calendar coverage, gap count, checksum-error count, verified-file count, aggregate storage usage, conservative Class A/Class B projections, and gapless cutover dates. It excludes R2 keys, largest-object names, source payloads, card identities, and prices.

The audit workflow commits only this aggregate receipt. The static build publishes it at `data/archive-health/latest.json`; the data-quality page renders it without querying R2.

## Notifications

Scheduled archive, audit, source-check, and report workflows post concise status messages through `scripts/notify_pipeline.py` when `ALERT_DISCORD_WEBHOOK` exists. Notification delivery is best-effort for production workflows so a Discord outage cannot invalidate an otherwise complete archive. The manual `discord-notification-test` workflow uses strict mode and fails unless delivery succeeds.

## Weekly reports

Every Monday the report workflow selects the preceding UTC ISO week. It exits successfully without changes while no real index is published. Once published data exists, it generates a deterministic draft, renders PNG charts, validates the static export and production build, and opens or updates a draft pull request.

Drafts and their source charts are never included in the public export. An editor must verify metrics and flags, add commentary, change the report status to `published`, add `publishedAt`, and consciously decide whether a separate SEO page definition has sufficient demand evidence. The static exporter copies charts into `public/reports/` only for published reports. The automation never marks a report published or indexable.

## Newsletter and portfolio boundaries

Newsletter signup remains disabled unless Vercel has a public HTTPS `NEWSLETTER_ENDPOINT`. The server route validates email and explicit consent, applies a small per-instance abuse limit, and sends the address directly to the configured provider. The provider API key is server-only.

Portfolio CSV data is parsed in the browser, limited to 1 MB and 5,000 rows, checked for duplicate holdings, and stored only in local storage. Without daily public card-price series, the UI shows a two-point cost-basis comparison rather than inventing a daily portfolio path. Durable cross-device portfolios remain a future authenticated-storage feature.
