# ADR 007: JSON-Only Portfolio Preview

Status: accepted

The MVP portfolio workflow validates CSV holdings and calculates benchmark comparisons without server-side persistence.

Accepted behavior:

- `POST /api/portfolios` returns an anonymous token and marks storage as `client-session`.
- `PUT /api/portfolios/[token]/holdings` validates CSV rows against the current static constituent universe and returns accepted rows plus line-level errors.
- `/portfolio` performs the holding-specific preview in the browser using the same parsing and comparison logic.
- `GET /api/portfolios/[token]/vs/[code]` returns a benchmark-only stateless series until persistent storage exists.

This avoids pretending that Vercel serverless functions can reliably store portfolio state without Supabase or another durable store. Persistent portfolios become part of the future database phase.
