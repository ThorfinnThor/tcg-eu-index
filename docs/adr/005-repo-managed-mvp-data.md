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

Later, Cardmarket import automation can replace the repo-managed MVP JSON files while keeping the same public JSON contract.
