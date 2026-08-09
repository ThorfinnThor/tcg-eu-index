# ADR 001: Cardmarket Source Schema

Status: pending human confirmation

The platform may only use Cardmarket official public daily downloads. The exact production URL templates and record schemas must be confirmed from Cardmarket's official downloads page before Phase B production runs.

Paste one current sample price-guide record and one current sample catalogue record here before enabling the scheduled archive. Until this ADR is completed, `.env.example` contains placeholder URL templates and all code keeps source URLs configurable through secrets.

Expected local mapping support today:

- Product id fields: `idProduct`, `productId`, `cm_product_id`, `id`
- Expansion id fields: `idExpansion`, `expansionId`, `cm_expansion_id`
- Price fields: `low`, `price_low`, `lowPrice`, `avg`, `price_avg`, `avgPrice`, `average`, `avg1`, `avg7`, `avg30`
- Foil fields: `foilLow`, `foilAvg`, `priceFoil`

If the official schema differs, update `packages/ingest/ingest/normalize.py` and this ADR in the same commit.
