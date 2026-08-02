# Release Runbook

## Release Boundary

Siftlane publishes a Python wheel, Python source distribution and production Web zip, plus `manifest.json` and `SHA256SUMS.txt`. It does not publish to PyPI/npm/container registries or deploy a hosted service. The Compose files are a reproducible self-hosted deployment input, not a hosted release asset.

## Authoritative Candidate Gate

From the repository root:

```powershell
.\scripts\release.ps1 -Install -BrowserChannel chrome
```

Use `-AllowDirty` only to exercise a local candidate before commit. A tagged release must run from a clean reviewed `main` commit. For `v1.0.0`, the gate includes all P0-P5 engine/browser tests, the production build, 30-second capacity/backup/soak qualification, dependency and credential security audits, release metadata, package smoke tests and artifact hash/path/content audit.

## Repository Governance

1. Enable GitHub Actions and allow only the release job to use `contents: write`.
2. Protect `main`; require `P2 acceptance / acceptance` and `P2 acceptance / linux deployment` to pass on the current commit.
3. Require reviewed, up-to-date branches and disallow routine bypass of failed/skipped checks.
4. Record branch protection/ruleset evidence with administrator, UTC date and repository.

The workflow name retains `P2 acceptance` for compatibility with the existing required-check identity, but its implementation is the full lifecycle gate. Until the external branch-protection evidence exists, `GOV-01` blocks formal P3/P4/P5 release status.

## Candidate Procedure

1. Confirm `VERSION`, Python metadata/runtime, Web package/lockfile, release notes and intended tag match.
2. Review the 8-section lifecycle PRD and set only evidence-backed checklist items to passed.
3. Run the authoritative local candidate gate and inspect all three P5 JSON reports and screenshots.
4. Inspect `release-artifacts/manifest.json`; independently recompute every SHA-256.
5. Commit through the normal review path and wait for both Windows lifecycle and Linux deployment jobs on the exact commit.
6. Exercise upgrade/restore on a copy, preserve the prior artifact/hash/backup and record reviewer/date.

## Formal Release

Only after the phase entry/exit conditions and governance gates are satisfied, create the matching annotated tag from accepted `main`:

```powershell
git tag -a v1.0.0 -m "Siftlane v1.0.0"
git push origin v1.0.0
```

The tag invokes the Release workflow, which reruns acceptance, packages from the tagged commit and creates the GitHub Release. Local scripts never commit, push, tag, deploy or publish. Do not create P3/P4/GA tags retroactively from one combined unreviewed commit merely to make the phase table appear complete.

## Post-Release Verification

1. Confirm the Release tag and manifest point to the reviewed clean commit.
2. Download all five assets and compare independently computed SHA-256 values.
3. Install the wheel in an empty Python 3.11+ environment; verify version, liveness, readiness and schema 5.
4. Serve the Web zip with the matching API origin and run login, known flow, connector list and NDJSON delivery checks.
5. Verify migrated counts, a current backup, metrics/alerts and Linux deployment health.
6. Record workflow/Release URLs, operator, UTC date and final promote/rollback decision.

## Stop Conditions

- Any mandatory P0-P5, security, accessibility, capacity, Linux or release check failed, skipped, bypassed or lacks required evidence.
- `GOV-01`, phase entry conditions, reviewer approval or representative-environment observation is incomplete.
- Versions, tag, commit, artifacts, manifest or checksums differ.
- Migration/restore loses integrity, a high-severity issue is unaccepted, or a secret appears in API/log/audit/artifact output.
- A breaking change or known limit is absent from release/compatibility documentation.

## Rollback

Before publication, leave failed workflow evidence, fix the issue and use a new version/tag; never move a pushed release tag. After publication, stop promotion, mark the Release as affected, disable the narrowest failing connector/target where possible, preserve logs/audit/data, restore the verified pre-upgrade backup with prior matching artifacts, validate readiness/counts and publish a new patch release after regression coverage. Never replace bytes attached to an existing version.
