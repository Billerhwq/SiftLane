# Siftlane Connector SDK v1

The connector SDK is an independent Python contract. A connector package declares
what it can do in a validated manifest and implements one async runtime method.
The engine owns credentials, event persistence, and controlled HTTP transport.

## Package entry point

Connector distributions register one factory in `pyproject.toml`:

```toml
[project.entry-points."siftlane.connectors"]
catalog = "acme_connector:create_connector"
```

The factory must return an object that implements `ConnectorRuntime`. Connector IDs
must be globally stable, and duplicate IDs prevent the engine from starting.

## Minimal runtime

```python
from siftlane_connector_sdk import (
    ConnectorCapability,
    ConnectorManifest,
    ConnectorOperationRequest,
    ConnectorOperationResult,
)


class CatalogConnector:
    @property
    def manifest(self) -> ConnectorManifest:
        return ConnectorManifest(
            id="acme.catalog",
            name="Acme catalog",
            version="1.0.0",
            capabilities=[
                ConnectorCapability(
                    id="search_content",
                    label="Search content",
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                )
            ],
        )

    async def execute(self, request, context) -> ConnectorOperationResult:
        if request.capability != "search_content":
            raise ValueError("unsupported capability")
        # Use context.http and context.secrets. Do not create an unrestricted client.
        return ConnectorOperationResult(items=[])


def create_connector() -> CatalogConnector:
    return CatalogConnector()
```

## Contract boundaries

- `ConnectorManifest` describes capabilities, auth modes, JSON Schemas, rate limits,
  browser requirements, allowed domains, and media access.
- `ConnectorOperationRequest` carries a capability ID, validated parameters, an
  opaque `SecretRef`, cursor, and result limit.
- `ConnectorOperationResult` returns normalized `ConnectorItem` records and an
  optional next cursor.
- `ConnectorContext` injects a secret provider, durable event sink, and controlled
  HTTP transport. The connector never receives the engine database or flow state.
- Secrets are references. They must never be placed in manifests, events, items,
  exception messages, or metadata.

The executable runtime is a trusted Python extension. Production deployments should
run third-party connectors in isolated worker processes or containers. Flow JSON
still cannot contain arbitrary Python, JavaScript, or shell code.

## Discovery endpoints

```text
GET /api/v1/connectors
GET /api/v1/connector-contract
```

The contract endpoint publishes the exact v1 JSON Schemas for the manifest,
operation request, and operation result. OpenAPI remains available at `/docs`.
