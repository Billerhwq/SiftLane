import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated, Any

import aiosqlite
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from siftlane_connector_sdk import (
    ConnectorManifest,
    ConnectorOperationRequest,
    ConnectorOperationResult,
)

from . import __version__
from .auth import (
    DUMMY_PASSWORD_HASH,
    LOCAL_USER_ID,
    LoginLimiter,
    Principal,
    hash_password,
    hash_session_token,
    issue_session_token,
    verify_password,
)
from .config import Settings
from .connectors import CONNECTOR_ENTRYPOINT_GROUP, ConnectorRegistry
from .integrations import IntegrationConflict
from .engine import node_capabilities
from .models import (
    AuditRecord,
    AuthSessionResponse,
    ConnectorInstallRequest,
    ConnectorState,
    CurrentUser,
    DeliveryCreate,
    DeliveryRecord,
    DeliveryTargetDefinition,
    DeliveryTargetRecord,
    EventRecord,
    FlowDefinition,
    FlowRecord,
    FlowVisibility,
    ItemPage,
    LoginRequest,
    ManagedConnectorRecord,
    RunCreate,
    RunFlowSnapshot,
    RunRecord,
    ScheduleDefinition,
    ScheduleRecord,
    SecretCreate,
    SecretRecord,
    SecretScope,
    UserCreate,
    UserRecord,
    UserRole,
    UserUpdate,
    utc_now,
)
from .service import CrawlerService, FlowDisabled, InvalidParameters
from .storage import RevisionConflict
from .telemetry import OperationsMonitor


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings()
    service = CrawlerService(configured)
    connectors = ConnectorRegistry.discover()
    login_limiter = LoginLimiter(
        max_attempts=configured.login_max_attempts,
        window_seconds=configured.login_window_seconds,
    )
    operations = OperationsMonitor()
    for connector_name, error in connectors.errors().items():
        operations.increment(
            "connector_isolation_failure_total",
            alert="connector_unavailable",
            detail={"connector": connector_name, "error": error},
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(
        title="Siftlane Engine",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.crawler = service
    app.state.connectors = connectors
    app.state.operations = operations
    if configured.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=configured.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        )

    async def authorize(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Principal:
        if configured.auth_mode == "local":
            if configured.api_token and authorization != f"Bearer {configured.api_token}":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user = await service.storage.get_user(LOCAL_USER_ID)
            if user is None:
                raise HTTPException(status_code=503, detail="local identity is unavailable")
            return Principal(user=user, auth_mode="local")

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = authorization[7:]
        if not token:
            raise HTTPException(status_code=401, detail="authentication required")
        session = await service.storage.get_session_user(
            hash_session_token(token), utc_now()
        )
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="session is invalid or expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        session_id, user, _ = session
        return Principal(user=user, auth_mode="team", session_id=session_id)

    Actor = Annotated[Principal, Depends(authorize)]

    async def audit(
        actor: Principal | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str = "success",
        detail: dict[str, Any] | None = None,
        *,
        username: str | None = None,
    ) -> AuditRecord:
        return await service.storage.add_audit(
            actor_user_id=actor.id if actor else None,
            actor_username=actor.username if actor else username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            detail=detail,
        )

    async def deny(
        actor: Principal,
        action: str,
        resource_type: str,
        resource_id: str | None,
        *,
        hide_resource: bool = True,
    ) -> None:
        operations.increment("authorization_denied_total")
        await audit(actor, action, resource_type, resource_id, "denied")
        raise HTTPException(
            status_code=404 if hide_resource else 403,
            detail="resource not found" if hide_resource else "permission denied",
        )

    def can_read(actor: Principal, owner_id: str, visibility: FlowVisibility) -> bool:
        return (
            actor.role == UserRole.ADMIN
            or actor.id == owner_id
            or visibility == FlowVisibility.TEAM
        )

    def can_run(actor: Principal, owner_id: str, visibility: FlowVisibility) -> bool:
        return (
            actor.role == UserRole.ADMIN
            or (
                actor.role == UserRole.EDITOR
                and (actor.id == owner_id or visibility == FlowVisibility.TEAM)
            )
        )

    def can_manage(actor: Principal, owner_id: str) -> bool:
        return actor.role == UserRole.ADMIN or (
            actor.role == UserRole.EDITOR and actor.id == owner_id
        )

    def can_manage_schedule(actor: Principal, schedule: ScheduleRecord) -> bool:
        return actor.role == UserRole.ADMIN or (
            actor.role == UserRole.EDITOR
            and actor.id in {schedule.owner_id, schedule.created_by}
        )

    async def require_admin(actor: Principal, action: str, resource_type: str, resource_id: str | None = None) -> None:
        if actor.role != UserRole.ADMIN:
            await deny(actor, action, resource_type, resource_id, hide_resource=False)

    @app.get("/health")
    async def health() -> dict[str, object]:
        schema = await service.storage.schema_status()
        return {
            "status": "UP",
            "version": __version__,
            "workers": configured.worker_count,
            "queuedRuns": service.queue_size,
            "database": str(configured.database_path),
            "authMode": configured.auth_mode,
            "schemaVersion": schema["current"],
        }

    @app.get("/health/live")
    async def health_live() -> dict[str, object]:
        return {"status": "UP", "version": __version__}

    @app.get("/health/ready")
    async def health_ready() -> JSONResponse:
        try:
            schema = await service.storage.schema_status()
            ready = bool(
                service.ready
                and schema["ready"]
                and service.queue_size <= configured.readiness_max_queue_size
            )
            payload = {
                "status": "UP" if ready else "DOWN",
                "database": "UP",
                "schemaVersion": schema["current"],
                "queueSize": service.queue_size,
            }
        except (OSError, aiosqlite.Error):
            ready = False
            payload = {"status": "DOWN", "database": "DOWN", "queueSize": service.queue_size}
        return JSONResponse(payload, status_code=200 if ready else 503)

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> PlainTextResponse:
        stats = await service.storage.operational_stats()
        lines = [operations.prometheus(queue_size=service.queue_size).rstrip()]
        lines.extend([
            "# HELP siftlane_database_bytes Size of the primary SQLite database file.",
            "# TYPE siftlane_database_bytes gauge",
            f"siftlane_database_bytes {stats['databaseBytes']}",
        ])
        lines.extend(["# TYPE siftlane_runs gauge", "# TYPE siftlane_deliveries gauge"])
        for status_name, total in sorted(stats["runs"].items()):
            lines.append(f'siftlane_runs{{status="{status_name}"}} {total}')
        for status_name, total in sorted(stats["deliveries"].items()):
            lines.append(f'siftlane_deliveries{{status="{status_name}"}} {total}')
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    @app.post("/api/v1/auth/login", response_model=AuthSessionResponse)
    async def login(payload: LoginRequest, request: Request) -> AuthSessionResponse:
        if configured.auth_mode != "team":
            raise HTTPException(status_code=409, detail="team authentication is disabled")
        username = payload.username.strip().lower()
        remote = request.client.host if request.client else "unknown"
        limiter_key = f"{remote}:{username}"
        retry_after = await login_limiter.retry_after(limiter_key)
        if retry_after:
            operations.increment(
                "login_rate_limited_total",
                alert="login_rate_limited",
                detail={"username": username},
            )
            await audit(
                None,
                "auth.login",
                "session",
                None,
                "rate_limited",
                {"remote": remote},
                username=username,
            )
            raise HTTPException(
                status_code=429,
                detail="too many login attempts",
                headers={"Retry-After": str(retry_after)},
            )
        credentials = await service.storage.get_user_credentials(username)
        password_hash = credentials[1] if credentials else DUMMY_PASSWORD_HASH
        valid = verify_password(payload.password.get_secret_value(), password_hash)
        if credentials is None or not credentials[0].active or not valid:
            operations.increment("login_failed_total")
            await login_limiter.record_failure(limiter_key)
            await audit(
                None,
                "auth.login",
                "session",
                None,
                "denied",
                {"remote": remote},
                username=username,
            )
            raise HTTPException(status_code=401, detail="invalid credentials")

        await login_limiter.reset(limiter_key)
        user = credentials[0]
        token = issue_session_token()
        expires_at = utc_now() + timedelta(minutes=configured.session_ttl_minutes)
        session_id = await service.storage.create_session(
            user.id, hash_session_token(token), expires_at
        )
        refreshed_user = await service.storage.get_user(user.id)
        if refreshed_user is None:
            raise HTTPException(status_code=503, detail="identity is unavailable")
        principal = Principal(
            user=refreshed_user,
            auth_mode="team",
            session_id=session_id,
        )
        await audit(principal, "auth.login", "session", session_id)
        return AuthSessionResponse(
            access_token=token,
            expires_at=expires_at,
            user=CurrentUser(**refreshed_user.model_dump(), auth_mode="team"),
        )

    @app.post("/api/v1/auth/logout", status_code=204)
    async def logout(actor: Actor) -> None:
        if actor.session_id:
            await service.storage.revoke_session(actor.session_id)
        await audit(actor, "auth.logout", "session", actor.session_id)

    @app.post("/api/v1/auth/refresh", response_model=AuthSessionResponse)
    async def refresh_session(actor: Actor) -> AuthSessionResponse:
        if actor.auth_mode != "team" or actor.session_id is None:
            raise HTTPException(status_code=409, detail="team authentication is disabled")
        await service.storage.revoke_session(actor.session_id)
        token = issue_session_token()
        expires_at = utc_now() + timedelta(minutes=configured.session_ttl_minutes)
        session_id = await service.storage.create_session(
            actor.id, hash_session_token(token), expires_at
        )
        user = await service.storage.get_user(actor.id)
        if user is None:
            raise HTTPException(status_code=401, detail="identity is unavailable")
        refreshed = Principal(user=user, auth_mode="team", session_id=session_id)
        await audit(
            refreshed,
            "auth.refresh",
            "session",
            session_id,
            detail={"replacedSessionId": actor.session_id},
        )
        return AuthSessionResponse(
            access_token=token,
            expires_at=expires_at,
            user=CurrentUser(**user.model_dump(), auth_mode="team"),
        )

    @app.get("/api/v1/auth/me", response_model=CurrentUser)
    async def me(actor: Actor) -> CurrentUser:
        return CurrentUser(**actor.user.model_dump(), auth_mode=actor.auth_mode)

    @app.get("/api/v1/users", response_model=list[UserRecord])
    async def list_users(actor: Actor) -> list[UserRecord]:
        if actor.role != UserRole.ADMIN:
            await deny(actor, "user.list", "user", None, hide_resource=False)
        return await service.storage.list_users()

    @app.post("/api/v1/users", response_model=UserRecord, status_code=201)
    async def create_user(payload: UserCreate, actor: Actor) -> UserRecord:
        if actor.role != UserRole.ADMIN:
            await deny(actor, "user.create", "user", None, hide_resource=False)
        try:
            user = await service.storage.create_user(
                username=payload.username.lower(),
                display_name=payload.display_name,
                password_hash=hash_password(payload.password.get_secret_value()),
                role=payload.role,
            )
        except aiosqlite.IntegrityError as error:
            raise HTTPException(status_code=409, detail="username already exists") from error
        await audit(
            actor,
            "user.create",
            "user",
            user.id,
            detail={"role": user.role.value},
        )
        return user

    @app.patch("/api/v1/users/{user_id}", response_model=UserRecord)
    async def update_user(user_id: str, payload: UserUpdate, actor: Actor) -> UserRecord:
        if actor.role != UserRole.ADMIN:
            await deny(actor, "user.update", "user", user_id, hide_resource=False)
        current = await service.storage.get_user(user_id)
        if current is None or current.id == LOCAL_USER_ID:
            raise HTTPException(status_code=404, detail="user not found")
        removes_admin = current.role == UserRole.ADMIN and (
            payload.role not in {None, UserRole.ADMIN} or payload.active is False
        )
        if removes_admin and await service.storage.count_active_admins() <= 1:
            raise HTTPException(status_code=409, detail="the last active admin cannot be removed")
        password_hash = (
            hash_password(payload.password.get_secret_value())
            if payload.password is not None
            else None
        )
        updated = await service.storage.update_user(
            user_id,
            display_name=payload.display_name,
            password_hash=password_hash,
            role=payload.role,
            active=payload.active,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="user not found")
        await audit(
            actor,
            "user.update",
            "user",
            user_id,
            detail={"role": updated.role.value, "active": updated.active},
        )
        return updated

    @app.get("/api/v1/audit", response_model=list[AuditRecord])
    async def list_audit(
        actor: Actor, limit: Annotated[int, Query(ge=1, le=1000)] = 200
    ) -> list[AuditRecord]:
        if actor.role != UserRole.ADMIN:
            await deny(actor, "audit.list", "audit", None, hide_resource=False)
        return await service.storage.list_audit(limit)

    @app.get("/api/v1/operations/security")
    async def security_operations(actor: Actor) -> dict[str, Any]:
        if actor.role != UserRole.ADMIN:
            await deny(actor, "operations.security.read", "operations", None, hide_resource=False)
        return operations.snapshot()

    @app.get("/api/v1/operations/schema")
    async def schema_operations(actor: Actor) -> dict[str, Any]:
        await require_admin(actor, "schema.read", "schema")
        return await service.storage.schema_status()

    @app.get("/api/v1/capabilities")
    async def capabilities(actor: Actor):
        managed_connectors = await service.integrations.list_connectors()
        return {
            "protocolVersion": "1.0",
            "nodeTypes": node_capabilities(),
            "features": {
                "durableQueue": True,
                "sse": True,
                "idempotency": True,
                "browserAutomation": False,
                "arbitraryCode": False,
                "connectorSdk": True,
                "branching": True,
                "boundedLoops": True,
                "pagination": True,
                "retries": True,
                "checkpoints": True,
                "scheduler": True,
                "teamAuth": configured.auth_mode == "team",
                "resourceAuthorization": True,
                "auditLog": True,
                "managedConnectors": True,
                "encryptedSecrets": True,
                "dataDelivery": True,
            },
            "connectorCount": len(managed_connectors),
        }

    @app.get("/api/v1/connectors", response_model=list[ConnectorManifest])
    async def list_connectors(actor: Actor) -> list[ConnectorManifest]:
        return connectors.manifests()

    @app.get("/api/v1/managed-connectors", response_model=list[ManagedConnectorRecord])
    async def list_managed_connectors(actor: Actor) -> list[ManagedConnectorRecord]:
        return await service.integrations.list_connectors()

    @app.post("/api/v1/managed-connectors/install", response_model=ManagedConnectorRecord, status_code=201)
    async def install_connector(payload: ConnectorInstallRequest, actor: Actor) -> ManagedConnectorRecord:
        await require_admin(actor, "connector.install", "connector")
        try:
            connector = await service.connector_manager.install(payload)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="connector package was not found in the inbox")
        except (ValueError, RuntimeError) as error:
            await audit(actor, "connector.install", "connector", None, "failed", {"error": str(error)})
            raise HTTPException(status_code=409, detail=str(error))
        await audit(actor, "connector.install", "connector", connector.id, detail={"version": connector.version})
        return connector

    @app.post("/api/v1/managed-connectors/{connector_id}/upgrade", response_model=ManagedConnectorRecord)
    async def upgrade_connector(connector_id: str, payload: ConnectorInstallRequest, actor: Actor) -> ManagedConnectorRecord:
        await require_admin(actor, "connector.upgrade", "connector", connector_id)
        try:
            connector = await service.connector_manager.install(payload, upgrade_id=connector_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="connector package was not found in the inbox")
        except (ValueError, RuntimeError, KeyError) as error:
            await audit(actor, "connector.upgrade", "connector", connector_id, "failed", {"error": str(error)})
            raise HTTPException(status_code=409, detail=str(error))
        await audit(actor, "connector.upgrade", "connector", connector_id, detail={"version": connector.version})
        return connector

    @app.post("/api/v1/managed-connectors/{connector_id}/enable", response_model=ManagedConnectorRecord)
    async def enable_connector(connector_id: str, actor: Actor) -> ManagedConnectorRecord:
        await require_admin(actor, "connector.enable", "connector", connector_id)
        try:
            connector = await service.integrations.set_connector_state(connector_id, ConnectorState.ENABLED)
        except KeyError:
            raise HTTPException(status_code=404, detail="connector not found")
        await audit(actor, "connector.enable", "connector", connector_id)
        return connector

    @app.post("/api/v1/managed-connectors/{connector_id}/disable", response_model=ManagedConnectorRecord)
    async def disable_connector(connector_id: str, actor: Actor) -> ManagedConnectorRecord:
        await require_admin(actor, "connector.disable", "connector", connector_id)
        try:
            connector = await service.integrations.set_connector_state(connector_id, ConnectorState.DISABLED)
        except KeyError:
            raise HTTPException(status_code=404, detail="connector not found")
        await audit(actor, "connector.disable", "connector", connector_id)
        return connector

    @app.post("/api/v1/managed-connectors/{connector_id}/rollback", response_model=ManagedConnectorRecord)
    async def rollback_connector(connector_id: str, actor: Actor) -> ManagedConnectorRecord:
        await require_admin(actor, "connector.rollback", "connector", connector_id)
        try:
            connector = await service.integrations.rollback_connector(connector_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="connector not found")
        except IntegrationConflict as error:
            raise HTTPException(status_code=409, detail=str(error))
        await audit(actor, "connector.rollback", "connector", connector_id, detail={"version": connector.version})
        return connector

    @app.delete("/api/v1/managed-connectors/{connector_id}", status_code=204)
    async def uninstall_connector(connector_id: str, actor: Actor) -> None:
        await require_admin(actor, "connector.uninstall", "connector", connector_id)
        if not await service.connector_manager.uninstall(connector_id):
            raise HTTPException(status_code=404, detail="connector not found")
        await audit(actor, "connector.uninstall", "connector", connector_id)

    @app.post("/api/v1/managed-connectors/{connector_id}/execute", response_model=ConnectorOperationResult)
    async def execute_managed_connector(
        connector_id: str,
        payload: ConnectorOperationRequest,
        actor: Actor,
    ) -> ConnectorOperationResult:
        if actor.role == UserRole.VIEWER:
            await deny(actor, "connector.execute", "connector", connector_id, hide_resource=False)
        try:
            result = await service.connector_manager.execute(connector_id, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail="connector or credential not found")
        except (ValueError, RuntimeError) as error:
            operations.increment("connector_isolation_failure_total", alert="connector_execution_failed", detail={"connector": connector_id})
            await audit(actor, "connector.execute", "connector", connector_id, "failed")
            raise HTTPException(status_code=502, detail=str(error))
        await audit(actor, "connector.execute", "connector", connector_id, detail={"itemCount": len(result.items)})
        return result

    @app.get("/api/v1/secrets", response_model=list[SecretRecord])
    async def list_secrets(actor: Actor) -> list[SecretRecord]:
        await require_admin(actor, "secret.list", "secret")
        return await service.integrations.list_secrets()

    @app.post("/api/v1/secrets", response_model=SecretRecord, status_code=201)
    async def create_secret(payload: SecretCreate, actor: Actor) -> SecretRecord:
        await require_admin(actor, "secret.create", "secret")
        if payload.scope_type == SecretScope.CONNECTOR:
            scope_exists = await service.integrations.get_connector(payload.scope_id) is not None
        else:
            scope_exists = await service.integrations.get_target(payload.scope_id) is not None
        if not scope_exists:
            raise HTTPException(status_code=404, detail="secret scope was not found")
        secret = await service.integrations.create_secret(payload, actor.id)
        await audit(actor, "secret.create", "secret", secret.id, detail={"scopeType": secret.scope_type.value, "scopeId": secret.scope_id, "version": secret.version})
        return secret

    @app.delete("/api/v1/secrets/{secret_id}", status_code=204)
    async def delete_secret(secret_id: str, actor: Actor) -> None:
        await require_admin(actor, "secret.delete", "secret", secret_id)
        try:
            deleted = await service.integrations.delete_secret(secret_id)
        except IntegrationConflict as error:
            raise HTTPException(status_code=409, detail=str(error))
        if not deleted:
            raise HTTPException(status_code=404, detail="secret not found")
        await audit(actor, "secret.delete", "secret", secret_id)

    @app.get("/api/v1/delivery-targets", response_model=list[DeliveryTargetRecord])
    async def list_delivery_targets(actor: Actor) -> list[DeliveryTargetRecord]:
        return [
            target for target in await service.integrations.list_targets()
            if can_read(actor, target.owner_id, target.visibility)
        ]

    @app.post("/api/v1/delivery-targets", response_model=DeliveryTargetRecord, status_code=201)
    async def create_delivery_target(payload: DeliveryTargetDefinition, actor: Actor) -> DeliveryTargetRecord:
        if actor.role == UserRole.VIEWER:
            await deny(actor, "delivery_target.create", "delivery_target", None, hide_resource=False)
        if payload.secret_id is not None:
            raise HTTPException(status_code=409, detail="create the target first, then bind its scoped secret")
        target = await service.integrations.create_target(payload, actor.id)
        await audit(actor, "delivery_target.create", "delivery_target", target.id, detail={"type": target.type.value})
        return target

    @app.put("/api/v1/delivery-targets/{target_id}", response_model=DeliveryTargetRecord)
    async def update_delivery_target(
        target_id: str,
        payload: DeliveryTargetDefinition,
        actor: Actor,
        expected_revision: Annotated[int | None, Query(alias="expectedRevision")] = None,
    ) -> DeliveryTargetRecord:
        existing = await service.integrations.get_target(target_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="delivery target not found")
        if not can_manage(actor, existing.owner_id):
            await deny(actor, "delivery_target.update", "delivery_target", target_id)
        if payload.secret_id:
            secret = await service.integrations.get_secret(payload.secret_id)
            if secret is None or secret.scope_type != SecretScope.DELIVERY_TARGET or secret.scope_id != target_id:
                raise HTTPException(status_code=409, detail="secret is not scoped to this delivery target")
        try:
            target = await service.integrations.update_target(target_id, payload, expected_revision)
        except KeyError:
            raise HTTPException(status_code=404, detail="delivery target not found")
        except IntegrationConflict as error:
            raise HTTPException(status_code=409, detail=str(error))
        await audit(actor, "delivery_target.update", "delivery_target", target_id, detail={"revision": target.revision})
        return target

    @app.delete("/api/v1/delivery-targets/{target_id}", status_code=204)
    async def delete_delivery_target(target_id: str, actor: Actor) -> None:
        target = await service.integrations.get_target(target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="delivery target not found")
        if not can_manage(actor, target.owner_id):
            await deny(actor, "delivery_target.delete", "delivery_target", target_id)
        try:
            await service.integrations.delete_target(target_id)
        except IntegrationConflict as error:
            raise HTTPException(status_code=409, detail=str(error))
        await audit(actor, "delivery_target.delete", "delivery_target", target_id)

    @app.get("/api/v1/deliveries", response_model=list[DeliveryRecord])
    async def list_deliveries(actor: Actor, limit: int = Query(default=200, ge=1, le=500)) -> list[DeliveryRecord]:
        accessible: list[DeliveryRecord] = []
        for delivery in await service.integrations.list_deliveries(limit):
            target = await service.integrations.get_target(delivery.target_id)
            run = await service.storage.get_run(delivery.run_id)
            if target and run and can_read(actor, target.owner_id, target.visibility) and can_read(actor, run.owner_id, run.visibility):
                accessible.append(delivery)
        return accessible

    @app.post("/api/v1/deliveries", response_model=DeliveryRecord, status_code=201)
    async def create_delivery(payload: DeliveryCreate, actor: Actor) -> DeliveryRecord:
        if actor.role == UserRole.VIEWER:
            await deny(actor, "delivery.create", "delivery", None, hide_resource=False)
        target = await service.integrations.get_target(payload.target_id)
        run = await service.storage.get_run(payload.run_id)
        if target is None or run is None or not can_run(actor, run.owner_id, run.visibility) or not can_read(actor, target.owner_id, target.visibility):
            await deny(actor, "delivery.create", "delivery", None)
        delivery = await service.delivery.create(payload, actor.id)
        await audit(actor, "delivery.create", "delivery", delivery.id, detail={"status": delivery.status.value, "idempotencyKey": delivery.idempotency_key})
        return delivery

    async def manageable_delivery(delivery_id: str, actor: Principal, action: str) -> DeliveryRecord:
        delivery = await service.integrations.get_delivery(delivery_id)
        if delivery is None:
            raise HTTPException(status_code=404, detail="delivery not found")
        target = await service.integrations.get_target(delivery.target_id)
        if target is None or not can_manage(actor, target.owner_id):
            await deny(actor, action, "delivery", delivery_id)
        return delivery

    @app.post("/api/v1/deliveries/{delivery_id}/replay", response_model=DeliveryRecord)
    async def replay_delivery(delivery_id: str, actor: Actor) -> DeliveryRecord:
        await manageable_delivery(delivery_id, actor, "delivery.replay")
        try:
            await service.integrations.replay_delivery(delivery_id)
            delivery = await service.delivery.process(delivery_id)
        except IntegrationConflict as error:
            raise HTTPException(status_code=409, detail=str(error))
        await audit(actor, "delivery.replay", "delivery", delivery_id, detail={"status": delivery.status.value})
        return delivery

    @app.post("/api/v1/deliveries/{delivery_id}/cancel", response_model=DeliveryRecord)
    async def cancel_delivery(delivery_id: str, actor: Actor) -> DeliveryRecord:
        await manageable_delivery(delivery_id, actor, "delivery.cancel")
        try:
            delivery = await service.integrations.cancel_delivery(delivery_id)
        except IntegrationConflict as error:
            raise HTTPException(status_code=409, detail=str(error))
        await audit(actor, "delivery.cancel", "delivery", delivery_id)
        return delivery

    @app.get("/api/v1/connector-contract")
    async def connector_contract(actor: Actor) -> dict[str, object]:
        return {
            "apiVersion": "siftlane.connector/v1",
            "entryPointGroup": CONNECTOR_ENTRYPOINT_GROUP,
            "schemas": {
                "manifest": ConnectorManifest.model_json_schema(),
                "operationRequest": ConnectorOperationRequest.model_json_schema(),
                "operationResult": ConnectorOperationResult.model_json_schema(),
            },
        }

    @app.get("/api/v1/flows", response_model=list[FlowRecord])
    async def list_flows(actor: Actor) -> list[FlowRecord]:
        return [
            flow
            for flow in await service.storage.list_flows()
            if can_read(actor, flow.owner_id, flow.visibility)
        ]

    @app.post("/api/v1/flows", status_code=201, response_model=FlowRecord)
    async def create_flow(definition: FlowDefinition, actor: Actor) -> FlowRecord:
        if actor.role == UserRole.VIEWER:
            await deny(actor, "flow.create", "flow", None, hide_resource=False)
        flow = await service.create_flow(definition, actor.id)
        await audit(
            actor,
            "flow.create",
            "flow",
            flow.id,
            detail={"visibility": flow.visibility.value},
        )
        return flow

    @app.get("/api/v1/flows/{flow_id}", response_model=FlowRecord)
    async def get_flow(flow_id: str, actor: Actor) -> FlowRecord:
        flow = await service.storage.get_flow(flow_id)
        if flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        if not can_read(actor, flow.owner_id, flow.visibility):
            await deny(actor, "flow.read", "flow", flow_id)
        return flow

    @app.put("/api/v1/flows/{flow_id}", response_model=FlowRecord)
    async def update_flow(
        flow_id: str,
        definition: FlowDefinition,
        actor: Actor,
        expected_revision: Annotated[int | None, Query(alias="expectedRevision")] = None,
    ) -> FlowRecord:
        current = await service.storage.get_flow(flow_id)
        if current is None:
            raise HTTPException(status_code=404, detail="flow not found")
        if not can_manage(actor, current.owner_id):
            await deny(actor, "flow.update", "flow", flow_id)
        try:
            flow = await service.storage.update_flow(flow_id, definition, expected_revision)
        except RevisionConflict as error:
            raise HTTPException(
                status_code=409,
                detail={"message": str(error), "actualRevision": error.actual_revision},
            ) from error
        if flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        await audit(
            actor,
            "flow.update",
            "flow",
            flow_id,
            detail={"revision": flow.revision, "visibility": flow.visibility.value},
        )
        return flow

    @app.delete("/api/v1/flows/{flow_id}", status_code=204)
    async def delete_flow(flow_id: str, actor: Actor) -> None:
        flow = await service.storage.get_flow(flow_id)
        if flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        if not can_manage(actor, flow.owner_id):
            await deny(actor, "flow.delete", "flow", flow_id)
        try:
            removed = await service.storage.delete_flow(flow_id)
        except aiosqlite.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="flow has run history and cannot be deleted"
            ) from error
        if not removed:
            raise HTTPException(status_code=404, detail="flow not found")
        await audit(actor, "flow.delete", "flow", flow_id)

    @app.get("/api/v1/schedules", response_model=list[ScheduleRecord])
    async def list_schedules(actor: Actor) -> list[ScheduleRecord]:
        return [
            schedule
            for schedule in await service.storage.list_schedules()
            if can_read(actor, schedule.owner_id, schedule.visibility)
        ]

    @app.post("/api/v1/schedules", status_code=201, response_model=ScheduleRecord)
    async def create_schedule(
        definition: ScheduleDefinition, actor: Actor
    ) -> ScheduleRecord:
        flow = await service.storage.get_flow(definition.flow_id)
        if flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        if not can_run(actor, flow.owner_id, flow.visibility):
            await deny(actor, "schedule.create", "flow", flow.id)
        try:
            schedule = await service.create_schedule(definition, actor.id)
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        await audit(actor, "schedule.create", "schedule", schedule.id)
        return schedule

    @app.put("/api/v1/schedules/{schedule_id}", response_model=ScheduleRecord)
    async def update_schedule(
        schedule_id: str,
        definition: ScheduleDefinition,
        actor: Actor,
        expected_revision: Annotated[int | None, Query(alias="expectedRevision")] = None,
    ) -> ScheduleRecord:
        current = await service.storage.get_schedule(schedule_id)
        if current is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        if not can_manage_schedule(actor, current):
            await deny(actor, "schedule.update", "schedule", schedule_id)
        target_flow = await service.storage.get_flow(definition.flow_id)
        if target_flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        if not can_run(actor, target_flow.owner_id, target_flow.visibility):
            await deny(actor, "schedule.update", "flow", target_flow.id)
        try:
            schedule = await service.update_schedule(
                schedule_id, definition, expected_revision, actor.id
            )
        except RevisionConflict as error:
            raise HTTPException(
                status_code=409,
                detail={"message": str(error), "actualRevision": error.actual_revision},
            ) from error
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        await audit(actor, "schedule.update", "schedule", schedule_id)
        return schedule

    @app.delete("/api/v1/schedules/{schedule_id}", status_code=204)
    async def delete_schedule(schedule_id: str, actor: Actor) -> None:
        schedule = await service.storage.get_schedule(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        if not can_manage_schedule(actor, schedule):
            await deny(actor, "schedule.delete", "schedule", schedule_id)
        if not await service.storage.delete_schedule(schedule_id):
            raise HTTPException(status_code=404, detail="schedule not found")
        await audit(actor, "schedule.delete", "schedule", schedule_id)

    @app.post(
        "/api/v1/schedules/{schedule_id}/trigger",
        status_code=202,
        response_model=RunRecord,
    )
    async def trigger_schedule(schedule_id: str, actor: Actor) -> RunRecord:
        schedule = await service.storage.get_schedule(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        if not can_run(actor, schedule.owner_id, schedule.visibility):
            await deny(actor, "schedule.trigger", "schedule", schedule_id)
        try:
            run = await service.trigger_schedule(schedule_id, actor.id)
        except FlowDisabled as error:
            raise HTTPException(status_code=409, detail="flow is disabled") from error
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        await audit(
            actor,
            "schedule.trigger",
            "schedule",
            schedule_id,
            detail={"runId": run.id},
        )
        return run

    @app.post("/api/v1/runs", status_code=202, response_model=RunRecord)
    async def create_run(payload: RunCreate, actor: Actor) -> RunRecord:
        flow = await service.storage.get_flow(payload.flow_id)
        if flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        if not can_run(actor, flow.owner_id, flow.visibility):
            await deny(actor, "run.create", "flow", flow.id)
        try:
            run = await service.create_run(payload, actor.id)
        except FlowDisabled as error:
            raise HTTPException(status_code=409, detail="flow is disabled") from error
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        await audit(
            actor,
            "run.create",
            "run",
            run.id,
            detail={"flowId": flow.id},
        )
        return run

    @app.get("/api/v1/runs", response_model=list[RunRecord])
    async def list_runs(
        actor: Actor, limit: Annotated[int, Query(ge=1, le=500)] = 100
    ) -> list[RunRecord]:
        return [
            run
            for run in await service.storage.list_runs(limit)
            if can_read(actor, run.owner_id, run.visibility)
        ]

    async def accessible_run(run_id: str, actor: Principal, action: str) -> RunRecord:
        run = await service.storage.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if not can_read(actor, run.owner_id, run.visibility):
            await deny(actor, action, "run", run_id)
        return run

    @app.get("/api/v1/runs/{run_id}", response_model=RunRecord)
    async def get_run(run_id: str, actor: Actor) -> RunRecord:
        return await accessible_run(run_id, actor, "run.read")

    @app.get("/api/v1/runs/{run_id}/flow", response_model=RunFlowSnapshot)
    async def get_run_flow(run_id: str, actor: Actor) -> RunFlowSnapshot:
        await accessible_run(run_id, actor, "run.flow.read")
        snapshot = await service.storage.get_run_flow_snapshot(run_id)
        if snapshot is None:
            raise HTTPException(status_code=409, detail="run flow snapshot is unavailable")
        return snapshot

    @app.post("/api/v1/runs/{run_id}/cancel", response_model=RunRecord)
    async def cancel_run(run_id: str, actor: Actor) -> RunRecord:
        run = await service.storage.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if not can_run(actor, run.owner_id, run.visibility):
            await deny(actor, "run.cancel", "run", run_id)
        updated = await service.cancel_run(run_id)
        await audit(actor, "run.cancel", "run", run_id)
        return updated

    @app.get("/api/v1/runs/{run_id}/items", response_model=ItemPage)
    async def list_items(
        run_id: str,
        actor: Actor,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> ItemPage:
        await accessible_run(run_id, actor, "run.items.read")
        items, next_cursor = await service.storage.list_items(run_id, cursor, limit)
        return ItemPage(items=items, next_cursor=next_cursor)

    @app.get("/api/v1/runs/{run_id}/events", response_model=list[EventRecord])
    async def list_events(
        run_id: str,
        actor: Actor,
        after: Annotated[int, Query(ge=0)] = 0,
    ) -> list[EventRecord]:
        await accessible_run(run_id, actor, "run.events.read")
        return await service.storage.list_events(run_id, after)

    @app.get("/api/v1/runs/{run_id}/events/stream")
    async def stream_events(
        request: Request,
        run_id: str,
        actor: Actor,
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        await accessible_run(run_id, actor, "run.events.stream")
        start_after = after
        if last_event_id is not None:
            try:
                parsed_last_event_id = int(last_event_id)
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail="Last-Event-ID must be a non-negative integer",
                ) from error
            if parsed_last_event_id < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Last-Event-ID must be a non-negative integer",
                )
            start_after = max(start_after, parsed_last_event_id)

        async def stream():
            async for event in service.subscribe(run_id, start_after):
                if await request.is_disconnected():
                    break
                if event is None:
                    yield ": keep-alive\n\n"
                    continue
                payload = event.model_dump(mode="json")
                yield (
                    f"id: {event.sequence}\n"
                    f"event: {event.type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
