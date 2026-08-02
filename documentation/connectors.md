# Managed Connectors

## Runtime Boundary

Every managed connector is described and executed by `siftlane_engine.connector_worker` in a child Python process. The worker receives a minimal environment, a bounded stdin request, an execution timeout and an 8 MiB stdout limit. Connector stderr is never returned through the API.

The built-in `io.siftlane.json-feed` reference connector uses the same child-process path. It fetches JSON Feed 1.0/1.1 over the managed HTTP context and normalizes feed items into the Connector SDK v1 item contract.

## Package Lifecycle

1. Place a reviewed `.whl` in `<data-dir>/connector-inbox`.
2. Calculate its SHA-256 and submit only the file name and digest to the install or upgrade API.
3. The engine rejects path traversal, digest mismatch, missing or duplicate entry points, invalid manifests and unsupported `siftlane.connector/v1` contracts.
4. Accepted wheels are extracted to `<data-dir>/connectors/<sha256>` and loaded only by the connector worker.
5. Upgrade preserves the previous version and package path. Rollback swaps the current and previous records without changing the engine version.
6. Disable a faulty connector before investigation. Uninstall removes its registration and private package directories.

Administrators own install, upgrade, enable, disable, rollback and uninstall. Editors may execute an enabled connector. Viewers can inspect connector metadata but cannot execute or change it.

## Credentials

Connector credentials are stored as scoped secrets with `scope_type=connector` and `scope_id=<connector-id>`. The database contains only Fernet ciphertext derived from `SIFTLANE_ENGINE_SECRET_KEY`. The plaintext is decrypted immediately before execution and appears only in the worker stdin envelope.

Rotate a credential by creating the same scope and name again. The record version increases while its ID remains stable. Delete credentials before uninstalling a connector when their lifecycle must end together.

## Failure And Rollback

- A discovery, timeout, oversized output or invalid JSON failure marks the operation failed but does not terminate the engine.
- An incompatible upgrade does not replace the active version.
- Disable isolates a connector immediately.
- Rollback is available only when a previous version exists.
- The API and audit log record metadata and outcomes, never credential values or connector stderr. A connector response containing credential material is rejected before response-model serialization.
