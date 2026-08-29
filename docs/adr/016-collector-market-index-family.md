# ADR 016: Uncapped Collector Market Index Family

Status: accepted for private shadow implementation on 2026-08-29

## Context

Methodology v1.4.0 selects the 500 highest-`avg30` eligible singles and the 100 highest-`avg30` eligible sealed products for each game. Those series describe the upper-priced part of each market. They do not measure the complete collector market above an economically meaningful price floor.

Fixed quotas by price, era, rarity, set, metacard, expansion, or product type would replace the top-price bias with a curator-defined basket. Without ownership, inventory, transaction-count, or traded-volume data, the repository cannot prove that such quotas represent a typical collector or the economic size of a segment.

Cardmarket's public price guide does provide aggregated sale-price fields. It does not provide the individual sales, order records, quantities, or transaction-level volume required for market-cap or volume weighting.

## Decision

### Add a new collector family; do not redefine v1.4

Methodology v1.5.0-preview.1 introduces separate, initially private Collector Market series. The existing v1.4 Top-500 and Top-100 series, codes, data, and history remain reproducible and are not relabelled as the new collector benchmark.

The collector code pattern is number-free:

- singles: `<game-prefix>EUCOL`, for example `MTEUCOL`
- sealed: `<game-prefix>EUSCOL`, for example `MTEUSCOL`

The lack of a number is intentional because membership is not capped.

### Objective universe

At each monthly rebalance, the collector index includes every eligible Cardmarket product variant in its game and universe:

- singles: latest positive `avg30` is at least EUR 10
- sealed: latest positive `avg30` is at least EUR 30

The constituent identity is `(cm_product_id, variant_key)`. If both foil and nonfoil variants pass the same rules, both are eligible constituents. There is no best-variant selection, price-band target, metacard cap, expansion cap, or target constituent count.

Price tiers may be calculated later as descriptive analytics. They cannot add, remove, reserve, or reweight constituents in the headline collector index.

### Eligibility and activity

The existing objective history, seasoning, observation, and suspect-zero gates remain eligibility controls. The former `liquidity_score` is renamed `data_quality_score`; it is not treated as market liquidity.

Positive `avg1` observations are recorded as a Trading Activity Proxy. In v1.5.0-preview.1 the proxy is diagnostic only. It does not exclude constituents until its semantics have been validated empirically across games and variants. Turning it into a hard gate requires a newly versioned methodology rather than an in-place configuration change.

### Reference and valuation price

The v1.5.0-preview.1 collector shadow uses `avg30` for both threshold eligibility and daily valuation. Cardmarket defines `AVG30` as the average sale price over the preceding 30 days. No `price_low` fallback is allowed.

An `avg7` alternative may be produced as a private calibration series. It is not the canonical v1.5.0-preview.1 valuation field and cannot replace `avg30` without a versioned decision.

### Weighting and rebalance

Collector indexes are equal-weighted only when membership is established at the monthly rebalance. Weights drift with constituent performance until the next rebalance. Missing constituents are carried and then explicitly suspended under the documented missing-data policy; their weight is not silently redistributed to available constituents.

Public preview membership, once approved, is frozen between monthly rebalances. Daily candidate universes remain private diagnostics.

### Series and cutover

Every series uses:

```text
series_id = "{index_code}:{methodology_version}:{data_state}"
```

v1.5 starts at 1000 on its own first shadow effective date. It is never spliced onto v1.4 history. Public aliases cannot point to v1.5 until the source-history gate, activity-proxy validation, calculation review, and human cutover are complete.

## Consequences

- Constituent counts vary naturally by game and rebalance date.
- Crossing a price threshold affects membership only at a monthly rebalance.
- Cheap bulk cannot dominate because products below EUR 10 singles or EUR 30 sealed are outside the universe.
- High-priced products do not dominate merely because of their absolute price; every eligible variant receives the same target weight at rebalance.
- Games with few eligible products remain transparent rather than filling an arbitrary target by weakening rules.
- Reprints and variants receive weight only because they are separate Cardmarket-traded product variants, not because a curator reserved space for them.
- The current price-leader series may remain useful as separate premium-market indicators.

## Superseded decisions

ADR 015 remains authoritative for methodology v1.4.0 price-leader series. It is superseded only as the design for the new collector-market benchmark.

ADR 014 remains the historical description of v1.4 preview publication. Its daily public preview cadence is superseded for v1.5 collector series by monthly frozen membership.
