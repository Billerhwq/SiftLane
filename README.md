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
|- outputs/                  Verification screenshots and runtime logs
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

## Start

Backend:

```powershell
cd D:\Siftlane\engine
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
$env:SIFTLANE_ENGINE_PORT="8092"
.\.venv\Scripts\siftlane-engine
```

Frontend:

```powershell
cd D:\Siftlane\apps\web
npm install
npm run dev
```

- Console: http://127.0.0.1:5173
- Engine health: http://127.0.0.1:8092/health
- OpenAPI: http://127.0.0.1:8092/docs

## Verification

```powershell
cd D:\Siftlane\engine
.\.venv\Scripts\python -m pytest -q

cd D:\Siftlane\apps\web
npm run build
npx playwright test
```

See `engine/CONNECTOR_SDK.md` for the connector entry-point and runtime contract.
