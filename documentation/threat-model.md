# P3 Threat Model

## Protected Assets

- User passwords and session tokens.
- Private flow definitions, run snapshots, events and result data.
- Schedule authority and connector/package execution authority.
- Audit records and the SQLite durability boundary.

## Actors and Boundaries

| Actor | Trusted authority | Must not gain |
| --- | --- | --- |
| Anonymous network client | Public health and API documentation only | Protected APIs, user existence or private resources |
| Viewer | Team-visible read access | Mutations, execution, audit or private resources |
| Editor | Owned resources and team execution | Other owners' mutations, user administration or global audit |
| Admin | All resources in one deployment | Host authority outside documented deployment controls |
| Connector package | Its bounded child process and validated request | Parent database, inherited Siftlane secrets or engine-process control |

## Threats and Controls

| Threat | Control | Verification |
| --- | --- | --- |
| Password theft from database | Salted PBKDF2-HMAC-SHA256 hashes | Password/session tests and storage inspection |
| Session fixation or continued access after reset | New random token per login/refresh; revoke replaced, logged-out, reset or deactivated sessions | `test_team_auth_sessions_users_and_last_admin_guard` |
| Brute-force login | Per-address/username window and `429 Retry-After` | `test_login_rate_limit_and_non_loopback_auth_guard` |
| Direct-ID or SSE authorization bypass | Server-side scope check on every resource path | P3 authorization matrix test |
| CSRF | No cookie credentials; bearer header; explicit CORS allowlist | Rejected-origin integration assertion |
| Audit erasure by an ordinary user | Append/list storage API only; list is admin-only | P3 role and audit tests |
| Connector crash or oversized output | Separate process, timeout, output cap and contract validation | Connector isolation test |
| Secret inheritance by connector | Child-process environment allowlist excludes Siftlane secrets | Connector environment test |
| Locking out every administrator | Reject demotion/deactivation of final active admin | Last-admin test |

## Accepted Limits

- Local storage bearer tokens remain exposed to successful same-origin script injection. TLS, restrictive script serving and dependency review are deployment requirements.
- Process isolation contains failure but is not a Windows/Linux kernel sandbox. Only reviewed packages may be installed until a container policy is added.
- SQLite files remain fully trusted by the engine OS account. Host compromise is outside application authorization.
- This is a single-deployment user model, not tenant isolation.

## Stop Conditions

Authentication bypass, cross-user private data access, missing audit for protected mutations, last-admin removal, raw secret leakage or connector failure terminating the engine blocks a P3 candidate.
