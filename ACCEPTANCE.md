# Siftlane Phase Acceptance

This document defines the evidence required to promote Siftlane between phases.
A feature is not accepted merely because implementation or a test file exists.

## Gate Rules

- Every mandatory row must pass in one clean verification run.
- Automated evidence is produced by `scripts/verify.ps1`.
- End-to-end services must be started by Playwright, use an isolated database,
  and not depend on a developer's existing processes or absolute paths.
- Failures, skipped checks, missing dependencies, or missing evidence keep the
  target phase in acceptance rather than completed.

## P1 Acceptance

| ID | Mandatory outcome | Evidence | Status |
| --- | --- | --- | --- |
| P1-01 | Create, select, edit, connect, save, delete, and run a DAG from the browser. | `apps/web/tests/p1.spec.ts`; API flow tests | Passed |
| P1-02 | Node configuration is generated from engine schemas and invalid graphs/config are rejected. | `engine/tests/test_models.py`; P1 browser test | Passed |
| P1-03 | The four-node fixture flow persists exactly two normalized results. | P1 browser test; `engine/scripts/smoke_test.py` | Passed |
| P1-04 | Runs expose durable ordered events, two-line live activity, full ledger, and resumable SSE. | P1 browser test; API/service tests | Passed |
| P1-05 | Queueing, cancellation, immutable run snapshots, restart recovery, and controlled HTTP policy work. | Engine service, storage, process recovery, and security tests | Passed |
| P1-06 | The 390x844 UI uses coherent drawers and has no document-level horizontal overflow. | P1 mobile browser test | Passed |
| P1-07 | Connector SDK v1 schemas and discovery boundaries are exposed without claiming installed connectors. | Connector and API tests | Passed |

## P2 Acceptance

| ID | Mandatory outcome | Evidence | Status |
| --- | --- | --- | --- |
| P2-01 | Conditions route records only through explicit `true`/`false` ports. | `test_condition_routes_true_and_false_ports`; P2 browser test | Passed |
| P2-02 | Loop and pagination expansion obey node and flow bounds without graph back-edges. | `test_loop_and_pagination_are_bounded` | Passed |
| P2-03 | Transient failures retry with bounded policy and exhausted retries fail clearly. | `test_retry_succeeds_and_exhausts`; retry inspector browser assertion | Passed |
| P2-04 | Checksummed checkpoints restore completed nodes and process restart produces exact, duplicate-free results. | Checkpoint and process recovery tests | Passed |
| P2-05 | Timezone schedules use leases and idempotency, support CRUD/pause/manual trigger, and survive competing claims. | Schedule API/engine tests; P2 browser test | Passed |
| P2-06 | Branch handles, retry editing, and schedule operations are usable from the control plane. | `apps/web/tests/p2.spec.ts` | Passed |
| P2-07 | Engine tests, production web build, and all P1/P2 browser tests pass in one isolated run. | `scripts/verify.ps1` output and `outputs/` screenshots | Passed |

## P2 Release Hardening Acceptance

| ID | Mandatory outcome | Evidence | Status |
| --- | --- | --- | --- |
| RH-01 | One root command runs engine tests, the production Web build, all P1/P2 browser tests, and release metadata checks. | `scripts/verify.ps1` | Passed |
| RH-02 | `VERSION`, Python metadata/runtime, Web package/lockfile, and release tag rules agree on `0.2.0`. | `scripts/check-release.ps1`; API version test | Passed |
| RH-03 | Pull requests, `main`, manual runs, and release callers execute the Windows acceptance gate. | `.github/workflows/ci.yml` | Implemented; remote run pending |
| RH-04 | A `v*` tag must pass the reusable acceptance workflow before any GitHub Release is created. | `.github/workflows/release.yml` | Implemented; tag run pending |
| RH-05 | Candidate packaging produces wheel, sdist, Web zip, manifest, and SHA-256 sums and smoke-tests both installable surfaces. | `scripts/package-release.ps1` | Passed |
| RH-06 | Release preparation, branch protection, stop conditions, post-release checks, and rollback are documented. | `documentation/release.md`; P2 release PRD | Passed |
| RH-07 | Formal release state is not claimed before the reviewed commit is pushed and the matching tag workflow passes. | Promotion decision; release runbook | Passed |

## Verification Evidence

- Engine: `26 passed`; one upstream Starlette `httpx` deprecation warning.
- Web: TypeScript and Vite production build passed; 1,794 modules transformed.
- Browser: `3 passed` covering P1 desktop/mobile and P2 branch/retry/scheduler.
- Runtime: Playwright created an isolated database, started all three services, and
  released ports 5173, 8090, and 8877 after the run.
- Visual evidence: `outputs/p1-desktop.png`, `outputs/p1-desktop-results.png`,
  `outputs/p1-mobile.png`, `outputs/p2-branch-retry.png`, and
  `outputs/p2-scheduler.png`.
- Release candidate: wheel, sdist, Web zip, `manifest.json`, and `SHA256SUMS.txt`
  were produced; wheel installation, Web extraction, and an independent checksum
  pass succeeded.

## Promotion Decision

Current decision: **P2 completed**.

All mandatory P1 and P2 rows passed from the same repository revision through the
root verification command. New P2 work must preserve this gate.

Release state: **`v0.2.0` candidate ready; not formally released**.

Formal release requires every RH row to pass, the complete baseline to be reviewed
and pushed, `P2 acceptance / acceptance` to be required on `main`, and the matching
tag workflow to create the GitHub Release. A local artifact build is evidence for a
candidate, not evidence that an external release exists.
