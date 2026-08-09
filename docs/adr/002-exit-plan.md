# ADR 002: Free-Tier Exit Plan

Raw snapshots are the durable asset and live in Cloudflare R2 under immutable keys. Supabase stores only catalogue metadata, derived index tables, analytics, and portfolio aggregates.

If a free tier changes or fills:

1. Keep R2 as source of truth and copy the bucket with an S3-compatible sync tool.
2. Recreate Postgres from `supabase/migrations`.
3. Recompute derived rows from R2 snapshots and the tagged repository version.
4. Point Vercel env vars at the new read surface.

No public API is allowed to expose raw per-card daily price feeds; only aggregate index values, analytics, constituents, and user portfolio benchmark results are public.
