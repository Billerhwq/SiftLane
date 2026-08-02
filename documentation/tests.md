# Test Coverage Map

## Automated Coverage

| Phase | Use case | Rule and expected behavior | Evidence |
| --- | --- | --- | --- |
| P0/P1 | Graph, API, storage, controlled HTTP, recovery | Reject invalid graphs/private targets; preserve snapshots, SSE, checkpoints and item identity | `engine/tests/test_models.py`, `test_api.py`, `test_storage.py`, `test_security.py`, `test_service.py`, `test_process_recovery.py` |
| P1 | Browser core loop and responsive drawers | Create/configure/run, observe events/results, no page overflow | `apps/web/tests/p1.spec.ts` and P1 screenshots |
| P2 | Branch, loop, retry, recovery and scheduler | Bounded execution, checksum restore, lease and idempotent schedule fire | `engine/tests/test_p2_engine.py`, `apps/web/tests/p2.spec.ts` |
| P2 | Release metadata and artifacts | Version parity, required evidence, wheel/sdist/Web zip, manifest, hashes and clean install smoke | `scripts/check-release.ps1`, `package-release.ps1` |
| P3 | Team authentication and sessions | Bootstrap, login, token hashing/rotation/revocation, throttling and last-admin guard | `engine/tests/test_p3_security.py` |
| P3 | Authorization and audit | Allow/deny every role across flows, runs, results, schedules, audit and security operations | `engine/tests/test_p3_security.py`, `apps/web/tests/p3.spec.ts` |
| P3 | Connector discovery isolation | Child-process timeout/output cap/reduced environment; failure cannot stop startup | `engine/tests/test_p3_security.py` |
| P4 | Managed connectors | Hash/contract/compatibility checks, lifecycle, child execution, rollback and secret stdin | `engine/tests/test_p4_integrations.py` |
| P4 | Scoped secrets and delivery | Ciphertext-only storage/API, connector-result echo rejection, target ownership, Bearer/HMAC, idempotency, bounded retry, cancel, dead letter and replay | `engine/tests/test_p4_integrations.py` |
| P4 | Integration console | Configure connector, secret, target and delivery; inspect failure/replay without plaintext | `apps/web/tests/p4.spec.ts` and `outputs/p4-integrations-delivery.png` |
| P5 | Schema, probes, metrics and backup | Schema 5 readiness, operational metrics, online backup, manifest/hash/integrity and atomic restore | `engine/tests/test_p5_operations.py` |
| P5 | Capacity and soak | 120 runs/2400 items at concurrency 8, database threshold, sustained cycles and heap limits | `scripts/p5-qualification.ps1`, `outputs/p5-*-report.json` |
| P5 | Security | Python/npm production dependency audit, repository credential scan and release artifact/path/hash scan | `scripts/security-check.ps1`, `engine/scripts/security_audit.py` |
| P5 | Accessibility and operations UI | Axe serious/critical checks, keyboard focus, Escape, 200% zoom, probes/metrics/schema browser loop | `apps/web/tests/p5.spec.ts`, `outputs/p5-production-readiness.png` |
| P5 | Linux deployment | Build hardened engine/Web images, Compose readiness, loopback ports and persisted data boundary | `.github/workflows/ci.yml` job `linux deployment` |

## Authoritative Gates

`scripts/verify.ps1` is the local lifecycle gate. For a `1.x` candidate it runs the full engine suite, production Web build, every P1-P5 Playwright test, 30-second P5 qualification, dependency/credential security checks and release metadata validation. `scripts/release.ps1` adds package construction, clean wheel/Web smoke tests, manifest/SHA-256 generation and release artifact audit.

The `P2 acceptance` GitHub Actions workflow retains its historical required-check name, executes the same Windows lifecycle gate and separately proves the Linux Compose deployment. A local Windows pass cannot substitute for the Linux job. Repository branch protection must still be confirmed by a repository administrator before P3/P4/P5 can be marked formally released.

## Manual Acceptance

The release reviewer checks the captured P3/P4/P5 browser evidence, runs the deployment/upgrade/restore instructions from a clean environment, records the candidate commit and workflow URLs, and confirms no serious accessibility or unaccepted high-severity security finding. These reviewer/date records are external release evidence and are never inferred from local test output.

## Residual Gaps

| Priority | Boundary | Exposure and handling |
| --- | --- | --- |
| High | Connector process isolation is not a kernel or VM sandbox | Install only reviewed wheels; disable/rollback the connector on fault |
| High | Single-node SQLite has no automatic failover | Operate inside the qualified capacity, verify backups and restore within the documented RTO |
| Medium | End-to-end exactly-once Webhook behavior depends on receiver idempotency | Receiver must honor `Idempotency-Key`; history and replay stay visible |
| Medium | Linux container behavior is unavailable on a Windows host without Docker | Require the `linux deployment` CI job for formal release |
