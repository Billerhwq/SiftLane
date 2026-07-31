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
|- ACCEPTANCE.md             P1/P2 promotion gates
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

P2 is completed. The mandatory P1/P2 gate passes the engine suite, production web
build, and isolated browser acceptance tests in one command. See `ACCEPTANCE.md` for
the criteria and evidence map. Version `0.2.0` is the P2 release candidate; it is not
a formal release until the protected tag workflow succeeds.

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
