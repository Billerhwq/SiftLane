# Operational Flows

## Authenticate and Manage a Session

- Actor: team user; administrator for account management.
- Preconditions: team mode is configured and the account is active.
- Outcome: an expiring bearer session is issued, used, and revocable.

1. The browser requests `/api/v1/auth/me` with its stored bearer token.
2. The engine hashes the token and joins the active, unexpired session to an active user.
3. On `401`, the browser shows login. Login throttling is keyed by remote address and normalized username.
4. A successful password check issues a new random token; only its hash is persisted.
5. The browser periodically refreshes team sessions. Refresh revokes the old token and rotates to a new one.
6. Logout revokes that session. Password reset or deactivation revokes every session for the user.

Trust crossing: browser to engine. Passwords and raw tokens must never enter audit detail, logs, items or connector payloads.

## Author and Run a Flow

- Actor: admin or editor; viewer for team-visible read-only inspection.
- Preconditions: the actor has access to the flow and the target passes controlled HTTP policy.
- Outcome: an immutable, owner-scoped flow snapshot is queued, executed, observed and persisted.

1. The browser reads only flows allowed by owner and visibility.
2. Create assigns the authenticated actor as owner. Update/delete requires owner or admin.
3. The engine validates schemas, connectivity, branch ports and acyclicity.
4. Starting a run requires admin, owner, or editor access to a team flow.
5. The run stores owner, visibility, creator and an immutable flow snapshot.
6. Workers perform controlled HTTP and persist checkpoints, events and idempotent results.
7. Every run, snapshot, SSE, event and item read repeats the captured scope check.

Deny case: a private resource owned by another user returns `404`; a viewer cannot create, mutate, run or cancel.

Trust crossings and side effects: browser to engine; engine to target; engine to SQLite. Mutations append audit events with actor, action, resource, outcome and safe detail.

## Collect Listing And Article Detail

- Actor: a flow author or an automatic run worker.
- Preconditions: listing and article URLs pass the controlled HTTP and robots policy.
- Outcome: each emitted row contains article-page content and provenance rather than a listing summary.

1. `start` supplies one or more listing or section URLs.
2. `http_request` fetches each listing with bounded retries. `continue_on_error` isolates a failed section, while `fallback_to_http` is an explicit compatibility option for sites whose HTTPS endpoint is intermittently unavailable.
3. `html_extract` or `json_extract` emits the listing title, canonical article URL and `listing_url`. `deduplicate_by: url` prevents overlapping sections from spending the detail-request budget twice.
4. A second `http_request` fetches each article. `timeout_seconds` bounds one attempt, retry policy applies per article when `continue_on_error` is enabled, and `force_http` is reserved for a site verified to publish the same public article over HTTP.
5. `html_extract` reads the article title, body, author and publication time. A field may read JSON-LD with `attribute: json` plus `path`, or parse HTML stored in a named JavaScript string with `script_variable`.
6. `emit` maps the article URL, full content and nested provenance metadata. Detail flows set `skip_empty_content: true`, so missing extraction is visible as `item.skipped` and never becomes serialized internal state disguised as article content.

The local news-flow updater is `scripts/update-local-news-flows.ps1`. It updates the five saved news flows in place and preserves optimistic revisions.

## Recover or Cancel a Run

- Actor: an authorized admin/editor, or engine startup recovery.
- Preconditions: a queued/running/cancelling run exists.
- Outcome: the run reaches a durable terminal state without duplicate result rows.

Cancellation checks run scope before setting its cancellation state. Startup recovery uses the stored snapshot and owner scope, restores valid checkpoints and only executes interrupted/downstream nodes. Result identity remains `(run_id, external_id)`.

## Manage a Schedule

- Actor: admin or editor with run access; the scheduler owns automatic triggers.
- Preconditions: the referenced flow is accessible; cron, timezone and parameters are valid.
- Outcome: a schedule is managed or creates one idempotent run.

Create and trigger use the flow run rule. Update/delete requires admin, flow owner or the editor who created the schedule. Scheduler instances use database leases. Scheduled fires use `schedule:{id}:{fire_time}` and append a system audit event.

## Manage Users and Audit

- Actor: administrator.
- Preconditions: at least one active administrator remains.
- Outcome: accounts and roles change without leaving old sessions active; audit history remains queryable.

Creating or updating a user is admin-only. Password change and deactivation revoke sessions. The API blocks removal of the final active admin. Audit and security-operation endpoints are admin-only and have no mutation route.

## Isolate Connector Discovery

- Actor: engine startup.
- Preconditions: third-party entry points may be installed.
- Outcome: valid manifests are available; a bad package cannot terminate engine startup.

The parent enumerates metadata but imports each external entry point in a child Python process. The child receives a reduced environment with no `SIFTLANE_ENGINE_SECRET_*`, a timeout and an output-size cap. A crash, timeout, invalid contract or oversized response becomes a connector health error and security alert.

This is a fault boundary, not a hostile-code OS sandbox. Managed P4 execution uses the same process boundary and does not grant connector code direct database authority.

## Manage And Execute A Connector

- Actor: administrator for lifecycle; administrator/editor for execution.
- Preconditions: the wheel exists in the configured inbox, its SHA-256 is supplied, and its manifest is compatible.
- Outcome: a reviewed package is installed, activated and executed without importing its code into the engine process.

Install copies the verified wheel into a versioned package directory, creates an isolated environment, validates the connector contract and records the active/previous version. Upgrade preserves the prior version for rollback. Enable, disable, rollback and uninstall are admin-only and audited. Execution rejects viewers, resolves only a connector-scoped credential, passes it through worker stdin and records no plaintext.

## Deliver Run Results

- Actor: administrator/editor; viewer may inspect team-visible history only.
- Preconditions: the actor can run the source flow and read the delivery target; an optional credential is scoped to that target.
- Outcome: one idempotent delivery reaches NDJSON/Webhook success, cancellation or a visible dead letter.

Target create requires a non-viewer. Update/delete/replay/cancel requires target owner or admin. The worker claims due attempts, sends a bounded payload with Bearer or HMAC authentication, records response/error metadata, applies bounded exponential backoff and stops at the configured attempt limit. Manual replay is audited and creates another controlled attempt; it never edits prior history.

## Back Up, Upgrade And Restore

- Actor: deployment operator outside the application API.
- Preconditions: matching release artifacts, the stable engine secret key and a verified backup are available.
- Outcome: schema 5 becomes ready with counts and integrity preserved, or the pre-upgrade database and prior application are restored.

`siftlane-ops backup` uses SQLite online backup and writes a versioned manifest plus SHA-256. Restore verifies the manifest and integrity, creates a safety copy when replacing a database, writes a temporary copy and atomically promotes it. The operator then checks readiness, schema status, counts, login and a non-destructive delivery.
