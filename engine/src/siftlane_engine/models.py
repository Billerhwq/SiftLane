from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NodeType(StrEnum):
    START = "start"
    HTTP_REQUEST = "http_request"
    HTML_EXTRACT = "html_extract"
    JSON_EXTRACT = "json_extract"
    CONDITION = "condition"
    LOOP = "loop"
    PAGINATION = "pagination"
    TRANSFORM = "transform"
    EMIT = "emit"


NODE_CONFIG_SCHEMAS: dict[NodeType, dict[str, Any]] = {
    NodeType.START: {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1000,
                "items": {"type": "string", "minLength": 1},
            }
        },
        "required": ["urls"],
        "additionalProperties": False,
    },
    NodeType.HTTP_REQUEST: {
        "type": "object",
        "properties": {
            "url": {"type": "string", "minLength": 1},
            "headers": {
                "type": "object",
                "maxProperties": 50,
                "additionalProperties": {"type": "string", "maxLength": 8192},
            },
            "respect_robots": {"type": "boolean"},
            "continue_on_error": {"type": "boolean"},
            "fallback_to_http": {"type": "boolean"},
            "force_http": {"type": "boolean"},
            "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 120},
        },
        "additionalProperties": False,
    },
    NodeType.HTML_EXTRACT: {
        "type": "object",
        "properties": {
            "item_selector": {"type": "string", "maxLength": 1000},
            "fields": {
                "type": "object",
                "minProperties": 1,
                "maxProperties": 100,
            },
            "deduplicate_by": {"type": "string", "minLength": 1, "maxLength": 120},
        },
        "required": ["fields"],
        "additionalProperties": False,
    },
    NodeType.JSON_EXTRACT: {
        "type": "object",
        "properties": {
            "items_path": {"type": "string", "maxLength": 1000},
            "fields": {
                "type": "object",
                "minProperties": 1,
                "maxProperties": 100,
            },
            "deduplicate_by": {"type": "string", "minLength": 1, "maxLength": 120},
        },
        "required": ["fields"],
        "additionalProperties": False,
    },
    NodeType.CONDITION: {
        "type": "object",
        "properties": {
            "field": {"type": "string", "minLength": 1, "maxLength": 500},
            "operator": {
                "type": "string",
                "enum": ["eq", "ne", "contains", "exists", "gt", "gte", "lt", "lte"],
            },
            "value": {},
        },
        "required": ["field", "operator"],
        "additionalProperties": False,
    },
    NodeType.LOOP: {
        "type": "object",
        "properties": {
            "items_path": {"type": "string", "minLength": 1, "maxLength": 500},
            "item_name": {"type": "string", "minLength": 1, "maxLength": 80},
            "index_name": {"type": "string", "minLength": 1, "maxLength": 80},
            "max_iterations": {"type": "integer", "minimum": 1, "maximum": 10000},
        },
        "required": ["items_path", "item_name", "index_name", "max_iterations"],
        "additionalProperties": False,
    },
    NodeType.PAGINATION: {
        "type": "object",
        "properties": {
            "url": {"type": "string", "minLength": 1, "maxLength": 4000},
            "page_parameter": {"type": "string", "minLength": 1, "maxLength": 120},
            "start_page": {"type": "integer", "minimum": 1, "maximum": 1000000},
            "max_pages": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
        "required": ["url", "page_parameter", "start_page", "max_pages"],
        "additionalProperties": False,
    },
    NodeType.TRANSFORM: {
        "type": "object",
        "properties": {
            "mapping": {
                "type": "object",
                "minProperties": 1,
                "maxProperties": 100,
            }
        },
        "required": ["mapping"],
        "additionalProperties": False,
    },
    NodeType.EMIT: {
        "type": "object",
        "properties": {
            "fields": {"type": "object", "maxProperties": 100},
            "skip_empty_content": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
}


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class FlowVisibility(StrEnum):
    PRIVATE = "private"
    TEAM = "team"


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_.-]+$",
    )
    display_name: str = Field(min_length=1, max_length=120)
    password: SecretStr = Field(min_length=12, max_length=256)
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    password: SecretStr | None = Field(default=None, min_length=12, max_length=256)
    role: UserRole | None = None
    active: bool | None = None


class UserRecord(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=256)


class CurrentUser(UserRecord):
    auth_mode: str


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: CurrentUser


class AuditRecord(BaseModel):
    id: str
    actor_user_id: str | None
    actor_username: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    detail: dict[str, Any]
    created_at: datetime


class ConnectorState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class ManagedConnectorRecord(BaseModel):
    id: str
    version: str
    previous_version: str | None = None
    state: ConnectorState
    source: str
    manifest: dict[str, Any]
    installed_at: datetime
    updated_at: datetime


class ConnectorInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(
        min_length=5,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.whl$",
    )
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class SecretScope(StrEnum):
    CONNECTOR = "connector"
    DELIVERY_TARGET = "delivery_target"


class SecretCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    scope_type: SecretScope
    scope_id: str = Field(min_length=1, max_length=200)
    value: SecretStr = Field(min_length=1, max_length=16_384)


class SecretRecord(BaseModel):
    id: str
    name: str
    scope_type: SecretScope
    scope_id: str
    owner_id: str
    created_by: str
    version: int
    created_at: datetime
    updated_at: datetime


class DeliveryTargetType(StrEnum):
    WEBHOOK = "webhook"
    NDJSON = "ndjson"


class DeliveryAuthScheme(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    HMAC_SHA256 = "hmac_sha256"


class DeliveryTargetDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    type: DeliveryTargetType
    visibility: FlowVisibility = FlowVisibility.TEAM
    enabled: bool = True
    url: str | None = Field(default=None, min_length=1, max_length=4000)
    auth_scheme: DeliveryAuthScheme = DeliveryAuthScheme.NONE
    secret_id: str | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0, le=300)

    @model_validator(mode="after")
    def validate_target(self) -> "DeliveryTargetDefinition":
        if self.type == DeliveryTargetType.WEBHOOK and not self.url:
            raise ValueError("webhook targets require a URL")
        if self.type == DeliveryTargetType.NDJSON and self.url is not None:
            raise ValueError("NDJSON targets do not accept a URL")
        if self.auth_scheme != DeliveryAuthScheme.NONE and not self.secret_id:
            raise ValueError("authenticated targets require a secret")
        if self.auth_scheme == DeliveryAuthScheme.NONE and self.secret_id is not None:
            raise ValueError("a secret requires an authentication scheme")
        return self


class DeliveryTargetRecord(DeliveryTargetDefinition):
    id: str
    owner_id: str
    created_by: str
    revision: int
    created_at: datetime
    updated_at: datetime


class DeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=200)


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    DELIVERING = "delivering"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class DeliveryRecord(BaseModel):
    id: str
    target_id: str
    run_id: str
    idempotency_key: str
    status: DeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    response_status: int | None
    error: str | None
    artifact_path: str | None
    payload_sha256: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1, le=10)
    backoff_seconds: float = Field(default=0.25, ge=0, le=60)
    max_backoff_seconds: float = Field(default=10, ge=0, le=300)
    retryable_statuses: list[int] = Field(
        default_factory=lambda: [408, 429, 500, 502, 503, 504], max_length=30
    )
    retryable_errors: list[str] = Field(
        default_factory=lambda: ["TimeoutError", "ConnectionError", "HTTPStatusError"],
        max_length=30,
    )


RETRY_POLICY_SCHEMA = RetryPolicy.model_json_schema()


class FlowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    type: NodeType
    name: str = Field(min_length=1, max_length=120)
    x: float = Field(default=0, ge=-10_000, le=10_000)
    y: float = Field(default=0, ge=-10_000, le=10_000)
    config: dict[str, Any] = Field(default_factory=dict)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)


class FlowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    source: str
    target: str
    source_port: str = Field(default="default", min_length=1, max_length=40)


class FlowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    visibility: FlowVisibility = FlowVisibility.TEAM
    max_items: int = Field(default=100, ge=1, le=10_000)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)
    parameter_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": True}
    )
    nodes: list[FlowNode] = Field(min_length=2, max_length=100)
    edges: list[FlowEdge] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_graph(self) -> FlowDefinition:
        for node in self.nodes:
            try:
                validate_json_schema(
                    instance=node.config,
                    schema=NODE_CONFIG_SCHEMAS[node.type],
                )
            except JsonSchemaValidationError as error:
                location = ".".join(str(part) for part in error.absolute_path)
                suffix = f" at {location}" if location else ""
                raise ValueError(
                    f"invalid config for node {node.id}{suffix}: {error.message}"
                ) from error

        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node ids must be unique")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("edge ids must be unique")
        known = set(node_ids)
        if any(edge.source not in known or edge.target not in known for edge in self.edges):
            raise ValueError("every edge endpoint must reference an existing node")
        starts = [node for node in self.nodes if node.type == NodeType.START]
        emits = [node for node in self.nodes if node.type == NodeType.EMIT]
        if len(starts) != 1:
            raise ValueError("a flow must contain exactly one start node")
        if not emits:
            raise ValueError("a flow must contain at least one emit node")

        types = {node.id: node.type for node in self.nodes}
        condition_ports: dict[str, set[str]] = {
            node.id: set() for node in self.nodes if node.type == NodeType.CONDITION
        }
        for edge in self.edges:
            if types[edge.source] == NodeType.CONDITION:
                if edge.source_port not in {"true", "false"}:
                    raise ValueError("condition edges must use true or false source ports")
                condition_ports[edge.source].add(edge.source_port)
            elif edge.source_port != "default":
                raise ValueError("only condition nodes expose non-default source ports")
        for node_id, ports in condition_ports.items():
            if ports != {"true", "false"}:
                raise ValueError(
                    f"condition node {node_id} must connect both true and false ports"
                )

        incoming = {node_id: 0 for node_id in node_ids}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            incoming[edge.target] += 1
            outgoing[edge.source].append(edge.target)
        ready = [node_id for node_id, count in incoming.items() if count == 0]
        ordered: list[str] = []
        while ready:
            current = ready.pop()
            ordered.append(current)
            for target in outgoing[current]:
                incoming[target] -= 1
                if incoming[target] == 0:
                    ready.append(target)
        if len(ordered) != len(node_ids):
            raise ValueError("flow graph must be acyclic")
        if starts[0].id not in ordered:
            raise ValueError("start node is not executable")

        reachable = {starts[0].id}
        changed = True
        while changed:
            changed = False
            for edge in self.edges:
                if edge.source in reachable and edge.target not in reachable:
                    reachable.add(edge.target)
                    changed = True
        if reachable != known:
            raise ValueError("every node must be reachable from the start node")
        return self


class FlowRecord(FlowDefinition):
    id: str
    owner_id: str
    revision: int
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)


class RunRecord(BaseModel):
    id: str
    flow_id: str
    flow_name: str
    flow_revision: int
    owner_id: str
    visibility: FlowVisibility
    created_by: str
    status: RunStatus
    parameters: dict[str, Any]
    idempotency_key: str | None
    current_node: str | None
    message: str | None
    processed_items: int
    total_items: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunFlowSnapshot(BaseModel):
    run_id: str
    flow_id: str
    flow_revision: int
    definition: FlowDefinition


class ItemRecord(BaseModel):
    id: str
    run_id: str
    external_id: str
    url: str
    title: str
    content: str
    media_type: str
    observed_at: datetime
    metadata: dict[str, Any]
    created_at: datetime


class EventRecord(BaseModel):
    id: str
    run_id: str
    sequence: int
    type: str
    level: str
    message: str
    data: dict[str, Any]
    created_at: datetime


class ItemPage(BaseModel):
    items: list[ItemRecord]
    next_cursor: str | None = None


class NodeCapability(BaseModel):
    type: NodeType
    label: str
    description: str
    category: str
    config_schema: dict[str, Any]
    retry_schema: dict[str, Any] = Field(default_factory=lambda: RETRY_POLICY_SCHEMA)


class NodeCheckpoint(BaseModel):
    run_id: str
    node_id: str
    outputs: dict[str, list[dict[str, Any]]]
    attempt_count: int
    emitted_count: int
    checksum: str
    created_at: datetime
    updated_at: datetime


class ScheduleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=160)
    cron: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=100)
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        if not croniter.is_valid(value):
            raise ValueError("invalid cron expression")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("unknown IANA timezone") from error
        return value


class ScheduleRecord(ScheduleDefinition):
    id: str
    owner_id: str
    visibility: FlowVisibility
    created_by: str
    revision: int
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_run_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
