# ADR 011: Private Shadow Index Engine

Status: accepted

Phase C calculates deterministic shadow indexes from the private normalized R2 data. It does not replace the repository-managed public JSON until the observation windows, target constituent counts, and quality checks pass a separate cutover review.

Private output keys:

```text
derived/indexes/<code>/rebalances.json
derived/indexes/<code>/daily-values.parquet
derived/indexes/<code>/contributions.parquet
derived/indexes/<code>/analytics.json
derived/indexes/<code>/quality/YYYY-MM-DD.json
derived/indexes/<code>/manifest.json
derived/calc_runs/YYYY-MM-DD.json
```

The engine recomputes from the available normalized history on every run. Rebalances are monthly. History, observation coverage, seasoning, price-floor, and suspect-zero checks determine eligibility; eligible products are then ranked by the latest Cardmarket `avg30` reference price in descending order. The exact top N distinct products are selected when enough eligible products exist, with no retention buffer. Daily values are equal-weighted and chain-linked. Missing archive dates remain gaps. Constituent prices can be carried for the configured number of days, after which that constituent is suspended until a fresh observation arrives. Daily returns are capped according to the versioned methodology.

The completion manifest is written last and contains source and output checksums. Re-running unchanged inputs must produce byte-identical output and no object writes. Per-card contributions and constituent selections remain private in R2. Only a later, explicitly approved export may generate the small aggregate JSON contract consumed by Vercel.

`analytics.json` contains deterministic daily aggregate records for 1, 7, and 30 calendar-day windows: top and bottom movers, contribution leaders and laggards, seven-day breadth, running drawdown, and annualized 30-day listing-price volatility. Whole-market unchanged snapshots keep the index return at zero but are excluded from mover and breadth observations so source staleness cannot masquerade as a flat market. Product names and derived returns may later enter the small public contract; raw prices remain private.

Cardmarket's confirmed files do not expose a reliable language field. The launch methodology therefore includes every language represented in the official Cardmarket Europe catalogue. It does not infer language from product names and does not claim an unsupported EN/DE-only universe. This policy resolves the language gate without discarding products on unreliable metadata.

`build_public_membership_contract` defines and tests the cutover shape for constituent lifecycle intervals and rebalance events. It preserves removal and later re-entry as separate membership intervals, enriches identities with catalogue names and sets, and carries human-readable selection reasons. The function is deliberately side-effect free: it does not write `derived/public`, upload to Vercel, or bypass the cutover review.
