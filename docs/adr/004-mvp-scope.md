# ADR 004: MVP Scope Reduction

Status: accepted

The first public version is a simple GitHub + Vercel static site.

MVP runtime:

```text
GitHub repository
  -> Vercel build
  -> static JSON export
  -> Next.js pages
  -> Vercel CDN
```

Deferred until product validation:

- Cloudflare R2 raw archive,
- Supabase master/admin database,
- daily Cardmarket archive workflow,
- Discord alerts,
- weekly report automation,
- portfolio persistence.

Reasoning:

- The website can be validated with static JSON first.
- Vercel does not need Supabase or Cloudflare for public page rendering.
- Raw archive durability matters later, once real daily source URLs and the product direction are confirmed.

Re-enable the parked workflows after the Cardmarket official download links and storage decision are finalized.
