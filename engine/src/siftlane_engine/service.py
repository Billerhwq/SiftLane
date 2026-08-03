from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

from croniter import croniter
from jsonschema import ValidationError, validate
from bs4 import BeautifulSoup

from .auth import hash_password
from .config import Settings
from .engine import FlowEngine, RunCancelled
from .integrations import ConnectorManager, DeliveryService, IntegrationStorage
from .models import (
    EventRecord,
    FlowDefinition,
    FlowRecord,
    FieldBinding,
    ImportPreviewItem,
    ImportEventRecord,
    ImportStatus,
    RunCreate,
    RunRecord,
    RunStatus,
    ScheduleDefinition,
    ScheduleRecord,
    UserRole,
    WebsiteImportCreate,
    WebsiteImportRecord,
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
        self._import_subscribers: dict[str, set[asyncio.Queue[ImportEventRecord]]] = defaultdict(set)
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

    async def create_website_import(self, definition: WebsiteImportCreate, owner_id: str) -> WebsiteImportRecord:
        record = await self.storage.create_website_import(definition, owner_id)
        await self._write_import_event(record.id, "import.created", "info", "Import job created", {"sourceUrl": record.source_url})
        return record

    async def probe_website_import(self, import_id: str) -> WebsiteImportRecord:
        record = await self.storage.get_website_import(import_id)
        if record is None: raise KeyError(import_id)
        record = await self.storage.update_website_import(import_id, status=ImportStatus.PROBING)
        assert record is not None
        await self._write_import_event(import_id, "probe.started", "info", "Probe started", {})
        try:
            response = await self.http.fetch(record.source_url)
        except Exception as error:
            await self._write_import_event(import_id, "import.failed", "error", "Network policy rejected the target", {"code":"NETWORK_POLICY"})
            return (await self.storage.update_website_import(import_id, status=ImportStatus.UNSUPPORTED, error_code="NETWORK_POLICY", error_message=str(error)))  # type: ignore[return-value]
        media = response.media_type
        if media in {"application/json", "application/ld+json"} or response.text().lstrip().startswith(("{", "[")):
            report = {"strategy":"http_json","canonical_url":response.url,"allowed_domains":[response.url.split("/")[2]],"page_kind":"api","content_type":media,"requires_auth":response.status in {401,403},"robots_allowed":True,"confidence":0.9,"field_candidates":[]}
        elif media in {"text/html", "application/xhtml+xml"}:
            soup = BeautifulSoup(response.text(), "html.parser")
            articles = soup.select("article")
            report = {"strategy":"http_html","canonical_url":response.url,"allowed_domains":[response.url.split("/")[2]],"page_kind":"listing" if len(articles) >= 2 else "detail","content_type":media,"requires_auth":response.status in {401,403},"robots_allowed":True,"confidence":0.86 if articles else 0.6,"list_candidates":["article"] if articles else [],"field_candidates":[]}
        else:
            return (await self.storage.update_website_import(import_id, status=ImportStatus.UNSUPPORTED, error_code="UNSUPPORTED_CONTENT_TYPE", error_message=f"unsupported content type: {media}"))  # type: ignore[return-value]
        status = ImportStatus.NEEDS_INPUT if report["requires_auth"] else ImportStatus.PROBE_READY
        await self._write_import_event(import_id, "probe.completed", "success", "Probe completed", {"strategy":report["strategy"]})
        return (await self.storage.update_website_import(import_id, status=status, probe_revision=record.probe_revision + 1, probe_report_json=report))  # type: ignore[return-value]

    async def compile_website_import(self, import_id: str) -> WebsiteImportRecord:
        record = await self.storage.get_website_import(import_id)
        if record is None: raise KeyError(import_id)
        if record.status != ImportStatus.PROBE_READY: raise ValueError("probe must complete before compile")
        await self._write_import_event(import_id, "compile.started", "info", "Compiling flow draft", {})
        report = record.probe_report_json or {}; strategy = report.get("strategy")
        if strategy not in {"http_html", "http_json"}: raise ValueError("selected strategy requires a dedicated runtime")
        field_names = record.intent.fields
        is_json = strategy == "http_json"
        bindings = [FieldBinding(field=name, selector=(name if is_json else {"title":"h1, h2, h3", "url":"a[href]", "content":"p", "author":".author, .byline", "published_at":"time"}.get(name, f"[data-field='{name}']")), attribute="href" if name == "url" else "text", required=name in {"title", "content", "url"}, confidence=.9, evidence=[]).model_dump() for name in field_names]
        extract_type = "json_extract" if is_json else "html_extract"
        extract_config = {"items_path":"data.items", "fields":{b["field"]:{"path":b["selector"]} for b in bindings}, "deduplicate_by":"url"} if is_json else {"item_selector":"article" if report.get("page_kind") == "listing" else "body", "fields":{b["field"]:{"selector":b["selector"],"attribute":b["attribute"]} for b in bindings}, "deduplicate_by":"url"}
        definition = FlowDefinition(name=f"Import: {record.source_url}", description=record.intent.description, max_items=100, timeout_seconds=300, nodes=[
            {"id":"start","type":"start","name":"Start","x":0,"y":0,"config":{"urls":[record.source_url]}},
            {"id":"request","type":"http_request","name":"Fetch source","x":220,"y":0,"config":{"url":"{{url}}","respect_robots":True}},
            {"id":"extract","type":extract_type,"name":"Extract records","x":440,"y":0,"config":extract_config},
            {"id":"emit","type":"emit","name":"Preview output","x":660,"y":0,"config":{"fields":{}}},
        ], edges=[{"id":"start-request","source":"start","target":"request"},{"id":"request-extract","source":"request","target":"extract"},{"id":"extract-emit","source":"extract","target":"emit"}])
        draft = {"definition":definition.model_dump(mode="json"),"field_bindings":bindings,"assumptions":["Preview is bounded to two pages and ten items"],"warnings":[],"compiler_version":"website-compiler/v1","probe_artifact_id":f"probe-{record.probe_revision}"}
        await self._write_import_event(import_id, "compile.completed", "success", "Flow draft is ready", {"compilerVersion":"website-compiler/v1"})
        return (await self.storage.update_website_import(import_id, status=ImportStatus.DRAFT_READY, draft_revision=record.draft_revision + 1, flow_draft_json=draft))  # type: ignore[return-value]

    async def preview_website_import(self, import_id: str) -> list[ImportPreviewItem]:
        record = await self.storage.get_website_import(import_id)
        if record is None: raise KeyError(import_id)
        if record.status not in {ImportStatus.DRAFT_READY, ImportStatus.PREVIEW_READY}: raise ValueError("draft must complete before preview")
        await self._write_import_event(import_id, "preview.started", "info", "Preview started", {"maxItems":10})
        response = await self.http.fetch(record.source_url)
        draft = record.flow_draft_json or {}; bindings = draft.get("field_bindings", []); rows: list[dict[str, Any]] = []
        if (record.probe_report_json or {}).get("strategy") == "http_json":
            payload = json.loads(response.text()); source_rows = payload.get("data", {}).get("items", payload if isinstance(payload, list) else [])
            for item in source_rows[:10]: rows.append({"external_id":str(item.get("url") or item.get("id") or hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()),"normalized_json":{b["field"]:item.get(b["selector"], "") for b in bindings},"field_evidence_json":{},"quality_json":{"required_missing":[]}})
        else:
            soup = BeautifulSoup(response.text(), "html.parser"); targets = soup.select("article") or [soup]
            for target in targets[:10]:
                values = {}; evidence = {}
                for binding in bindings:
                    element = target.select_one(binding["selector"]); value = ""
                    if element: value = element.get(binding["attribute"], "") if binding["attribute"] != "text" else element.get_text(" ", strip=True)
                    values[binding["field"]] = value; evidence[binding["field"]] = {"selector":binding["selector"],"sample":value[:200]}
                external = values.get("url") or hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest(); rows.append({"external_id":str(external),"normalized_json":values,"field_evidence_json":evidence,"quality_json":{"required_missing":[b["field"] for b in bindings if b["required"] and not values.get(b["field"])]}})
        items = await self.storage.replace_preview_items(import_id, record.draft_revision, rows)
        await self.storage.update_website_import(import_id, status=ImportStatus.PREVIEW_READY, preview_revision=record.preview_revision + 1)
        await self._write_import_event(import_id, "preview.completed", "success", "Preview completed", {"itemCount":len(items)})
        return items

    async def confirm_website_import(self, import_id: str, owner_id: str, idempotency_key: str) -> WebsiteImportRecord:
        record = await self.storage.get_website_import(import_id)
        if record is None: raise KeyError(import_id)
        definition = FlowDefinition.model_validate((record.flow_draft_json or {})["definition"])
        updated = await self.storage.confirm_website_import(import_id, definition, owner_id, idempotency_key)
        if updated is None: raise KeyError(import_id)
        if updated.status == ImportStatus.CREATED:
            await self._write_import_event(import_id, "import.confirmed", "success", "Formal flow created", {"flowId":updated.created_flow_id})
        return updated

    async def subscribe_import(self, import_id: str, after: int = 0) -> AsyncIterator[ImportEventRecord | None]:
        queue: asyncio.Queue[ImportEventRecord] = asyncio.Queue(maxsize=200); self._import_subscribers[import_id].add(queue)
        try:
            for event in await self.storage.list_import_events(import_id, after):
                yield event; after = event.sequence
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=self.settings.sse_heartbeat_seconds)
                    if event.sequence > after: yield event; after = event.sequence
                except asyncio.TimeoutError:
                    yield None
        finally: self._import_subscribers[import_id].discard(queue)

    async def _write_import_event(self, import_id: str, event_type: str, level: str, message: str, data: dict[str, Any]) -> None:
        event = await self.storage.add_import_event(import_id,event_type,level,message,data)
        for queue in tuple(self._import_subscribers.get(import_id, ())):
            if queue.full():
                with suppress(asyncio.QueueEmpty): queue.get_nowait()
            queue.put_nowait(event)

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
