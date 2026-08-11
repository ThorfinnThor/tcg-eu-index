# ADR 005: Repo-Managed MVP Data

Status: accepted

For the MVP, the GitHub repository is the data source.

The editable source files are:

```text
apps/web/source-data/indexes.json
apps/web/source-data/indexes/<index-code>/history.json
apps/web/source-data/indexes/<index-code>/constituents.json
```

The Vercel build runs:

```text
npm run data:export
npm run data:validate
npm run build
```

This produces generated static files in:

```text
apps/web/public/data/
```

Those generated files are deployment artifacts and are ignored by Git. The source data files are versioned in Git.

Cardmarket collection and private normalization are now active. Repository fixtures remain available for deterministic development and calculation tests, but accumulating indexes export empty history, constituent, rebalance, and report collections. The later cutover fills the same public JSON paths and schemas only after the real observation windows, index calculations, and human review pass their quality gates.
