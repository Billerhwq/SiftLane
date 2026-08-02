# Operations Runbook

## Daily Checks

1. `GET /health/live` returns 200 and the expected version.
2. `GET /health/ready` returns 200, database `UP`, schema version 5 and an acceptable queue size.
3. Scrape `/metrics`; check queue growth, failed runs and dead-letter deliveries.
4. Confirm the latest daily backup verifies successfully.
5. Review admin audit and security alerts for denied access, rate limits and connector isolation failures.

## Key Commands

```bash
docker compose ps
docker compose logs --since 30m engine web
curl --fail http://127.0.0.1:8090/health/ready
curl --fail http://127.0.0.1:8090/metrics
docker stats --no-stream
```

## Queue Or Failure Growth

1. Pause new schedules that create the backlog.
2. Check worker count, host CPU/RAM/disk and database bytes.
3. Inspect recent failed run events; do not increase retries until the root cause is known.
4. Disable a failing connector or delivery target independently.
5. Drain and replay only bounded work. Re-qualify capacity before raising worker count above the tested profile.

## Secret Rotation

Keep the engine master key stable. Rotate a connector or target credential through the control plane by submitting the same scope and name; verify the record version increments. If the master key is compromised, stop the service, preserve evidence, export no plaintext, rotate every scoped credential, create a new data directory and re-enter credentials under a new master key.

## Known Limits

- Single node and SQLite only.
- No automatic cross-host failover.
- Connector processes are isolated by process/environment/limits, not a hardware VM boundary.
- Webhook receivers must enforce the idempotency key; Siftlane prevents duplicate sends for duplicate creation requests but cannot control a receiver that ignores the key.
- Schema downgrade in place is unsupported; restore the pre-upgrade backup with the matching engine version.
