# ADR 014: Labelled Preview Index Publication

Status: accepted

## Decision

The public dashboard may expose real Cardmarket-derived index levels, constituent reference prices, current composition, and daily additions or removals before the official 60-day launch gate passes. Every such dataset uses the `preview` status and this disclaimer:

> Provisional index based on the Cardmarket history available so far. Composition and index values may change materially during the 60-day observation period. This is not the official index and is not investment advice.

Synthetic repository fixtures remain excluded from every public export.

## Calculation separation

The official launch controls remain unchanged: the 60-day lookback, target-size gates, monthly rebalance cadence, archive audit, and human cutover review are still mandatory. Under methodology v1.4.0, preview selection uses only the observations available before each effective date, scales observation ratios to that available calendar, applies the same eligibility gates, and then selects the 500 highest-`avg30` distinct singles or 100 highest-`avg30` distinct sealed products. It recalculates provisionally each day. A preview may contain fewer members than the eventual target when fewer products pass the gates.

Official calculations remain under `derived/indexes/<code>`. Preview calculations use `derived/preview/indexes/<code>`, their own manifests, `data_state: preview`, and `cadence: daily_preview`. The public exporter verifies every referenced object checksum before writing repository JSON. Raw and normalized Cardmarket source files remain private.

## Historical treatment

Preview history, membership intervals, and daily selection events are retained as explicitly named `preview-*` files. The official cutover candidate includes those preparation-phase files separately when they exist. It never concatenates preview rows into official history or silently relabels preview values as official observations.

Portfolio benchmarking and editorial weekly reports continue to require `published` official indexes. Preview CSV downloads include an explicit status and warning header.
