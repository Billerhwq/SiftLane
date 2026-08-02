# Database Migration And Rollback

## Version Boundary

The GA engine reports schema version `5` in `schema_meta` and accepts restore sources from schema `2` through `5`. Startup migrations are additive: existing P2 flow/run/schedule fields remain readable while later tables and ownership metadata are created.

| Schema | Product phase | Additive data |
| --- | --- | --- |
| 2 | P2 | Flow snapshots, checkpoints, retries and schedules |
| 3 | P3 | Users, sessions, audit, owner/visibility/creator metadata |
| 4 | P4 | Managed connectors, scoped encrypted secrets, delivery targets and deliveries |
| 5 | P5 | `schema_meta` compatibility/readiness contract and operational backup boundary |

On first authenticated start, legacy resources are assigned to the non-login `local-operator` identity and remain team-visible. Team mode creates the first administrator only when no team account exists and a valid bootstrap password is present. The P4 integration initializer creates its tables and the built-in JSON Feed connector idempotently.

## Required Upgrade Procedure

1. Stop external writers and create/verify a complete online backup with its manifest.
2. Preserve the current artifacts, database and `SIFTLANE_ENGINE_SECRET_KEY`.
3. Start the target engine against a copy; require `/health/ready` and `/api/v1/operations/schema` to report current/latest `5`.
4. Compare flow, run, item and event counts with the backup manifest.
5. In team mode, log in and inspect migrated ownership, connector state and secret metadata.
6. Run the complete authenticated browser suite and one non-destructive NDJSON delivery before promoting the copy.

## Failure And Rollback

Startup must not be considered ready if migration does not reach schema 5. Preserve the failed copy and logs; do not repeatedly modify it. In-place downgrade is unsupported. Stop the new engine, restore the verified pre-upgrade database atomically with `siftlane-ops restore`, deploy the matching prior artifacts and restore the prior network/authentication boundary.

Do not point P2/P3 at a live database after later team, connector or delivery writes and call that a rollback. A connector-only fault should first use disable or connector rollback; a target-only fault should pause/cancel delivery work. Preserve the later database for investigation and forward repair.

## Verification Evidence

- `engine/tests/test_p3_security.py` covers ownership/session migration behavior.
- `engine/tests/test_p4_integrations.py` creates and reopens the integration schema.
- `engine/tests/test_p5_operations.py` checks schema reporting and backup/restore integrity.
- `engine/tests/fixtures/v0.2-flow.json` pins the oldest supported flow contract.
- `engine/scripts/backup_drill.py` records count, checksum, integrity and RTO evidence.
