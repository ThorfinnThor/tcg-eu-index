# ADR 017: Defer the Sealed Collector Family

Status: accepted for private shadow implementation on 2026-08-29

## Context

The S4 real-archive audit found zero positive Cardmarket `avg1`, `avg7`, or `avg30`
observations for every sealed universe. This was not caused by the catalogue join:
non-single products are present in the official per-game price-guide files, but their
rolling sale-price fields are null.

Cardmarket product pages display rolling one-, seven-, and thirty-day average sale
prices for individual sealed products. The bulk file does not expose those values.
Its available `avg` field is the average price of articles ever sold, while `trend`
is an independently defined Cardmarket trend value. Neither is equivalent to the
required rolling `avg30` contract.

Fetching every individual product page would create a fragile, high-volume scraping
dependency without a stable bulk schema or documented service contract. Listing
prices are not sold prices and remain prohibited as a fallback.

## Decision

Methodology `1.5.0-preview.2` keeps the singles collector family unchanged and marks
the sealed collector family as:

```yaml
calculation_enabled: false
source_status: rolling_sold_price_unavailable
```

The ten sealed definitions and their number-free codes remain reserved, private, and
unpublished. The engine must reject attempts to calculate them. The private audit
reports them as deferred rather than as valid zero-member indexes.

The sealed family may be enabled only by another versioned methodology after one of
these conditions is met:

1. Cardmarket exposes rolling sold-price fields for non-singles in a stable bulk
   download;
2. authorized Cardmarket API access exposes the same fields at an operationally
   sustainable request volume; or
3. another source with auditable European sealed transaction prices is approved.

Lifetime `SELL`, `trend`, current `low`, average listings, and inferred values cannot
be silently substituted.

Authoritative source references:

- Cardmarket price-guide field definitions:
  <https://api.cardmarket.com/ws/documentation/API_2.0%3APriceGuide>
- Cardmarket product price-guide entity semantics:
  <https://api.cardmarket.com/ws/documentation/API_2.0%3AEntities%3AProduct>
- Cardmarket non-singles download announcement:
  <https://news.cardmarket.com/en/Magic/adding-non-singles-and-accessories-to-the-price-guide>
- Cardmarket price-guide downloads:
  <https://www.cardmarket.com/en/Magic/Data/Price-Guide>

## Consequences

- `1.5.0-preview.2` can continue collecting and calibrating the ten singles shadows.
- Sealed routes and outputs remain unavailable and cannot be publicly cut over.
- Existing v1.4 Top-100 sealed data remains reproducible and is not rewritten.
- No historical `1.5.0-preview.1` artifact is mutated or spliced into preview.2.
- A future sealed source starts a newly versioned series with explicit provenance.
