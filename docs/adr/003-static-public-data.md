# ADR 003: Static Public Data Runtime

Status: accepted

The public website must not query Supabase at runtime for public pages, rankings, comparisons, methodology pages, index detail pages or constituent tables.

Supabase remains allowed for:

- pipeline/admin persistence,
- append-only derived tables,
- future user accounts,
- token-scoped portfolio APIs,
- internal operational checks.

Public runtime data flow:

```text
Cardmarket official downloads
  -> GitHub Actions
  -> validation, normalization, scoring
  -> Supabase master/admin tables and R2 archive
  -> small versioned JSON files
  -> Next.js static generation
  -> Vercel CDN
```

The web app reads from `apps/web/public/data` during build and route-handler execution. The build runs `data:export` and `data:validate` before `next build`.

Generated data rules:

- no direct browser Supabase access for public pages,
- no monolithic JSON files,
- every deployment has `public/data/manifest.json`,
- static HTML includes primary page content,
- finder/search data uses lightweight index records only,
- large generated datasets are deployment artifacts and should not be manually edited.
