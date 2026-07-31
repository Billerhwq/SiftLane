# Test Coverage Map

## Existing Coverage

| Use case | Rule and expected behavior | Evidence | Status |
| --- | --- | --- | --- |
| Graph validation | Reject cycles, disconnected nodes, invalid config, and invalid branch ports | `test_models.py`, `test_p2_engine.py` | Passed |
| Flow/run API | Persist revisions and snapshots; reject bad auth; resume SSE | `test_api.py`, `test_storage.py` | Passed |
| Controlled HTTP | Reject private targets by default | `test_security.py` | Passed |
| Recovery/cancel | Requeue/recover/cancel durably without duplicate items | `test_service.py`, `test_process_recovery.py` | Passed |
| P1 browser loop | Create/configure/run, observe events/results, and validate mobile drawers | `apps/web/tests/p1.spec.ts` | Passed |
| P2 execution | Branch, bound loop/pagination, retry, checkpoint restore, scheduler lease/idempotency | `test_p2_engine.py` | Passed |
| P2 browser loop | Branch handles, retry inspector, schedule create/pause/trigger | `apps/web/tests/p2.spec.ts` | Passed |
| Connector contract | Validate manifests, duplicates, discovery schemas | `test_connectors.py`, `test_api.py` | Passed |
| Release metadata | Keep Python runtime/package, Web package/lockfile, evidence, and tag format consistent | `test_health_and_openapi_expose_runtime_version`, `scripts/check-release.ps1` | Implemented |
| Release artifacts | Build and smoke-test wheel and Web zip; generate manifest and checksums | `scripts/package-release.ps1` | Implemented |

The required local gate is `scripts/verify.ps1`. Its release-hardening acceptance
run passed 26 engine tests, the production Web build, 3 Playwright tests, and the
release metadata check. `scripts/release.ps1` then built five candidate files and
passed the wheel, Web archive, and independent SHA-256 checks.

The `P2 acceptance` GitHub Actions workflow now runs the same gate for pull requests,
`main`, manual dispatch, and the release workflow. It passed on `main` and again from
the `v0.2.0` release workflow. Repository branch protection must still require
`P2 acceptance / acceptance` before CI can enforce merges; that administrator setting
was not changed or confirmed by this release run.

## Proposed Tests

| Type | Case | Expected behavior |
| --- | --- | --- |
| Automated integration | CORS with an unapproved origin | Browser preflight does not grant access |
| Automated integration | Corrupt checkpoint during startup recovery | Run fails visibly or safely re-executes according to an explicit policy |
| Automated integration | Scheduler restart after claim but before completion | Lease expiry produces one idempotent run |
| Automated E2E | API token enabled for browser and engine | Full P1/P2 UI path passes; missing token receives 401 |
| Guarded live | Public target respecting redirects, robots, and throttling | Policy matches a real HTTP server without private-network override |
| Manual review | Keyboard-only complete P1/P2 workflow | Focus remains visible and dialogs/drawers trap and restore focus |

## Gaps

| Priority | Unverified rule | Exposure |
| --- | --- | --- |
| High | Connector runtime is not isolated from the engine process | A malicious trusted extension can access process authority |
| Medium | Production bearer-token UI path lacks end-to-end coverage | Deployment-only auth/config errors may escape local testing |
| Medium | Recovery behavior for deliberately corrupt checkpoint data lacks a service-level acceptance case | Operational recovery may require manual intervention |
| Low | Accessibility has focused checks but no automated audit | Keyboard or semantic regressions may be missed |
