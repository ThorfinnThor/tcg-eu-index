# ADR 005: Repo-Managed MVP Data

Status: accepted

For the MVP, the GitHub repository is the data source.

The editable source file is:

```text
apps/web/source-data/indexes.json
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

Those generated files are deployment artifacts and are ignored by Git. The source data file is versioned in Git.

Later, Cardmarket import automation can replace the seeded history generation while keeping the same public JSON contract.
