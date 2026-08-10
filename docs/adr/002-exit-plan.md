# ADR 002: Free-Tier Exit Plan

Raw snapshots are the durable asset and live in Cloudflare R2 under immutable keys. The current system does not require Supabase. A database may later store catalogue metadata, derived index tables, analytics, or portfolio aggregates if repository-managed JSON no longer meets product needs.

If a free tier changes or fills:

1. Keep R2 as source of truth and copy the bucket with an S3-compatible sync tool.
2. Recompute generated datasets from copied snapshots and a tagged repository version.
3. If a database has been introduced by then, recreate it from versioned migrations and recompute derived rows.
4. Keep the same public JSON paths so the Vercel application does not depend on the storage vendor.

No public API is allowed to expose raw per-card daily price feeds; only aggregate index values, analytics, constituents, and user portfolio benchmark results are public.
