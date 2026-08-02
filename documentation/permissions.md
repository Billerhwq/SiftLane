# Permissions

## Identity Modes

| Mode | Identity source | Intended use |
| --- | --- | --- |
| `local` | Built-in `local-operator`; optional deployment bearer token | Loopback development or a trusted single-operator network |
| `team` | Local user record plus expiring opaque bearer session | Multiple known users inside one deployment |

Team session tokens are random values. Only their SHA-256 hashes are stored. Passwords use PBKDF2-HMAC-SHA256 with a per-user salt. Tokens are sent in the `Authorization` header and are never cookies, so browser CSRF credentials are not used.

Non-loopback `local` mode is rejected at startup unless a non-empty deployment API token is configured. `team` mode requires an initial administrator password only when no team user exists.

## Roles

| Role | Authority |
| --- | --- |
| `admin` | Manage users; read and operate every resource; read audit and security operations |
| `editor` | Create flows; manage owned flows; read/run team flows; manage schedules they own or created |
| `viewer` | Read team-visible flows, runs, events, results and schedules; no mutations or execution |

## Resource Matrix

| Resource and operation | Admin | Editor | Viewer |
| --- | --- | --- | --- |
| Users: list/create/update | Allow | Deny | Deny |
| Audit/security operations: read | Allow | Deny | Deny |
| Flow: create | Allow | Allow | Deny |
| Private flow: read | Allow | Owner only | Owner only |
| Team flow: read | Allow | Allow | Allow |
| Flow: update/delete | Allow | Owner only | Deny |
| Team flow: run/cancel | Allow | Allow | Deny |
| Private flow: run/cancel | Allow | Owner only | Deny |
| Run snapshot/events/SSE/items | Same read rule as the run's captured owner/visibility | Same | Same |
| Schedule: create/trigger | Allow | Allowed flow only | Deny |
| Schedule: update/delete | Allow | Flow owner or schedule creator | Deny |
| Connector manifests/contracts | Allow | Allow | Allow |
| Connector manifests and managed connector list | Allow | Allow | Allow |
| Connector install/upgrade/enable/disable/rollback/uninstall | Allow | Deny | Deny |
| Managed connector execute | Allow | Allow | Deny |
| Secret metadata/create/delete | Allow | Deny | Deny |
| Team delivery target: read | Allow | Allow | Allow |
| Private delivery target: read | Allow | Owner only | Owner only |
| Delivery target: create | Allow | Allow | Deny |
| Delivery target: update/delete | Allow | Owner only | Deny |
| Delivery: create | Allow | Allowed run and readable target | Deny |
| Delivery history | Allow | Readable run and target only | Readable run and target only |
| Delivery: replay/cancel | Allow | Target owner only | Deny |
| Schema operations: read | Allow | Deny | Deny |
| SQLite direct access | Deployment boundary only | Deny | Deny |

All protected paths enforce authorization in `engine/src/siftlane_engine/api.py`. Lists are filtered before serialization. Direct-ID, event, SSE, item and cancel paths repeat the resource check instead of relying on a prior list response. Inaccessible existing resources return `404` to reduce enumeration; role-wide forbidden operations return `403`.

There is no database row-level security. SQLite is only reachable by the engine process, so the API resource checks are the enforcement boundary. Resource ownership and visibility are copied into run and schedule records so later flow edits cannot broaden historical access silently.

## Session and Administration Rules

- Login and refresh create new tokens and revoke the replaced session; supplied tokens are never reused, preventing session fixation.
- Logout, password reset and user deactivation revoke active sessions.
- Expired and revoked sessions are rejected with `401`.
- Role changes take effect on the next request. Ownership never restores mutation or execution authority to a viewer.
- Failed login attempts are rate-limited per remote address and normalized username.
- The final active administrator cannot be demoted or disabled.
- Ordinary users cannot mutate or delete audit records through any API.

## Deny Tests

`engine/tests/test_p3_security.py` checks private-flow enumeration, team-flow mutation, role demotion of existing owners, run creation/cancel, events/items, schedule triggering, audit access, session revocation, last-admin protection, CORS rejection and login throttling. `engine/tests/test_p4_integrations.py` checks P4 lifecycle, secret redaction including connector-result echo rejection, target ownership, delivery and replay rules. `apps/web/tests/p3.spec.ts` and `p4.spec.ts` exercise the same boundaries through the browser.
