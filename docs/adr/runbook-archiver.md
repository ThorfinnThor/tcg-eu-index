# Archiver Runbook

## Daily Operation

`archive.yml` runs four staggered UTC attempts. The first successful run writes raw gzipped snapshots and then writes `manifests/YYYY-MM-DD.json` last as the completion marker. A successful run also commits `data/manifest-latest.json` as the keep-alive heartbeat.

## Missed Day

Cardmarket daily downloads are point-in-time. A missed day is treated as a permanent incident:

1. Record the date, game, and reason in `archive_gaps`.
2. Do not fabricate a snapshot.
3. Re-run `scripts/verify_archive.py --since <inception>`.
4. The engine skips documented gap dates.

## Backup Trigger

Create a cron-job.org job for 16:00 UTC daily that calls GitHub's `workflow_dispatch` endpoint for `.github/workflows/archive.yml` with a fine-grained PAT limited to Actions write access on this repository.

## Forced Alert Test

Run `archive.yml` manually with a known-bad URL template in a temporary branch or test environment. The workflow must post a CRITICAL message to `ALERT_DISCORD_WEBHOOK`.
