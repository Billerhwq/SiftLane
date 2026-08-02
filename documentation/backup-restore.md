# Backup And Restore

## Objectives

- Default RPO: 24 hours. Schedule at least one verified backup per day.
- RTO: 30 minutes for databases within the published single-node capacity boundary.
- A backup is accepted only with a matching `siftlane.backup/v1` manifest, SHA-256 and SQLite `integrity_check=ok`.

## Online Backup

The engine may remain running during backup because the command uses SQLite's online backup API:

```bash
siftlane-ops backup --data-dir /data --output /backups/siftlane-$(date -u +%Y%m%dT%H%M%SZ).sqlite3
siftlane-ops verify --backup /backups/siftlane-20260801T000000Z.sqlite3
```

Store the database and adjacent `.manifest.json` together in a separate failure domain. Back up `SIFTLANE_ENGINE_SECRET_KEY` through the deployment secret manager; it is not included in the database backup.

## Restore

1. Stop the engine and confirm no process writes `/data/crawler.db`.
2. Run `siftlane-ops verify --backup <backup>`.
3. Restore with `siftlane-ops restore --data-dir /data --backup <backup> --replace`.
4. Keep the generated `crawler.db.pre-restore-<UTC>` safety copy until verification completes.
5. Start the target engine version and require `/health/ready` to return 200.
6. Compare flow, run, item and event counts with the manifest.
7. Log in, inspect a known flow/run and exercise one non-destructive NDJSON delivery.

Restore rejects a bad hash, failed integrity check, missing manifest, unsupported old schema or schema newer than the running engine.

## Drill Evidence

`scripts/p5-qualification.ps1` backs up the capacity database, restores it into an empty directory, compares table counts and records elapsed time in `outputs/p5-backup-restore-report.json`.
