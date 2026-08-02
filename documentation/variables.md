# Variables and Secrets

## Configuration Map

| Name | Used by | Scope/source | Rotation | Risk |
| --- | --- | --- | --- | --- |
| `SIFTLANE_ENGINE_API_TOKEN` | API authorization | Server secret/environment | Replace server and browser value together | Empty disables API auth |
| `SIFTLANE_ENGINE_AUTH_MODE` | Identity mode | Server environment; `local` or `team` | Migration and restart | `local` is not multi-user authentication |
| `SIFTLANE_ENGINE_BOOTSTRAP_ADMIN_USERNAME` | First team account | Server environment | Remove after bootstrap or leave inert | Used only when no team user exists |
| `SIFTLANE_ENGINE_BOOTSTRAP_ADMIN_PASSWORD` | First team account | Server secret/environment | Rotate account password, then remove environment value | Must contain at least 12 characters; never sent to browser |
| `SIFTLANE_ENGINE_SECRET_KEY` | Fernet connector/target secret encryption | Stable server secret/environment | Planned re-encryption and credential rotation | Loss makes encrypted scoped credentials unrecoverable |
| `SIFTLANE_ENGINE_SESSION_TTL_MINUTES` | Session expiry | Server environment | Restart | Long TTL increases stolen-token exposure |
| `SIFTLANE_ENGINE_LOGIN_WINDOW_SECONDS` | Login throttling | Server environment | Restart | Window that retains failed attempts in process memory |
| `SIFTLANE_ENGINE_LOGIN_MAX_ATTEMPTS` | Login throttling | Server environment | Restart | High values weaken password-guessing resistance |
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
| `SIFTLANE_ENGINE_CONNECTOR_TIMEOUT_SECONDS` | Connector child process | Server environment | Restart | High values extend untrusted package execution |
| `SIFTLANE_ENGINE_DELIVERY_TIMEOUT_SECONDS` | Webhook delivery | Server environment | Restart | High values hold delivery capacity during target failure |
| `SIFTLANE_ENGINE_DELIVERY_POLL_SECONDS` | Delivery worker | Server environment | Restart | High values delay due attempts; very low values add DB load |
| `SIFTLANE_ENGINE_MAX_DELIVERY_BYTES` | Delivery worker | Server environment | Restart | High values increase memory, disk and receiver pressure |
| `SIFTLANE_ENGINE_READINESS_MAX_QUEUE_SIZE` | Readiness probe | Server environment | Restart | Readiness becomes unavailable above this run backlog |
| `SIFTLANE_ENGINE_ALLOW_PRIVATE_NETWORKS` | SSRF policy | Server environment | Restart | `true` permits private/loopback targets; test-only by default |
| `SIFTLANE_ENGINE_RESPECT_ROBOTS_TXT` | Collection policy | Server environment | Restart | Disabling changes collection behavior |
| `SIFTLANE_ENGINE_SECRET_*` | Connector secret provider | Server secret/environment | Rotate provider value | Must not enter events, items, manifests, or errors |
| `GITHUB_TOKEN` | Tag release workflow | GitHub Actions ephemeral token | Managed per workflow run | Release job alone receives `contents: write` |

No server secret is embedded in the Web bundle. `VITE_API_TOKEN` remains a deliberately
client-visible compatibility credential for local mode and is not user authentication.
Team session tokens are stored by the browser in local storage and sent as bearer headers;
deployments must use TLS and a restrictive content-security policy at the serving layer.

## Pre-Go-Live Checklist

- Use `team` mode for multiple users. Use a non-empty API token for non-loopback `local` mode.
- Remove the bootstrap password from the environment after the first admin exists.
- Use TLS, restrict script sources and keep session TTL proportional to deployment risk.
- Restrict bind address, firewall rules, and CORS origins.
- Keep private-network collection disabled unless the deployment explicitly requires it.
- Back up the SQLite data directory and test restart recovery.
- Review connector packages as trusted code and rotate connector secrets independently.
- Preserve `SIFTLANE_ENGINE_SECRET_KEY` in the deployment secret manager and restore the same value with the database.
- Keep connector wheels in the inbox only for reviewed installation and always supply their expected SHA-256.
- Scrape readiness and metrics from a trusted operations network; they intentionally expose operational state without a user session.
