from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

from croniter import croniter
from jsonschema import ValidationError, validate

from .auth import hash_password
from .config import Settings
from .engine import FlowEngine, RunCancelled
from .integrations import ConnectorManager, DeliveryService, IntegrationStorage
from .models import (
    EventRecord,
    FlowDefinition,
    FlowRecord,
    RunCreate,
    RunRecord,
    RunStatus,
    ScheduleDefinition,
    ScheduleRecord,
    UserRole,
    utc_now,
)
from .security import SecureHttpClient
from .storage import Storage


class CrawlerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage = Storage(settings.database_path)
        self.http = SecureHttpClient(settings)
        self.engine = FlowEngine(self.storage, self.http)
        self.integrations = IntegrationStorage(settings)
        self.connector_manager = ConnectorManager(settings, self.integrations)
        self.delivery = DeliveryService(settings, self.integrations, self.storage)
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._scheduler: asyncio.Task[None] | None = None
        self._scheduler_owner = f"scheduler-{uuid.uuid4()}"
        self._cancelled: dict[str, asyncio.Event] = {}
        self._subscribers: dict[str, set[asyncio.Queue[EventRecord]]] = defaultdict(set)
        self.ready = False

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        self.ready = False
        await self.storage.initialize()
        await self.integrations.initialize()
        if self.settings.auth_mode == "team" and await self.storage.count_team_users() == 0:
            bootstrap_password = self.settings.bootstrap_admin_password.get_secret_value()
            if not bootstrap_password:
                raise RuntimeError(
                    "team auth requires a bootstrap admin password when no team users exist"
                )
            admin = await self.storage.create_user(
                username=self.settings.bootstrap_admin_username.lower(),
                display_name="Siftlane administrator",
                password_hash=hash_password(bootstrap_password),
                role=UserRole.ADMIN,
            )
            await self.storage.add_audit(
                actor_user_id=admin.id,
                actor_username=admin.username,
                action="user.bootstrap",
                resource_type="user",
                resource_id=admin.id,
                outcome="success",
                detail={"role": admin.role.value},
            )
        recovery = await self.storage.recover_runs()
        for run_id in recovery.recovered:
            await self._write_event(
                run_id,
                "run.recovered",
                "warning",
                "Run requeued after engine restart",
                {},
            )
        for run_id in recovery.cancelled:
            await self._write_event(
                run_id,
                "run.cancelled",
                "warning",
                "Run cancelled while engine was restarting",
                {"reason": "engine_restart"},
            )
        for run_id in recovery.requeued:
            await self._queue.put(run_id)
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"crawler-worker-{index}")
            for index in range(self.settings.worker_count)
        ]
        self._scheduler = asyncio.create_task(
            self._scheduler_loop(), name="crawler-scheduler"
        )
        await self.delivery.start()
        self.ready = True

    async def stop(self) -> None:
        self.ready = False
        await self.delivery.stop()
        if self._scheduler is not None:
            self._scheduler.cancel()
            with suppress(asyncio.CancelledError):
                await self._scheduler
            self._scheduler = None
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            with suppress(asyncio.CancelledError):
                await task
        await self.http.close()

    async def create_flow(
        self, definition: FlowDefinition, owner_id: str = "local-operator"
    ) -> FlowRecord:
        return await self.storage.create_flow(definition, owner_id)

    async def create_schedule(
        self, definition: ScheduleDefinition, created_by: str = "local-operator"
    ) -> ScheduleRecord:
        flow = await self._validate_schedule(definition)
        next_run = self._next_occurrence(definition, utc_now()) if definition.enabled else None
        return await self.storage.create_schedule(
            definition,
            next_run,
            owner_id=flow.owner_id,
            visibility=flow.visibility,
            created_by=created_by,
        )

    async def update_schedule(
        self,
        schedule_id: str,
        definition: ScheduleDefinition,
        expected_revision: int | None,
        created_by: str = "local-operator",
    ) -> ScheduleRecord | None:
        flow = await self._validate_schedule(definition)
        next_run = self._next_occurrence(definition, utc_now()) if definition.enabled else None
        return await self.storage.update_schedule(
            schedule_id,
            definition,
            expected_revision,
            next_run,
            owner_id=flow.owner_id,
            visibility=flow.visibility,
        )

    async def trigger_schedule(
        self, schedule_id: str, created_by: str = "local-operator"
    ) -> RunRecord:
        schedule = await self.storage.get_schedule(schedule_id)
        if schedule is None:
            raise KeyError(schedule_id)
        run = await self.create_run(
            RunCreate(
                flow_id=schedule.flow_id,
                parameters=schedule.parameters,
                idempotency_key=f"schedule:{schedule.id}:manual:{uuid.uuid4()}",
            ),
            created_by=created_by,
        )
        await self.storage.record_manual_schedule_run(schedule.id, run.id)
        return run

    async def create_run(
        self, request: RunCreate, created_by: str = "local-operator"
    ) -> RunRecord:
        flow = await self.storage.get_flow(request.flow_id)
        if flow is None:
            raise KeyError(request.flow_id)
        if not flow.enabled:
            raise FlowDisabled(flow.id)
        try:
            validate(instance=request.parameters, schema=flow.parameter_schema)
        except ValidationError as error:
            raise InvalidParameters(error.message) from error
        run, created = await self.storage.create_run(
            flow, request.parameters, request.idempotency_key, created_by
        )
        if created:
            await self._write_event(
                run.id,
                "run.queued",
                "info",
                "Run queued",
                {"flowId": flow.id, "flowName": flow.name},
            )
            await self._queue.put(run.id)
        return run

    async def cancel_run(self, run_id: str) -> RunRecord:
        run = await self.storage.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status.terminal:
            return run
        event = self._cancelled.setdefault(run_id, asyncio.Event())
        event.set()
        if run.status == RunStatus.QUEUED:
            updated, terminal_event = await self.storage.finalize_run(
                run_id,
                status=RunStatus.CANCELLED,
                run_message="Cancelled before execution",
                event_type="run.cancelled",
                event_level="warning",
                event_message="Run cancelled before execution",
                event_data={"reason": "cancelled_before_execution"},
            )
            self._publish_event(terminal_event)
        else:
            if run.status == RunStatus.CANCELLING:
                return run
            updated = await self.storage.update_run(
                run_id, status=RunStatus.CANCELLING, message="Cancellation requested"
            )
            await self._write_event(
                run_id, "run.cancelling", "warning", "Cancellation requested", {}
            )
        return updated

    async def subscribe(
        self, run_id: str, after: int = 0
    ) -> AsyncIterator[EventRecord | None]:
        queue: asyncio.Queue[EventRecord] = asyncio.Queue(maxsize=200)
        self._subscribers[run_id].add(queue)
        try:
            terminal_events = {"run.completed", "run.failed", "run.cancelled"}
            for event in await self.storage.list_events(run_id, after):
                if event.sequence > after:
                    yield event
                    after = event.sequence
                if event.type in terminal_events:
                    return
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=self.settings.sse_heartbeat_seconds
                    )
                    if event.sequence > after + 1:
                        for missed in await self.storage.list_events(run_id, after):
                            if missed.sequence > after:
                                yield missed
                                after = missed.sequence
                            if missed.type in terminal_events:
                                return
                    if event.sequence > after:
                        yield event
                        after = event.sequence
                    if event.type in terminal_events:
                        return
                except asyncio.TimeoutError:
                    run = await self.storage.get_run(run_id)
                    if run is None or run.status.terminal:
                        for event in await self.storage.list_events(run_id, after):
                            if event.sequence > after:
                                yield event
                                after = event.sequence
                        return
                    yield None
        finally:
            self._subscribers[run_id].discard(queue)

    async def _worker(self, index: int) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                await self._execute(run_id, index)
            finally:
                self._queue.task_done()

    async def _scheduler_loop(self) -> None:
        while True:
            try:
                now = utc_now()
                schedules = await self.storage.claim_due_schedules(
                    self._scheduler_owner,
                    now,
                    lease_seconds=self.settings.scheduler_lease_seconds,
                )
                for schedule in schedules:
                    await self._fire_schedule(schedule)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient scheduler/database error is retried on the next poll.
                pass
            await asyncio.sleep(self.settings.scheduler_poll_seconds)

    async def _fire_schedule(self, schedule: ScheduleRecord) -> None:
        fired_at = schedule.next_run_at or utc_now()
        next_run = self._next_occurrence(schedule, fired_at)
        run_id: str | None = None
        error_message: str | None = None
        try:
            run = await self.create_run(
                RunCreate(
                    flow_id=schedule.flow_id,
                    parameters=schedule.parameters,
                    idempotency_key=f"schedule:{schedule.id}:{fired_at.astimezone(timezone.utc).isoformat()}",
                ),
                created_by="scheduler",
            )
            run_id = run.id
        except Exception as error:
            error_message = (str(error) or type(error).__name__)[:1000]
        await self.storage.complete_schedule_fire(
            schedule.id,
            self._scheduler_owner,
            fired_at=fired_at,
            next_run_at=next_run,
            last_run_id=run_id,
            last_error=error_message,
        )
        await self.storage.add_audit(
            actor_user_id=None,
            actor_username="scheduler",
            action="schedule.fire",
            resource_type="schedule",
            resource_id=schedule.id,
            outcome="success" if error_message is None else "failed",
            detail={"runId": run_id, "error": error_message},
        )

    async def _validate_schedule(self, definition: ScheduleDefinition) -> FlowRecord:
        flow = await self.storage.get_flow(definition.flow_id)
        if flow is None:
            raise KeyError(definition.flow_id)
        try:
            validate(instance=definition.parameters, schema=flow.parameter_schema)
        except ValidationError as error:
            raise InvalidParameters(error.message) from error
        return flow

    @staticmethod
    def _next_occurrence(
        definition: ScheduleDefinition | ScheduleRecord, after: datetime
    ) -> datetime:
        local_after = after.astimezone(ZoneInfo(definition.timezone))
        occurrence = croniter(definition.cron, local_after).get_next(datetime)
        if occurrence.tzinfo is None:
            occurrence = occurrence.replace(tzinfo=ZoneInfo(definition.timezone))
        return occurrence.astimezone(timezone.utc)

    async def _execute(self, run_id: str, worker_index: int) -> None:
        run = await self.storage.claim_run(
            run_id, worker_index=worker_index, started_at=utc_now()
        )
        if run is None:
            return
        flow = await self.storage.get_run_flow(run_id)
        if flow is None:
            await self._fail(
                run_id,
                "FLOW_SNAPSHOT_NOT_FOUND",
                "Run flow snapshot is missing",
            )
            return
        cancelled = self._cancelled.setdefault(run_id, asyncio.Event())
        await self._write_event(
            run_id,
            "run.started",
            "info",
            "Run started",
            {"worker": worker_index + 1},
        )

        async def event(
            event_type: str, level: str, message: str, data: dict[str, Any]
        ) -> None:
            await self._write_event(run_id, event_type, level, message, data)

        async def progress(node_id: str, message: str, processed: int) -> None:
            await self.storage.update_run(
                run_id,
                current_node=node_id,
                message=message,
                processed_items=processed,
            )

        try:
            async with asyncio.timeout(flow.timeout_seconds):
                await self.engine.execute(
                    run_id, flow, run.parameters, cancelled, event, progress
                )
            emitted = await self.storage.count_items(run_id)
            _, terminal_event = await self.storage.finalize_run(
                run_id,
                status=RunStatus.SUCCEEDED,
                run_message=f"Completed with {emitted} item(s)",
                processed_items=emitted,
                total_items=emitted,
                event_type="run.completed",
                event_level="success",
                event_message=f"Run completed with {emitted} item(s)",
                event_data={"itemCount": emitted},
            )
            self._publish_event(terminal_event)
        except RunCancelled:
            _, terminal_event = await self.storage.finalize_run(
                run_id,
                status=RunStatus.CANCELLED,
                run_message="Run cancelled",
                event_type="run.cancelled",
                event_level="warning",
                event_message="Run cancelled",
            )
            self._publish_event(terminal_event)
        except TimeoutError:
            await self._fail(
                run_id,
                "RUN_TIMEOUT",
                f"Run exceeded its {flow.timeout_seconds} second timeout",
            )
        except Exception as error:
            await self._fail(run_id, type(error).__name__.upper(), str(error))
        finally:
            self._cancelled.pop(run_id, None)

    async def _fail(self, run_id: str, code: str, message: str) -> None:
        safe_message = message[:2000] or "Crawler execution failed"
        _, terminal_event = await self.storage.finalize_run(
            run_id,
            status=RunStatus.FAILED,
            run_message="Run failed",
            error_code=code[:120],
            error_message=safe_message,
            event_type="run.failed",
            event_level="error",
            event_message=safe_message,
            event_data={"errorCode": code[:120]},
        )
        self._publish_event(terminal_event)

    async def _write_event(
        self,
        run_id: str,
        event_type: str,
        level: str,
        message: str,
        data: dict[str, Any],
    ) -> None:
        event = await self.storage.add_event(
            run_id, event_type, level, message, data
        )
        self._publish_event(event)

    def _publish_event(self, event: EventRecord) -> None:
        for queue in tuple(self._subscribers.get(event.run_id, ())):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)


class FlowDisabled(RuntimeError):
    pass


class InvalidParameters(ValueError):
    pass
