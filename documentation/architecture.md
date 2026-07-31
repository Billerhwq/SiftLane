# Architecture

## Product and Assumptions

Siftlane is a single-operator crawler workflow system. A React control plane sends
versioned HTTP/SSE requests to an independent FastAPI engine. The engine validates
declarative DAGs, performs controlled HTTP collection, and persists operational
state in SQLite. It does not execute arbitrary user code.

The current authorization model assumes one trusted deployment boundary. An
optional bearer token protects every `/api/v1/*` route, but there are no users,
roles, tenants, or per-flow ownership rules.

## Components

| Component | Technology | Responsibility |
| --- | --- | --- |
| Web control plane | React, TypeScript, Vite, React Flow, TanStack Query | Flow editing, run observation, results, connectors, schedules |
| Engine API | FastAPI, Pydantic | Versioned API, validation, auth gate, SSE |
| Worker and scheduler | asyncio, croniter | Durable execution, cancellation, recovery, scheduled runs |
| Storage | SQLite WAL | Flows, snapshots, runs, events, items, checkpoints, schedules |
| Connector SDK | Python entry points and Pydantic contracts | Trusted extension discovery and controlled runtime context |

## Trust Boundaries

- Browser to engine: CORS plus optional bearer token; all API clients receive the
  same authority once authenticated.
- Engine to target websites: `SecureHttpClient` enforces scheme, DNS/IP policy,
  robots.txt, rate delay, redirects, timeout, and response-size limits.
- Engine to SQLite: the engine process has full database authority; clients never
  receive direct database access.
- Engine to connectors: connector packages are trusted executable Python. Their
  declared contract is validated, but process isolation is not implemented.

## Known Risks and Assumptions

- An empty API token disables authentication and is suitable only for local use.
- There is no tenant isolation or role model; a valid token can operate every flow,
  run, result, connector contract, and schedule.
- Third-party connectors execute in the engine process and require deployment-level
  trust until worker/container isolation is added.
- SQLite is the durability boundary and is appropriate for the current single-node
  deployment assumption; multi-node operation is not claimed.
- Browser automation, authenticated platform adapters, email, SEO routes, embedded
  agents, and external webhooks are not present. No `emails.md`, `seo.md`, or
  `automation.md` is required.

## Related Documents

- [Phase acceptance](../ACCEPTANCE.md)
- [Operational flows](flows.md)
- [Permissions](permissions.md)
- [Variables and secrets](variables.md)
- [Test coverage](tests.md)
- [Scheduled work](cron.md)
- [Release and rollback](release.md)
- [P2 release PRD](../PRD-P2-release-hardening.md)
