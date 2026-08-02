# Upgrade And Rollback

## Upgrade

1. Read the target release notes and compatibility policy.
2. Run the complete candidate gate against the intended commit.
3. Verify a fresh backup and preserve the current engine secret key.
4. Stop writers and record current version, schema, counts and artifact SHA-256.
5. Start the new engine against a copy first. Require migration completion and `/health/ready`.
6. Validate login, a known flow/run, connector state, secret metadata and one NDJSON delivery.
7. Promote the migrated copy, start the Web asset with the matching version and monitor SLO alerts.

## Failed Migration

Startup must remain not-ready when migration cannot reach schema 5. Preserve the failed database copy and logs. Do not retry destructively. Restore the verified pre-upgrade backup and prior artifacts, then reproduce on another copy.

## Rollback

In-place schema downgrade is unsupported. Stop the new engine, preserve its database, restore the pre-upgrade backup with `siftlane-ops restore`, deploy the previous artifacts and validate readiness/counts. Connector rollback and delivery-target pause remain independent first responses and should be preferred when the engine itself is healthy.
