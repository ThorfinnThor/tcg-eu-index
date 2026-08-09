# TCG Europe Index

Public, repository-managed listing-price benchmarks for the European One Piece and Pokemon card markets.

## Local development

Requirements: Python 3.12 with `uv`, and Node.js 20 or newer.

```bash
uv sync --all-packages
npm ci --prefix apps/web
npm run dev
```

The web app is available at <http://localhost:3000>. Static public JSON is generated from `apps/web/source-data` before development and production builds.

## Checks

```bash
uv run ruff check .
uv run mypy
uv run pytest
npm --prefix apps/web run data:export
npm --prefix apps/web run data:validate
npm --prefix apps/web run lint
npm --prefix apps/web run test
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e
```

Verify the current official Cardmarket downloads without writing data:

```bash
uv run --package tcg-eu-index-ingest python -m ingest.source_check
```

The public source paths and confirmed JSON schema are recorded in `docs/adr/001-source-schema.md`. The scheduled workflow retains each source-check result as a GitHub artifact for 14 days. Production index values remain repository-managed until enough daily official snapshots exist for the methodology's observation windows.
