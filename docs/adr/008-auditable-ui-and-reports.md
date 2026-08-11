# ADR 008: Auditable UI and deterministic report drafts

## Status

Accepted for the JSON-only MVP.

## Decision

Public index pages calculate chart ranges and drawdowns from the exported daily history in the browser. Drawdown uses the running peak, and pure functions cover both calculations with unit tests.

Constituent source records may include `removed_at`. The public table derives the active composition for an `as of` date using `member_since <= as_of < removed_at`, then applies client-side search. This keeps historical additions and removals inspectable without a database.

The static export also derives `indexes/<code>/rebalances.json`. Once an index is published, the constituent explorer offers a current/historical composition view, a two-date membership comparison, and monthly or ISO-week grouping of actual rebalance events. Weekly grouping never implies a weekly rebalance: weeks without an event have no membership change. Validation fixtures are never included in public exports or user-facing calculations.

Membership is modeled as an interval, not one mutable row per card. If the same variant leaves and later re-enters, the export keeps two intervals distinguished by `member_since`, preserving the complete audit trail.

Weekly report drafts are generated manually with:

```bash
npm --prefix apps/web run reports:generate -- --week YYYY-Www
```

The command reads repository-managed index history, replaces only an unpublished report for the requested week, and writes both `source-data/reports/index.json` and `docs/reports/YYYY-Www.md`. Published reports cannot be overwritten. Human editor review remains required, and draft reports are excluded from the public export.

## Deferred production integration

True per-product movers, automated weekly runs, and production report commentary require the later Cardmarket-derived import and calculation pipeline. The MVP generator labels unavailable inputs instead of synthesizing them.
