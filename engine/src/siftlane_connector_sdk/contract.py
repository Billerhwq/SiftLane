from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator


JsonSchema = dict[str, Any]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SecretRef(ContractModel):
    """Opaque reference resolved by the engine, never serialized with a value."""

    provider: Literal["engine"] = "engine"
    key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")


class AuthScheme(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]+$")
    label: str = Field(min_length=1, max_length=80)
    type: Literal["none", "api_key", "cookie", "oauth2", "browser_session"]
    credential_schema: JsonSchema = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )


class ConnectorCapability(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]+$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    input_schema: JsonSchema
    output_schema: JsonSchema = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": True}
    )
    supports_cursor: bool = False


class RateLimitPolicy(ContractModel):
    requests: int = Field(default=30, ge=1, le=100_000)
    period_seconds: int = Field(default=60, ge=1, le=86_400)
    max_concurrency: int = Field(default=2, ge=1, le=100)


class RuntimeRequirements(ContractModel):
    browser: bool = False
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)
    media_download: bool = False


class ConnectorManifest(ContractModel):
    api_version: Literal["siftlane.connector/v1"] = "siftlane.connector/v1"
    id: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$",
    )
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(
        min_length=5,
        max_length=40,
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$",
    )
    description: str = Field(default="", max_length=500)
    capabilities: list[ConnectorCapability] = Field(min_length=1, max_length=50)
    auth_schemes: list[AuthScheme] = Field(default_factory=list, max_length=20)
    settings_schema: JsonSchema = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )
    rate_limit: RateLimitPolicy = Field(default_factory=RateLimitPolicy)
    runtime: RuntimeRequirements = Field(default_factory=RuntimeRequirements)

    @model_validator(mode="after")
    def unique_contract_ids(self) -> ConnectorManifest:
        capability_ids = [capability.id for capability in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("connector capability ids must be unique")
        auth_ids = [scheme.id for scheme in self.auth_schemes]
        if len(auth_ids) != len(set(auth_ids)):
            raise ValueError("connector auth scheme ids must be unique")
        return self


class ConnectorOperationRequest(ContractModel):
    capability: str = Field(min_length=1, max_length=80)
    parameters: dict[str, Any] = Field(default_factory=dict)
    credential: SecretRef | None = None
    cursor: str | None = Field(default=None, max_length=2000)
    limit: int = Field(default=100, ge=1, le=10_000)


class ConnectorItem(ContractModel):
    external_id: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=4000)
    title: str = Field(default="", max_length=1000)
    content: str = ""
    media_type: str = Field(default="text/plain", max_length=200)
    observed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorOperationResult(ContractModel):
    items: list[ConnectorItem] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorEvent(ContractModel):
    type: str = Field(min_length=1, max_length=120)
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str = Field(min_length=1, max_length=1000)
    data: dict[str, Any] = Field(default_factory=dict)


class ConnectorHttpRequest(ContractModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str = Field(min_length=1, max_length=4000)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    json_body: Any | None = None
    respect_robots: bool = True


class ConnectorHttpResponse(ContractModel):
    status: int = Field(ge=100, le=599)
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes


@runtime_checkable
class SecretProvider(Protocol):
    async def resolve(self, reference: SecretRef) -> str: ...


@runtime_checkable
class EventSink(Protocol):
    async def emit(self, event: ConnectorEvent) -> None: ...


@runtime_checkable
class HttpTransport(Protocol):
    async def request(self, request: ConnectorHttpRequest) -> ConnectorHttpResponse: ...


@dataclass(frozen=True, slots=True)
class ConnectorContext:
    run_id: str
    node_id: str
    secrets: SecretProvider
    events: EventSink
    http: HttpTransport


@runtime_checkable
class ConnectorRuntime(Protocol):
    @property
    def manifest(self) -> ConnectorManifest: ...

    async def execute(
        self,
        request: ConnectorOperationRequest,
        context: ConnectorContext,
    ) -> ConnectorOperationResult: ...
