# SEO reference: European TCG Index

Source: `seo_ideas.md`, provided on 2026-09-07. This document is the project reference for future SEO, content, data-page, and affiliate-link work.

## Positioning

Position the site as the European destination for trading-card prices and market intelligence. The index is the analytical layer underneath a broader database of current values, historical trends, rankings, sets, cards, and market reports.

Primary search intent includes European card prices, individual card values, most expensive cards, gainers/losers, and whether a TCG market is rising or falling.

## Canonical information architecture

Use the crawlable hierarchy:

`European TCG Index → Game → Set → Card`

Planned page types:

- Game hubs: `/pokemon/`, `/magic/`
- Market indexes: `/pokemon/market-index/`
- Set pages: `/pokemon/sets/base-set/`
- Permanent card pages: `/pokemon/base-set/charizard-4-102/`
- Rankings: `/pokemon/most-expensive-cards/`, `/pokemon/price-gainers/`, `/pokemon/price-losers/`, `/pokemon/cards-over-100/`
- Market status and new-high/low pages
- Monthly reports: `/reports/2026/08/european-tcg-market/`
- Cross-game comparisons: `/compare/pokemon-vs-mtg/`
- Entity pages where useful: `/pokemon/charizard/`, `/pokemon/pikachu/`

Every important page must be reachable through normal `<a href>` links, not only through JavaScript search.

## Card pages

Card pages should show materially unique data: current European 30-day average, 7/30/90-day and one-year movement, history chart, set/game rank, percentile, high/low observations, variant/language/finish, set and collector number, rarity, index eligibility and history, related printings, Cardmarket/eBay/TCGplayer links, source/methodology, and an actual last-updated timestamp.

Card URLs are permanent. If a card falls below the eligibility threshold, keep its URL and history and state that it is not currently included in the index.

## Set, ranking, and report pages

Set pages should include market value, performance, cards tracked, most valuable card, biggest gainer/loser, median, threshold counts, complete card table, distribution buckets, charts, and links to card pages.

Ranking pages should be generated from factual data and reused across Pokémon, Magic, Yu-Gi-Oh!, One Piece, Lorcana, Dragon Ball, Flesh and Blood, Digimon, Star Wars Unlimited, and Riftbound only when the dataset supports useful differentiation.

Monthly reports should compare all tracked games, indexes, top cards, top sets, largest movements, breadth, new highs/lows, and additions/removals. Reports are intended to become citation and backlink assets.

## SEO and technical rules

- Use unique search-oriented titles, H1s, meta descriptions, introductory copy, and internal anchor text. Avoid generic titles such as “Collector preview”.
- Generate market commentary from actual metrics; do not add generic filler copy.
- Do not index faceted/search URLs such as `?min=10`, `?sort=desc`, or `?foil=true`. Create intentional static landing pages for valuable concepts and keep utility search pages noindex.
- Use a sitemap index split by game and page type, with `lastmod` based on real data changes.
- Add `Dataset`, `DataCatalog`, `DataDownload` where appropriate, plus `BreadcrumbList`, `Organization`, and `WebSite` structured data. Do not present reference prices as `Offer` commerce markup.
- Move to a permanent branded custom domain before large-scale indexing and backlinks.
- Programmatic SEO is acceptable only when each page combines genuinely useful card/set/market data; avoid thin “Card X costs €Y” pages.

## Rollout priority

1. Build game hubs and set pages.
2. Build permanent individual card URLs, starting with high-value/high-demand cards.
3. Add ranking pages and recurring market reports.
4. Add selected entity and comparison pages.
5. Expand only templates that demonstrate useful indexing and search demand.

Start with Pokémon because it has the largest natural hierarchy and search surface. Preserve stable URLs, transparent methodology, historical continuity, and reliable publication throughout.
