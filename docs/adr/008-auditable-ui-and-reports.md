# ADR 008: Auditable UI and deterministic report drafts

## Status

Accepted for the JSON-only MVP.

## Decision

Public index pages calculate chart ranges and drawdowns from the exported daily history in the browser. Drawdown uses the running peak, and pure functions cover both calculations with unit tests.

Constituent source records may include `removed_at`. The public table derives the active composition for an `as of` date using `member_since <= as_of < removed_at`, then applies client-side search. This keeps historical additions and removals inspectable without a database.

Weekly report drafts are generated manually with:

```bash
npm --prefix apps/web run reports:generate -- --week YYYY-Www
```

The command reads repository-managed index history, replaces only an unpublished report for the requested week, and writes both `source-data/reports/index.json` and `docs/reports/YYYY-Www.md`. Published reports cannot be overwritten. Human editor review remains required.

## Deferred production integration

True per-product movers, automated weekly runs, and production report commentary require the later Cardmarket-derived import and calculation pipeline. The MVP generator labels unavailable inputs instead of synthesizing them.
