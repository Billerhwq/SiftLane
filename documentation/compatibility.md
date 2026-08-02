# v1 Compatibility Policy

## Stable Surfaces

| Surface | v1 promise | Breaking change rule |
| --- | --- | --- |
| HTTP API | `/api/v1` request/response fields remain backward compatible | New `/api/v2` or next major release |
| Flow definition | Existing valid P2+ JSON remains accepted; new fields have defaults | Migration tool and major release |
| Connector SDK | `siftlane.connector/v1`, SDK `1.x` | Incompatible manifest rejected before activation |
| Database | Schema 2 through 5 may upgrade forward to schema 5 | Backup required; no in-place downgrade |
| Backup | `siftlane.backup/v1` manifest and SHA-256 | New format identifier with explicit converter |

Additive response fields, optional request fields, new node types and new metrics are compatible changes. Renaming/removing fields, changing authorization, changing idempotency meaning or narrowing accepted data is breaking.

Deprecations must be documented in release notes for at least one minor release before removal and must emit a machine-visible warning where practical. Security fixes may shorten this window, but require explicit migration and rollback instructions.

Compatibility fixtures live in `engine/tests/fixtures`; `v0.2-flow.json` pins the pre-GA flow contract. Database startup records the current schema in `schema_meta`, and the admin schema endpoint exposes current/latest/minimum versions.
