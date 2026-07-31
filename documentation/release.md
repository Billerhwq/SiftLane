# Release Runbook

## Release Boundary

Siftlane P2 is released as three download formats on GitHub:

- A Python wheel for installation.
- A Python source distribution for rebuilds.
- A zip containing the production web files.

The release also includes `manifest.json` and `SHA256SUMS.txt`. P2 does not publish
to PyPI, npm, a container registry, or a deployment environment.

## Required Gate

The authoritative local candidate command is:

```powershell
.\scripts\release.ps1 -Install -BrowserChannel chrome
```

Use `-AllowDirty` only to exercise the candidate pipeline before the changes are
committed. A tagged release always runs from a clean Git checkout.

The command must pass all engine tests, the production web build, every P1/P2
Playwright test, release metadata checks, package builds, and artifact smoke tests.
It writes ignored candidate files to `release-artifacts/`.

## Repository Setup

Configure these GitHub settings before creating the first release:

1. Enable GitHub Actions for the repository.
2. Allow the repository `GITHUB_TOKEN` to create releases.
3. Protect `main` and require the `P2 acceptance / acceptance` status check.
4. Require the branch to be current before merging.
5. Do not permit a failed or skipped acceptance job to be bypassed for routine merges.

The workflow file makes the check available. Branch protection is an external
repository setting and must be confirmed by an administrator.

## Candidate Procedure

1. Confirm `VERSION`, Python metadata, runtime health version, Web package metadata,
   and the intended tag all describe the same version.
2. Update `documentation/releases/v<version>.md` with user-visible changes and any
   required action.
3. Run the local candidate command from the repository root.
4. Inspect `release-artifacts/manifest.json` and verify every distributable is listed.
5. Review and commit the complete P2 baseline through the normal PR process.
6. Wait for `P2 acceptance` to pass on the PR and again on `main`.

## Formal Release

From the accepted `main` commit, create and push the matching annotated tag:

```powershell
git tag -a v0.2.0 -m "Siftlane v0.2.0"
git push origin v0.2.0
```

The tag starts the `Release` workflow. That workflow calls the complete acceptance
workflow first. Only after it passes does the workflow rebuild, smoke-test, hash,
and upload the artifacts to a GitHub Release.

Creating or pushing the tag is a deliberate maintainer action. The local release
scripts never commit, tag, push, deploy, or publish by themselves.

## Post-Release Verification

1. Confirm the GitHub Release points to the intended tag and commit.
2. Download all five files: wheel, sdist, Web zip, manifest, and SHA-256 list.
3. Run `Get-FileHash -Algorithm SHA256` and compare the values with
   `SHA256SUMS.txt`.
4. Install the wheel in an empty Python 3.11+ environment and confirm the health
   response reports `0.2.0`.
5. Serve the extracted Web zip and confirm it can connect to an engine on the
   configured API URL.
6. Record the successful workflow URL in the release review or deployment record.

## Stop Conditions

Do not create or keep a formal release when any of these conditions is true:

- A required P1/P2 or release-hardening check failed, skipped, or was bypassed.
- The tag, package, runtime, or Web versions differ.
- A required artifact or checksum is missing.
- The tag does not point to the reviewed `main` commit.
- A known breaking change is absent from the release notes.

## Rollback

If failure is found before the GitHub Release is created, leave the failed tag
workflow as evidence, fix the issue, bump the version, and create a new tag. Do not
move an already-pushed release tag to a different commit.

If failure is found after release:

1. Mark the GitHub Release as a prerelease or remove it from normal download paths.
2. Restore the last known-good application artifacts in the deployment environment.
3. Preserve and back up the SQLite data directory before changing engine versions.
4. Open a corrective change that reproduces the failure and adds a regression test.
5. Publish a new patch version; do not replace the bytes attached to `v0.2.0`.

Database migrations are not part of P2. If a future release adds them, its runbook
must define forward and backward compatibility before release.
