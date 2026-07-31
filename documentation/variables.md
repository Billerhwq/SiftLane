# Variables and Secrets

## Configuration Map

| Name | Used by | Scope/source | Rotation | Risk |
| --- | --- | --- | --- | --- |
| `SIFTLANE_ENGINE_API_TOKEN` | API authorization | Server secret/environment | Replace server and browser value together | Empty disables API auth |
| `VITE_API_TOKEN` | Browser API client | Build/dev client environment | Rebuild/restart client | Bundled into client; not a private user secret |
| `VITE_API_BASE_URL` | Browser API client | Client environment | Restart/rebuild client | Wrong origin breaks connectivity |
| `SIFTLANE_ENGINE_BIND_ADDRESS` | Uvicorn | Server environment | Restart | Broad bind exposes engine |
| `SIFTLANE_ENGINE_PORT` | Uvicorn | Server environment | Restart | Must match client; canonical local port is `8090` |
| `SIFTLANE_ENGINE_DATA_DIR` | SQLite storage | Server environment | Migrate before change | Wrong path can split or lose operational state |
| `SIFTLANE_ENGINE_ALLOWED_ORIGINS` | CORS | Server environment | Restart | Over-broad origins expose bearer-authorized API calls |
| `SIFTLANE_ENGINE_WORKER_COUNT` | Worker pool | Server environment | Restart | High values increase target and SQLite load |
| `SIFTLANE_ENGINE_SCHEDULER_*` | Scheduler | Server environment | Restart | Bad lease/poll values can delay or duplicate attempts |
| `SIFTLANE_ENGINE_REQUEST_*` | Controlled HTTP | Server environment | Restart | Weak limits increase target or resource risk |
| `SIFTLANE_ENGINE_MAX_RESPONSE_BYTES` | Controlled HTTP | Server environment | Restart | High values increase memory/storage pressure |
| `SIFTLANE_ENGINE_MAX_REDIRECTS` | Controlled HTTP | Server environment | Restart | High values expand request surface |
| `SIFTLANE_ENGINE_ALLOW_PRIVATE_NETWORKS` | SSRF policy | Server environment | Restart | `true` permits private/loopback targets; test-only by default |
| `SIFTLANE_ENGINE_RESPECT_ROBOTS_TXT` | Collection policy | Server environment | Restart | Disabling changes collection behavior |
| `SIFTLANE_ENGINE_SECRET_*` | Connector secret provider | Server secret/environment | Rotate provider value | Must not enter events, items, manifests, or errors |
| `GITHUB_TOKEN` | Tag release workflow | GitHub Actions ephemeral token | Managed per workflow run | Release job alone receives `contents: write` |

No server secret is embedded in the web bundle except the deliberately client-visible
`VITE_API_TOKEN`. This is a deployment-wide bearer credential, not user authentication.

## Pre-Go-Live Checklist

- Set and test a non-empty API token over TLS or a trusted private network.
- Restrict bind address, firewall rules, and CORS origins.
- Keep private-network collection disabled unless the deployment explicitly requires it.
- Back up the SQLite data directory and test restart recovery.
- Review connector packages as trusted code and rotate connector secrets independently.
