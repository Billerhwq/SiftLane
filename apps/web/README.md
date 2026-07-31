# Siftlane Web

React control plane for the Siftlane crawler engine. The node palette and inspector
are driven by the engine capability schemas rather than hard-coded forms.

## Run locally

```powershell
npm install
npm run dev
```

The default engine URL is `http://127.0.0.1:8092`. Override it when needed:

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8090"
$env:VITE_API_TOKEN="local-token"
npm run dev
```

## Verify

```powershell
npm run build
npx playwright test
```

The Playwright test creates a flow through the UI, updates node configuration,
saves it, runs it against a local fixture, follows SSE events, and verifies two
persisted result rows. It also checks the mobile rail and inspector drawers.
