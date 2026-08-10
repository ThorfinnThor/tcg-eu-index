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
- keyword and page-definition identities are unique,
- indexable pages reference distinct approved keywords,
- canonical URLs match registered slugs,
- page locale, intent, and cluster match the keyword registry,
- explicit internal-link relationships resolve,
- indexable pages pass result, insight, and completeness thresholds.

The page-definition registry is the only source for sitemap inclusion and indexability. Utility pages, filtered constituent views, embeds, draft reports, and the report archive before its first human-reviewed publication use `noindex`. The validator writes an ignored build artifact to:

```text
apps/web/generated/reports/static-build.json
```

The report records public JSON size, the largest file, page counts, indexable/noindex counts, duplicate candidates, and failed quality checks. A critical validation failure stops the build before Next.js or Vercel deployment.
Successful CI and static-data-check runs retain this report as a GitHub Actions artifact for 30 days.

This keeps the MVP deployable on Vercel with zero public database reads. Collection of immutable Cardmarket source snapshots is active as an independent background workflow; transforming those snapshots into production index values, newsletter delivery, and fully automated weekly report generation remain later phases.
