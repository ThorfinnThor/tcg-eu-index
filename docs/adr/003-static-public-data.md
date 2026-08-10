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
repository-managed source JSON
  -> validation and deterministic export
  -> small versioned public JSON files
  -> Next.js static generation
  -> Vercel CDN
```

The future Cardmarket production pipeline may use R2 for immutable raw snapshots and Supabase for admin or derived persistence, but neither service is an MVP runtime or build dependency. Any production pipeline must preserve the same public JSON contract.

The web app reads from `apps/web/public/data` during build and route-handler execution. The build runs `data:export` and `data:validate` before `next build`.

Generated data rules:

- no direct browser Supabase access for public pages,
- no monolithic JSON files,
- every deployment has `public/data/manifest.json`,
- static HTML includes primary page content,
- finder/search data uses lightweight index records only,
- large generated datasets are deployment artifacts and should not be manually edited.
