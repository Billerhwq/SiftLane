# Incident Response

## Severity

| Severity | Example | Initial action |
| --- | --- | --- |
| SEV-1 | Credential exposure, unauthorized private data access, unrecoverable corruption | Isolate network access, stop writers, preserve logs/data |
| SEV-2 | Readiness down, sustained queue, widespread run or delivery failure | Pause schedules/targets, capture metrics and logs |
| SEV-3 | One flow, connector or target fails within isolation boundary | Disable affected resource and investigate |

## First 15 Minutes

1. Record UTC start time, reporter, affected version and visible impact.
2. Check `/health/live`, `/health/ready` and `/metrics`.
3. Preserve `docker compose ps`, recent JSON logs and audit events.
4. Stop the smallest unsafe side effect: schedule, connector, delivery target, then engine writers if required.
5. Create an online backup when the database is readable; never overwrite the last known-good backup.

## Decision Paths

- **Credential exposure:** revoke external credentials, disable related targets/connectors, rotate scoped secrets, then assess master-key replacement.
- **Database corruption:** stop the engine, verify backups, restore into a new directory, validate counts and integrity before promotion.
- **Bad connector upgrade:** disable and roll back the connector without rolling back the engine.
- **Bad engine upgrade:** stop writers, restore the pre-upgrade database and matching prior artifacts. Do not point an older engine at post-migration data.
- **Delivery backlog:** pause the target, repair it, then replay selected dead letters. Do not enable unbounded retries.

## Closeout

Document root cause, affected resources/users, data impact, detection gap, timeline, recovery evidence and a regression test. Preserve audit events; corrections are appended rather than editing history.
