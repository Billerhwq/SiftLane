# Scheduled Work

## Inventory

| Job | Schedule | Function | Secrets | Limits and retry |
| --- | --- | --- | --- | --- |
| Schedule poller | `scheduler_poll_seconds`, default 1s | Claims due schedules and creates runs | API token not used internally | DB lease defaults to 30s; loop logs error and continues |
| Scheduled flow run | User cron plus IANA timezone | Executes immutable flow snapshot | Connector/HTTP secrets used only by nodes | Flow timeout, item bounds, node retry policy |

## Idempotency and Ownership

Due schedules are claimed with a database lease owner. Each scheduled run uses
`schedule:{schedule_id}:{scheduled_fire_time}` as its idempotency key, backed by a
unique database index. Manual triggers intentionally use a unique key.

Internal scheduler calls do not traverse HTTP and therefore do not use the API token.
The engine process owns schedule authority. The schedule record exposes next/last run,
last run ID, and last error for operations review.

## Operating Rules

- Cron and timezone are validated before persistence.
- Paused schedules have no next fire time.
- Keep lease duration longer than normal claim/update latency.
- Investigate `last_error` and run events before manually retriggering a failed schedule.
- Competing scheduler processes rely on shared SQLite and are not a supported
  multi-node deployment architecture beyond the tested lease race.
