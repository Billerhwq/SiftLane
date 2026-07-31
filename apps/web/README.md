# Siftlane Web

React control plane for the Siftlane crawler engine. The node palette and inspector
are driven by the engine capability schemas rather than hard-coded forms.

## Run locally

```powershell
npm install
npm run dev
```

The default engine URL is `http://127.0.0.1:8090`. Override it when needed:

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8090"
$env:VITE_API_TOKEN="local-token"
npm run dev
```

## Verify

```powershell
npm run build
npm run test:e2e
```

Playwright starts an isolated engine on port 8090, a fixture server on port 8877,
and Vite on port 5173. The tests create flows through the UI, run them, verify
durable events and results, exercise P2 branching/retry/scheduling, and check the
mobile rail and inspector drawers. The engine virtual environment must already
exist at `engine/.venv`; provision the repository-local browser once with
`npm run install:browsers`. Set `SIFTLANE_E2E_BROWSER_CHANNEL=chrome` to use an
installed Chrome when the Playwright browser CDN is unavailable.
