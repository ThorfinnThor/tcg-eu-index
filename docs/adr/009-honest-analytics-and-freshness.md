# ADR 009: Honest MVP analytics, provenance, and freshness

## Status

Accepted for the JSON-only MVP.

## Decision

The public index page must display only figures derivable from repository data. Available-history return, maximum drawdown, best and worst daily returns, positive-day ratio, 30-day annualized listing-price volatility, and calculation-flag counts are derived directly from daily index history and covered by unit tests.

Per-card movers and contribution rankings are not shown until per-constituent daily return and weight series exist. The UI states that limitation explicitly. Synthetic rankings based on row order are prohibited.

The public status payload includes dataset version, generation timestamp, and source identifier. The UI derives freshness from the latest snapshot date using these thresholds:

- 0-2 days: fresh
- 3-7 days: delayed
- more than 7 days: stale

Contract completeness and date freshness are separate signals. A structurally complete fixture dataset may still be stale.

Constituent filters are mirrored into URL query parameters so historical compositions can be linked and reproduced. Draft reports remain accessible for review but use `noindex`; only published report pages enter the sitemap.

## Production follow-up

Connecting the confirmed Cardmarket download source is the gate for true per-card movers, contribution leaders, and automated daily freshness.
