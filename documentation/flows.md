# Operational Flows

## Author and Run a Flow

- Actor: operator with network access and, when configured, the API bearer token.
- Preconditions: engine is healthy; the target is allowed by controlled HTTP policy.
- Outcome: an immutable flow snapshot is queued, executed, observed, and persisted.

1. The browser reads capabilities and flows through protected API routes.
2. The engine validates node schemas, graph connectivity, branch ports, and acyclicity.
3. Saving writes a revisioned flow; an expected revision prevents silent overwrite.
4. Starting a run validates parameters and stores an immutable flow snapshot.
5. A worker claims the run, performs controlled outbound HTTP, writes checkpoints,
   events, and idempotent result rows, then commits a terminal state.
6. The browser consumes resumable SSE and reads persisted results/history.

Authorization deny case: when an API token is configured, a missing or different
bearer token receives `401`. There is no finer-grained flow ownership check.

Trust crossings and side effects: browser to engine; engine to target websites;
engine to SQLite. Writes include flow revisions, runs, events, checkpoints, and items.

## Recover or Cancel a Run

- Actor: authenticated operator, or engine startup recovery.
- Preconditions: a queued/running/cancelling run exists.
- Outcome: the run reaches a durable terminal state without duplicate result rows.

Cancellation sets an in-memory event and persists cancellation state/events. Startup
recovery requeues interrupted runs, restores valid completed-node checkpoints, and
executes only the interrupted node and downstream work. Result identity is scoped by
`(run_id, external_id)`.

## Manage a Schedule

- Actor: authenticated operator; automatic trigger is owned by the engine scheduler.
- Preconditions: referenced flow exists; cron and IANA timezone are valid.
- Outcome: a schedule is created/updated/paused/deleted or produces one idempotent run.

The API validates and persists the schedule. Scheduler instances compete for a
database lease. A scheduled fire uses `schedule:{id}:{fire_time}` as the run
idempotency key. Manual triggers use a unique key and record the resulting run.

## Inspect Connectors

- Actor: authenticated operator.
- Preconditions: connector packages, if any, are installed at engine startup.
- Outcome: the browser receives validated manifests and the SDK v1 schema contract.

Connector execution is a trusted extension boundary. The current UI only discovers
connectors; it does not expose an arbitrary connector execution endpoint.
