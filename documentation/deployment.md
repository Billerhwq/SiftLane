# Linux Deployment

## Supported Boundary

Siftlane v1 supports one Linux host, one engine container, one Web container and one persistent SQLite volume. It does not claim high availability, multi-host scheduling or zero-downtime database migration.

Minimum qualification profile: 2 CPU cores, 4 GiB RAM, 10 GiB persistent storage, Docker Engine 27+ and Compose v2. The accepted workload is 120 stored runs with 2,400 results at eight concurrent writers within 75 seconds and below 64 MiB of database storage. Re-qualify before raising these limits materially.

## First Start

Create `engine/.env` outside version control with mode `0600`:

```dotenv
SIFTLANE_ENGINE_BOOTSTRAP_ADMIN_USERNAME=admin
SIFTLANE_ENGINE_BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-unique-12-character-password
SIFTLANE_ENGINE_SECRET_KEY=replace-with-a-stable-random-value-at-least-32-characters
SIFTLANE_ENGINE_WORKER_COUNT=2
```

Then run:

```bash
cd engine
docker compose config
docker compose up --build --wait --wait-timeout 180 --detach
curl --fail http://127.0.0.1:8090/health/ready
curl --fail http://127.0.0.1:8080/
docker compose ps
```

The engine and Web ports bind only to host loopback. Put an authenticated TLS reverse proxy in front when remote access is required. Update both `SIFTLANE_ENGINE_ALLOWED_ORIGINS` and the Web image `VITE_API_BASE_URL`/CSP for the public origin.

## Paths And Lifecycle

- Persistent data: Docker volume `siftlane-data`, mounted at `/data`.
- Structured logs: stdout/stderr with JSON driver rotation, 10 MiB x 3 files.
- Temporary files: bounded tmpfs mounts.
- Start: `docker compose up --detach --wait`.
- Stop: `docker compose stop`.
- Logs: `docker compose logs --since 30m engine web`.
- Remove containers but preserve data: `docker compose down`.

Never use `docker compose down --volumes` on a production deployment. Back up `/data/crawler.db` through `siftlane-ops backup` before upgrades.

## Clean-Host Evidence

The `linux deployment` CI job builds both images on Ubuntu, starts the hardened Compose file, checks engine liveness/readiness and the Web root, preserves logs, and then removes its disposable volume. A local Windows candidate cannot replace this Linux evidence.
