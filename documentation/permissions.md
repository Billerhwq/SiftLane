# Permissions

## Authority Model

Siftlane has one effective role: `operator`. When `SIFTLANE_ENGINE_API_TOKEN` is
non-empty, authority is derived solely from an exact bearer-token match. When it is
empty, every network client that can reach the engine has operator authority.

## Access Matrix

| Resource | Operation | Anonymous | Operator |
| --- | --- | --- | --- |
| Health | Read | Allow | Allow |
| Capabilities and connector manifests/contracts | Read | Deny when token configured | Allow |
| Flows | Create/read/update/delete | Deny when token configured | Allow all |
| Runs, snapshots, events, items | Create/read/cancel | Deny when token configured | Allow all |
| Schedules | Create/read/update/delete/trigger | Deny when token configured | Allow all |
| SQLite database | Direct access | Deny by deployment boundary | Engine process only |

There is no row-level security. Resource scope is not derived from database ownership;
all enforcement is the single API dependency in `engine/src/siftlane_engine/api.py`.

## Required Deployment Rules

- Production must set a non-empty API token and restrict the bind address/network.
- The browser token is client-visible by design; deployments must not treat it as a
  per-user secret or expose the control plane to untrusted users.
- Multi-user or multi-tenant deployment is unsupported until identities, ownership,
  and resource-level checks are implemented.
