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

- Supabase master/admin database,
- portfolio persistence.

Activated data-collection extension:

- private Cloudflare R2 raw archive,
- daily Cardmarket archive workflow,
- deterministic private catalogue and price normalization,
- weekly archive integrity audit.
- aggregate public archive-health and readiness receipts,
- Discord workflow digests and a manual delivery test,
- weekly report drafts with human-reviewed pull-request publication,
- optional newsletter delivery through a configured HTTPS provider,
- browser-local portfolio CSV storage after index publication.

Reasoning:

- The website can be validated with static JSON first.
- Vercel does not need Supabase or Cloudflare for public page rendering.
- R2 preserves replaceable daily source files but is not read by public pages or Vercel builds.

The archive schedules remain guarded by `ARCHIVE_ENABLED` until the one-time setup and manual first-snapshot checks in the archiver runbook are complete.
