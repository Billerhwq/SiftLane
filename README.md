# Siftlane

Siftlane is an independent Python and React crawler workflow product. It combines
inspectable DAG definitions, controlled HTTP collection, structured extraction,
durable runs, resumable SSE events, and result inspection in one deployable system.

It borrows workflow ideas from spider-flow and platform-adapter boundaries from
MediaCrawler, but it does not embed either project or depend on SubtleSight.

## Structure

```text
Siftlane/
|- apps/web/                 React + TypeScript control plane
|- engine/                   FastAPI DAG engine and connector SDK
|- design-system/            Surface briefs
|- designs/                  Approved prototypes
|- documentation/            Architecture, permissions, operations, and test map
|- outputs/                  Verification screenshots and runtime logs
|- ACCEPTANCE.md             P0-P5 promotion gates and evidence
|- PRD-SiftLane-product-lifecycle.md  P0-P5 lifecycle requirements
|- PRD-P2-release-hardening.md  P2 release requirements and decision rules
|- VERSION                   Release version source
|- PRODUCT.md                Product truth and boundaries
`- DESIGN.md                 Cloud Blue Console design system
```

## Current closed loop

- Create, edit, connect, save, delete, and run a crawler flow from the browser.
- Configure nodes from engine-provided JSON Schemas.
- Follow the newest two SSE events without moving the canvas.
- Expand the complete durable event ledger on demand.
- Inspect run history and normalized result rows.
- Discover installed connectors and consume the Connector SDK v1 contract.
- Recover queued work, cancel runs, resume SSE, and enforce controlled HTTP policy.
- Route records through explicit `true`/`false` branch ports.
- Expand bounded loops and page-number pagination without graph back-edges.
- Retry transient node failures with configurable exponential backoff.
- Resume completed nodes from checksummed, compressed SQLite checkpoints.
- Create, pause, edit, delete, and manually trigger timezone-aware cron schedules.

## Recovery guarantee

Each completed node stores its port-aware output as a compressed checkpoint. After
an engine restart, completed nodes are restored and only the interrupted node and
its downstream nodes execute again. Result writes use `(run_id, external_id)` as
their idempotency boundary, and final counts are read from the durable result table.
The process-level acceptance test force-kills a worker during a 250-item emit,
restarts it against the same database, and verifies exact, duplicate-free output.

## Phase status

| Phase | Status | Milestone |
| --- | --- | --- |
| P0 product and engineering baseline | Completed | Retrospective baseline; no separate tag |
| P1 single-operator core workflow | Completed | `0.1.x` functional baseline |
| P2 reliable orchestration and release | Released | `v0.2.0` |
| P3 secure team collaboration | Local implementation accepted; formal release blocked | `v0.3.0` local candidate |
| P4 managed connectors and delivery | Local candidate accepted; formal release blocked | `v0.4.0` local candidate |
| P5 production readiness and GA | GA candidate qualification | Target `v1.0.0` |

The lifecycle gate passes the complete engine suite, production Web build,
isolated P1-P5 browser acceptance, GA qualification and security checks in one
command. Version `v0.2.0` was published by the successful tag workflow with all
five release assets. Administrator confirmation of required Windows and Linux
`main` checks still blocks formal P3/P4/P5 release status, not the recorded
`v0.2.0` publication.

See `PRD-SiftLane-product-lifecycle.md` for the complete phase scope, dependencies,
entry and exit criteria, release rules, and rollback rules. See `ACCEPTANCE.md` for
the itemized gates, evidence, current decision, and governance debt.

## Start

Prerequisites: Python 3.11+ and Node.js 20.19+ or 22.12+.

Backend:

```powershell
cd engine
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\siftlane-engine
```

Frontend:

```powershell
cd apps\web
npm ci
npm run dev
```

- Console: http://127.0.0.1:5173
- Engine health: http://127.0.0.1:8090/health
- OpenAPI: http://127.0.0.1:8090/docs

## Verification

```powershell
.\scripts\verify.ps1 -Install
```

The install step also provisions Playwright's pinned Chromium build. After dependencies
are installed, omit `-Install` for repeat runs. Playwright starts an isolated engine,
the local fixture server, and Vite automatically. See
`ACCEPTANCE.md` for the phase promotion criteria. The command also checks that all
release metadata uses the version in `VERSION`.

When the Playwright browser CDN is unavailable, use an installed Chrome explicitly:

```powershell
.\scripts\verify.ps1 -Install -BrowserChannel chrome
```

## Release candidate

Run the complete local release gate and build smoke-tested artifacts with:

```powershell
.\scripts\release.ps1 -Install -BrowserChannel chrome
```

The command writes the Python wheel, Python source distribution, Web zip, manifest,
and SHA-256 list to the ignored `release-artifacts/` directory. It never commits,
tags, pushes, deploys, or publishes. See `documentation/release.md` for branch
protection, formal tag release, post-release verification, and rollback steps.

See `engine/CONNECTOR_SDK.md` for the connector entry-point and runtime contract.
