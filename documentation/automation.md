# Background Automation

## Inventory

| Automation | Trigger | Side effect | Idempotency and stop control |
| --- | --- | --- | --- |
| Worker pool | Queued run | Executes an immutable flow snapshot and writes events/items/checkpoints | Run state and `(run_id, external_id)` uniqueness; cancel endpoint |
| Startup recovery | Engine start | Requeues or resumes interrupted runs | Checkpoint checksum and terminal-state checks |
| Schedule poller | Database due time | Creates a scheduled run | `schedule:{id}:{fire_time}` unique key; pause schedule |
| Delivery poller | Due delivery attempt | Writes NDJSON or calls Webhook | Idempotency key, claim state, bounded retry; cancel target delivery |
| Session cleanup | Authentication access | Rejects expired/revoked session | Token hash and expiry; logout/deactivate/password reset |
| Backup schedule | Operator-defined external timer | Creates database backup and manifest | Refuses overwrite; operator removes/archives old backups |

The engine performs no hidden email, browser, marketing, billing or cross-deployment automation. All product background loops start and stop with the engine process, expose durable state through APIs or SQLite, and emit structured errors. Host backup retention is deliberately outside the engine because the operator owns its failure domain and policy.

## Failure Rules

- Never retry without a fixed limit or a durable next-attempt timestamp.
- Never pass a plaintext scoped secret through command arguments, persisted audit detail or result payloads.
- Never broaden actor authority when work crosses into an internal worker; stored owner and visibility remain authoritative.
- Pause the narrowest failing schedule, connector or delivery target before stopping the entire engine.
