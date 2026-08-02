# Scheduled Work

## Inventory

| Job | Schedule | Function | Secrets | Limits and retry |
| --- | --- | --- | --- | --- |
| Schedule poller | `scheduler_poll_seconds`, default 1s | Claims due schedules and creates runs | API token not used internally | DB lease defaults to 30s; loop logs error and continues |
| Scheduled flow run | User cron plus IANA timezone | Executes immutable flow snapshot | Connector/HTTP secrets used only by nodes | Flow timeout, item bounds, node retry policy |
| Delivery poller | `delivery_poll_seconds`, default 1s | Claims due Webhook/NDJSON deliveries and records attempts | Decrypts only the target-scoped secret for the attempt | Target timeout, payload cap, bounded attempts and exponential backoff |

## Idempotency and Ownership

Due schedules are claimed with a database lease owner. Each scheduled run uses
`schedule:{schedule_id}:{scheduled_fire_time}` as its idempotency key, backed by a
unique database index. Manual triggers intentionally use a unique key.

Internal scheduler calls do not traverse HTTP and therefore do not use a user session.
The engine process owns automatic schedule authority and appends a `schedule.fire` audit
event. The schedule record captures owner, visibility and creator and exposes next/last
run, last run ID, and last error for operations review.

## Operating Rules

- Cron and timezone are validated before persistence.
- Paused schedules have no next fire time.
- Keep lease duration longer than normal claim/update latency.
- Investigate `last_error` and run events before manually retriggering a failed schedule.
- Competing scheduler processes rely on shared SQLite and are not a supported
  multi-node deployment architecture beyond the tested lease race.
- Delivery claims and retry state are durable. A dead-letter remains stopped until an authorized manual replay.
- Backups are deployment automation, not an in-process timer; schedule `siftlane-ops backup` in the host and verify every result.
