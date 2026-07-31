from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Annotated

import aiosqlite
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from siftlane_connector_sdk import (
    ConnectorManifest,
    ConnectorOperationRequest,
    ConnectorOperationResult,
)

from . import __version__
from .config import Settings
from .connectors import CONNECTOR_ENTRYPOINT_GROUP, ConnectorRegistry
from .engine import node_capabilities
from .models import (
    EventRecord,
    FlowDefinition,
    FlowRecord,
    ItemPage,
    RunCreate,
    RunFlowSnapshot,
    RunRecord,
    ScheduleDefinition,
    ScheduleRecord,
)
from .service import CrawlerService, FlowDisabled, InvalidParameters
from .storage import RevisionConflict


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings()
    service = CrawlerService(configured)
    connectors = ConnectorRegistry.discover()

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
    if configured.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=configured.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        )

    async def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if not configured.api_token:
            return
        if authorization != f"Bearer {configured.api_token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    protected = [Depends(authorize)]

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "UP",
            "version": __version__,
            "workers": configured.worker_count,
            "queuedRuns": service.queue_size,
            "database": str(configured.database_path),
        }

    @app.get("/api/v1/capabilities", dependencies=protected)
    async def capabilities():
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
            },
            "connectorCount": len(connectors.manifests()),
        }

    @app.get(
        "/api/v1/connectors",
        dependencies=protected,
        response_model=list[ConnectorManifest],
    )
    async def list_connectors() -> list[ConnectorManifest]:
        return connectors.manifests()

    @app.get("/api/v1/connector-contract", dependencies=protected)
    async def connector_contract() -> dict[str, object]:
        return {
            "apiVersion": "siftlane.connector/v1",
            "entryPointGroup": CONNECTOR_ENTRYPOINT_GROUP,
            "schemas": {
                "manifest": ConnectorManifest.model_json_schema(),
                "operationRequest": ConnectorOperationRequest.model_json_schema(),
                "operationResult": ConnectorOperationResult.model_json_schema(),
            },
        }

    @app.get("/api/v1/flows", dependencies=protected)
    async def list_flows() -> list[FlowRecord]:
        return await service.storage.list_flows()

    @app.post("/api/v1/flows", status_code=201, dependencies=protected)
    async def create_flow(definition: FlowDefinition) -> FlowRecord:
        return await service.create_flow(definition)

    @app.get("/api/v1/flows/{flow_id}", dependencies=protected)
    async def get_flow(flow_id: str) -> FlowRecord:
        flow = await service.storage.get_flow(flow_id)
        if flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        return flow

    @app.put("/api/v1/flows/{flow_id}", dependencies=protected)
    async def update_flow(
        flow_id: str,
        definition: FlowDefinition,
        expected_revision: Annotated[int | None, Query(alias="expectedRevision")] = None,
    ) -> FlowRecord:
        try:
            flow = await service.storage.update_flow(
                flow_id, definition, expected_revision
            )
        except RevisionConflict as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(error),
                    "actualRevision": error.actual_revision,
                },
            ) from error
        if flow is None:
            raise HTTPException(status_code=404, detail="flow not found")
        return flow

    @app.delete("/api/v1/flows/{flow_id}", status_code=204, dependencies=protected)
    async def delete_flow(flow_id: str):
        try:
            removed = await service.storage.delete_flow(flow_id)
        except aiosqlite.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="flow has run history and cannot be deleted"
            ) from error
        if not removed:
            raise HTTPException(status_code=404, detail="flow not found")

    @app.get(
        "/api/v1/schedules",
        dependencies=protected,
        response_model=list[ScheduleRecord],
    )
    async def list_schedules() -> list[ScheduleRecord]:
        return await service.storage.list_schedules()

    @app.post(
        "/api/v1/schedules",
        status_code=201,
        dependencies=protected,
        response_model=ScheduleRecord,
    )
    async def create_schedule(definition: ScheduleDefinition) -> ScheduleRecord:
        try:
            return await service.create_schedule(definition)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="flow not found") from error
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.put(
        "/api/v1/schedules/{schedule_id}",
        dependencies=protected,
        response_model=ScheduleRecord,
    )
    async def update_schedule(
        schedule_id: str,
        definition: ScheduleDefinition,
        expected_revision: Annotated[int | None, Query(alias="expectedRevision")] = None,
    ) -> ScheduleRecord:
        try:
            schedule = await service.update_schedule(
                schedule_id, definition, expected_revision
            )
        except RevisionConflict as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(error),
                    "actualRevision": error.actual_revision,
                },
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="flow not found") from error
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        return schedule

    @app.delete(
        "/api/v1/schedules/{schedule_id}",
        status_code=204,
        dependencies=protected,
    )
    async def delete_schedule(schedule_id: str):
        if not await service.storage.delete_schedule(schedule_id):
            raise HTTPException(status_code=404, detail="schedule not found")

    @app.post(
        "/api/v1/schedules/{schedule_id}/trigger",
        status_code=202,
        dependencies=protected,
        response_model=RunRecord,
    )
    async def trigger_schedule(schedule_id: str) -> RunRecord:
        try:
            return await service.trigger_schedule(schedule_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="schedule not found") from error
        except FlowDisabled as error:
            raise HTTPException(status_code=409, detail="flow is disabled") from error
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/v1/runs", status_code=202, dependencies=protected)
    async def create_run(request: RunCreate) -> RunRecord:
        try:
            return await service.create_run(request)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="flow not found") from error
        except FlowDisabled as error:
            raise HTTPException(status_code=409, detail="flow is disabled") from error
        except InvalidParameters as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v1/runs", dependencies=protected)
    async def list_runs(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[RunRecord]:
        return await service.storage.list_runs(limit)

    @app.get("/api/v1/runs/{run_id}", dependencies=protected)
    async def get_run(run_id: str) -> RunRecord:
        run = await service.storage.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.get("/api/v1/runs/{run_id}/flow", dependencies=protected)
    async def get_run_flow(run_id: str) -> RunFlowSnapshot:
        snapshot = await service.storage.get_run_flow_snapshot(run_id)
        if snapshot is None:
            if await service.storage.get_run(run_id) is None:
                raise HTTPException(status_code=404, detail="run not found")
            raise HTTPException(status_code=409, detail="run flow snapshot is unavailable")
        return snapshot

    @app.post("/api/v1/runs/{run_id}/cancel", dependencies=protected)
    async def cancel_run(run_id: str) -> RunRecord:
        try:
            return await service.cancel_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="run not found") from error

    @app.get("/api/v1/runs/{run_id}/items", dependencies=protected)
    async def list_items(
        run_id: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> ItemPage:
        if await service.storage.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        items, next_cursor = await service.storage.list_items(run_id, cursor, limit)
        return ItemPage(items=items, next_cursor=next_cursor)

    @app.get("/api/v1/runs/{run_id}/events", dependencies=protected)
    async def list_events(
        run_id: str, after: Annotated[int, Query(ge=0)] = 0
    ) -> list[EventRecord]:
        if await service.storage.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        return await service.storage.list_events(run_id, after)

    @app.get("/api/v1/runs/{run_id}/events/stream", dependencies=protected)
    async def stream_events(
        request: Request,
        run_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if await service.storage.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")

        start_after = after
        if last_event_id is not None:
            try:
                parsed_last_event_id = int(last_event_id)
            except ValueError as error:
                raise HTTPException(
                    status_code=400, detail="Last-Event-ID must be a non-negative integer"
                ) from error
            if parsed_last_event_id < 0:
                raise HTTPException(
                    status_code=400, detail="Last-Event-ID must be a non-negative integer"
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
