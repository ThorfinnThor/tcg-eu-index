# ADR 009: Honest MVP analytics, provenance, and freshness

## Status

Accepted for the JSON-only MVP.

## Decision

The public index page must display only figures derivable from repository data. Return, maximum drawdown, best and worst daily returns, positive-day ratio, 30-day annualized listing-price volatility, and calculation-flag counts are derived directly from daily index history and covered by unit tests.

Repository fixture observations are internal validation history. They must not appear in public charts, downloads, constituents, reports, portfolio calculations, return analytics, or risk analytics. Index metadata records both `history_start_date` and `history_start_kind`; the exporter publishes observations only when both the index status and history provenance are `published`.

Per-card movers and contribution rankings are not shown until per-constituent daily return and weight series exist. The UI states that limitation explicitly. Synthetic rankings based on row order are prohibited.

The public status payload includes dataset version, generation timestamp, and source identifier. The UI derives freshness from the latest snapshot date using these thresholds:

- 0-2 days: fresh
- 3-7 days: delayed
- more than 7 days: stale

Contract completeness and date freshness are separate signals. An accumulating index has zero public-data completeness and no public freshness date.

Constituent filters are mirrored into URL query parameters so published historical compositions can be linked and reproduced. Draft reports remain internal; only published report pages enter the public export and sitemap.

## Production follow-up

Accumulating enough validated daily snapshots and normalized observations from the confirmed Cardmarket downloads is the gate for true movers, contribution leaders, and automated daily freshness. Private per-card observations remain in R2; only derived aggregate analytics are candidates for public export.
