"""Public connector contract for independently packaged Siftlane connectors."""

CONNECTOR_API_VERSION = "siftlane.connector/v1"
SDK_VERSION = "1.0.0"

from .contract import (
    AuthScheme,
    ConnectorCapability,
    ConnectorContext,
    ConnectorEvent,
    ConnectorHttpRequest,
    ConnectorHttpResponse,
    ConnectorItem,
    ConnectorManifest,
    ConnectorOperationRequest,
    ConnectorOperationResult,
    ConnectorRuntime,
    EventSink,
    HttpTransport,
    RateLimitPolicy,
    RuntimeRequirements,
    SecretProvider,
    SecretRef,
)

__all__ = [
    "CONNECTOR_API_VERSION",
    "SDK_VERSION",
    "AuthScheme",
    "ConnectorCapability",
    "ConnectorContext",
    "ConnectorEvent",
    "ConnectorHttpRequest",
    "ConnectorHttpResponse",
    "ConnectorItem",
    "ConnectorManifest",
    "ConnectorOperationRequest",
    "ConnectorOperationResult",
    "ConnectorRuntime",
    "EventSink",
    "HttpTransport",
    "RateLimitPolicy",
    "RuntimeRequirements",
    "SecretProvider",
    "SecretRef",
]
