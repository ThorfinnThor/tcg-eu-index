# ADR 015: Price-Ranked Top 500 Singles and Top 100 Sealed Indexes

Status: accepted

## Decision

Every singles benchmark targets 500 distinct Cardmarket products. Every sealed benchmark targets 100 distinct Cardmarket products. After the versioned history and data-quality eligibility gates pass, candidates are ranked by their latest Cardmarket `avg30` reference price from highest to lowest and the first N products are selected.

If multiple eligible variants exist for one Cardmarket product, only the highest-priced eligible variant may enter. Reference price is the primary rank; data score and stable variant identity are deterministic tie-breakers. There is no incumbent retention or entry buffer, because such a buffer would cause the published composition to diverge from the stated top-price universe.

## Consequences

- An index may hold fewer than its target while fewer eligible distinct products exist.
- Preview composition is ranked daily; official composition remains monthly after the 60-day launch controls and human cutover.
- Equal weighting and chain linking are unchanged. “Top 500” and “Top 100” describe constituent selection, not market-cap weighting.
- The public composition table displays reference-price rank and calls the former liquidity metric a data score, because Cardmarket guide data does not establish executed trading volume.
- Renamed singles codes use the `500` suffix. Legacy public URLs permanently redirect to their new canonical codes.
