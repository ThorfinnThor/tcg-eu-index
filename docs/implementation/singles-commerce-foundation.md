# Singles index and commerce foundation

## Sprint outcome

This sprint connects the enabled `1.5.0-preview.2` singles family to the daily private
R2 pipeline and prepares its constituent presentation for marketplace monetization.
Sealed remains excluded from calculation and presentation.

The daily collector runner now:

- reads verified normalized Cardmarket catalogue and price history;
- calculates only families with `calculation_enabled: true`;
- freezes all eligible EUR 10+ singles variants at monthly rebalances;
- writes versioned private schema-v2 history, composition, contributions, diagnostics,
  and manifests;
- enriches each constituent with Cardmarket product ID, clean display name, set,
  explicit collector number when available, image metadata, and an optional direct
  TCGplayer product URL;
- reports constituent metadata coverage without changing eligibility or weights.

No public alias, v1.4 artifact, or official history is changed by the runner.

## Real archive evidence

GitHub Actions run
[`33267738854`](https://github.com/ThorfinnThor/tcg-eu-index/actions/runs/33267738854)
completed successfully against the real 2026-08-29 archive after the implementation
merged. It normalized all configured catalogues, ran the existing shadow indexes, and
wrote all ten enabled collector-singles bundles to private R2 paths.

The retained `collector-result.json` receipt reports:

- 10 preview indexes and 36,536 active EUR 10+ variants in total;
- 18 to 20 observable archive days and 11 to 13 calculated value days;
- 14,608 Magic, 5,377 Yu-Gi-Oh!, 2,126 One Piece, 8,695 Pokemon, 1,781
  Dragon Ball Super, 1,582 Flesh and Blood, 829 Digimon, 506 Lorcana, 730
  Star Wars: Unlimited, and 302 Riftbound variants;
- one deterministic monthly rebalance and six versioned output objects per index.

The first production run exposed a late nullable-metadata schema-inference edge case.
PR #20 fixed it with full-record schema inference and a regression test before the
successful rerun. The current complete Python suite contains 95 passing tests.

## Identity and image provenance

The official Cardmarket product download exposes product ID, product name, category,
expansion ID, metacard ID, and date added. It does not expose a dedicated collector
number or image URL. Names and sets are therefore first-party catalogue fields.

Some games include an explicit printed code in the catalogue name, for example
`Roronoa Zoro (OP01-001)`. The normalizer extracts only that explicit trailing code
and records `collector_number_from_catalogue_name`. It never guesses a number from a
product ID, expansion, card title, or marketplace search result.

Image fields stay nullable until a licensed or explicitly permitted provider is
connected. The UI renders an honest `Image pending` placeholder and reports artwork
coverage. Supported presentation hosts are allowlisted; arbitrary remote image hosts
cannot be rendered.

## Commerce contract

Each card row always retains its direct Cardmarket product link. It also derives an
unambiguous commerce query from card name, collector number, and set name for eBay and
TCGplayer. If a verified direct TCGplayer product URL exists, that URL takes precedence
over search.

Affiliate tracking is disabled by default. It activates independently for each market
only when the corresponding public URL template is configured:

```text
NEXT_PUBLIC_EBAY_AFFILIATE_URL_TEMPLATE
NEXT_PUBLIC_TCGPLAYER_AFFILIATE_URL_TEMPLATE
```

Templates may use `{url}` and `{custom_id}`. Activated links are marked `sponsored`
and `nofollow`, display `Ad`, and trigger the page-level commission disclosure. This
keeps commercial routing separate from index prices, selection, and valuation.

## Remaining external dependencies

The code path is ready, but two external approvals/data contracts remain:

1. image and card-number coverage for games whose Cardmarket catalogue name does not
   include a printed number;
2. approved eBay Partner Network and TCGplayer Impact accounts with their official
   deep-link templates or API credentials.

The recommended enrichment source should map directly to `cm_product_id`, provide
source provenance, permit public image display, and preferably expose a stable
TCGplayer product URL. Fuzzy name-only matches must be reviewed rather than silently
published.

## Release controls

- collector routes expose a feature-flagged, `noindex` public preview;
- the web projection contains summary, history, monthly composition, and aggregate
  diagnostics, but no raw per-card price history or raw eligibility diagnostics;
- v1.5 outputs remain under `private_shadow` R2 prefixes;
- no affiliate template is configured in repository defaults;
- the official public alias/cutover still requires 60 observable days, two monthly compositions, final
  Sol review, and separate human authorization.
