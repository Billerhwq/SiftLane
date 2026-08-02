# Architecture

## Product and Assumptions

Siftlane is a single-deployment crawler workflow system. A React control plane sends
versioned HTTP/SSE requests to an independent FastAPI engine. The engine validates
declarative DAGs, performs controlled HTTP collection, and persists operational
state in SQLite. It does not execute arbitrary user code.

The engine supports a compatibility `local` mode and a multi-user `team` mode.
Team mode uses local accounts, expiring opaque bearer sessions, three roles,
flow ownership and private/team visibility. It does not claim SaaS tenant isolation.

## Components

| Component | Technology | Responsibility |
| --- | --- | --- |
| Web control plane | React, TypeScript, Vite, React Flow, TanStack Query | Flow editing, run observation, results, team administration, integrations and schedules |
| Engine API | FastAPI, Pydantic | Versioned API, validation, auth gate, SSE |
| Worker and scheduler | asyncio, croniter | Durable execution, cancellation, recovery, scheduled runs |
| Storage | SQLite WAL | Users, sessions, audit, flows, snapshots, runs, events, items, checkpoints, schedules, connectors, encrypted secrets, delivery targets and delivery attempts |
| Connector SDK | Python entry points, Pydantic contracts and child workers | Isolated discovery and bounded managed execution |
| Delivery worker | asyncio, HTTPX, NDJSON | Authenticated Webhook or atomic NDJSON delivery, bounded retry, idempotency, dead letters and replay |
| Operations surface | FastAPI probes/metrics, JSON logs, `siftlane-ops` | Readiness, telemetry, verified online backup and atomic restore |

## Trust Boundaries

- Browser to engine: CORS plus bearer session; server-side role, owner and visibility
  checks run on every protected resource path.
- Engine to target websites: `SecureHttpClient` enforces scheme, DNS/IP policy,
  robots.txt, rate delay, redirects, timeout, and response-size limits.
- Engine to SQLite: the engine process has full database authority; clients never
  receive direct database access.
- Engine to connectors: external entry points are imported and validated in bounded
  child processes with a reduced environment. This is fault isolation, not a kernel sandbox.
- Engine to delivery targets: payload size, timeout, authentication/signature, idempotency
  and retry are enforced before an attempt becomes succeeded or dead-lettered.
- Engine to secret store: Fernet ciphertext is persisted in SQLite. Plaintext is decrypted
  only for a scoped operation and is passed to connector workers through stdin.

## Known Risks and Assumptions

- `local` mode with an empty API token is allowed only on a loopback bind.
- Team accounts share one deployment; tenant isolation and enterprise identity are not claimed.
- Connector child processes still run under the engine OS account and require reviewed packages.
- SQLite is the durability boundary and is appropriate for the current single-node
  deployment assumption; multi-node operation is not claimed.
- Webhook receivers must honor the supplied idempotency key to obtain end-to-end exactly-once
  business behavior; Siftlane guarantees bounded, recorded delivery attempts.
- Browser automation, email, SEO routes, embedded agents, multi-node execution and SaaS
  tenant isolation are not present.
- Release artifacts include application packages, not hosted deployment, managed backup
  storage or automatic cross-host failover.

## Related Documents

- [Product lifecycle PRD](../PRD-SiftLane-product-lifecycle.md)
- [Phase acceptance](../ACCEPTANCE.md)
- [Operational flows](flows.md)
- [Permissions](permissions.md)
- [Variables and secrets](variables.md)
- [P3 threat model](threat-model.md)
- [Connectors](connectors.md)
- [Delivery](delivery.md)
- [Database migrations](migrations.md)
- [Test coverage](tests.md)
- [Scheduled work](cron.md)
- [Background automation](automation.md)
- [Deployment](deployment.md)
- [Operations](operations.md)
- [Backup and restore](backup-restore.md)
- [Incident response](incident-response.md)
- [Upgrade and rollback](upgrade.md)
- [Compatibility](compatibility.md)
- [Service levels and alerts](slo.md)
- [Release and rollback](release.md)
- [P2 release PRD](../PRD-P2-release-hardening.md)
