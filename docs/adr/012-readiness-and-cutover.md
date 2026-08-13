# ADR 012: Aggregate Readiness and Review-Only Cutover

Status: accepted

## Decision

Every successful new shadow calculation produces a small repository-managed readiness receipt. The receipt contains the calculation date, methodology version, archive-day counts, target counts, language-policy status, and named gates for each index. It contains no product prices, price history, contribution rows, or private R2 object details.

The static site exports the receipt to `data/readiness/latest.json`. Accumulating index pages and the data-quality page may display this aggregate progress. Public index completeness remains zero until a reviewed publication occurs.

## Language universe

The official Cardmarket downloads do not expose a reliable language field. Every launch index therefore covers all languages represented in the Cardmarket Europe catalogue. Product names are not parsed to infer language, and no EN/DE-only claim is made.

## Cutover control

`scripts/prepare_cutover.py` reads a successful archive audit and private shadow outputs. It verifies archive, lookback, target-size, language, methodology, and checksum gates. A blocked run writes only a review report. An eligible run writes a checksummed candidate into an isolated operator-selected directory.

The tool has no publish mode. It refuses to write into the repository's public source or generated-data directories, records `publicationPerformed: false`, and always requires human sign-off. This preserves the distinction between deterministic preparation and the editorial/legal decision to publish.
