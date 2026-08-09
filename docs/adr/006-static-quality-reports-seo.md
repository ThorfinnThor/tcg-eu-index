# ADR 006: Static Quality, Reports, and SEO Surfaces

Status: accepted

For the JSON-only MVP, the public quality page and report archive are generated from repo-managed source JSON.

Editable source files:

```text
apps/web/source-data/data-quality.json
apps/web/source-data/reports/index.json
apps/web/data-config/seo/keywords.json
apps/web/data-config/seo/page-definitions.json
```

Generated public files:

```text
apps/web/public/data/data-quality/latest.json
apps/web/public/data/reports/index.json
```

The static-data validation step verifies:

- source JSON shape,
- generated manifest checksums,
- data-quality and reports public contracts,
- published SEO pages reference approved keywords.

This keeps the MVP deployable on Vercel with zero public database reads. Cardmarket ingestion, newsletter delivery, and fully automated weekly report generation remain later phases.
