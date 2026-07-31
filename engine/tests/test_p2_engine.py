from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from siftlane_engine.config import Settings
from siftlane_engine.engine import FlowEngine, HttpStatusError
from siftlane_engine.models import FlowDefinition, RunStatus, ScheduleDefinition, utc_now
from siftlane_engine.service import CrawlerService
from siftlane_engine.storage import Storage


@dataclass
class FakeResponse:
    status: int
    url: str
    media_type: str = "text/plain"
    headers: dict[str, str] | None = None

    def text(self) -> str:
        return "ok"


class FakeHttp:
    def __init__(self, statuses: list[int] | None = None):
        self.statuses = list(statuses or [200])
        self.calls = 0

    async def fetch(self, url: str, **_: Any) -> FakeResponse:
        index = min(self.calls, len(self.statuses) - 1)
        self.calls += 1
        return FakeResponse(self.statuses[index], url, headers={})


def node(node_id: str, node_type: str, config: dict[str, Any], **extra: Any):
    return {
        "id": node_id,
        "type": node_type,
        "name": node_id.title(),
        "config": config,
        **extra,
    }


async def execute(tmp_path, definition: dict[str, Any], http: FakeHttp | None = None):
    storage = Storage(tmp_path / "crawler.db")
    await storage.initialize()
    flow_data = {key: value for key, value in definition.items() if key != "parameters"}
    flow = await storage.create_flow(FlowDefinition.model_validate(flow_data))
    run, _ = await storage.create_run(flow, definition.get("parameters", {}), None)
    await storage.update_run(run.id, status=RunStatus.RUNNING)
    events: list[tuple[str, dict[str, Any]]] = []

    async def event(event_type: str, _level: str, _message: str, data: dict[str, Any]):
        events.append((event_type, data))

    async def progress(_node: str, _message: str, _processed: int):
        return None

    engine = FlowEngine(storage, http or FakeHttp())
    count = await engine.execute(
        run.id, flow, definition.get("parameters", {}), asyncio.Event(), event, progress
    )
    return storage, run.id, count, events


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "expected_port"), [("news", "true"), ("other", "false")])
async def test_condition_routes_true_and_false_ports(tmp_path, kind, expected_port):
    definition = {
        "name": "Branch",
        "parameters": {"kind": kind},
        "nodes": [
            node("start", "start", {"urls": ["https://example.com/item"]}),
            node("branch", "condition", {"field": "kind", "operator": "eq", "value": "news"}),
            node("emit", "emit", {}),
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "branch"},
            {"id": "b", "source": "branch", "source_port": "true", "target": "emit"},
            {"id": "c", "source": "branch", "source_port": "false", "target": "emit"},
        ],
    }
    storage, run_id, count, _ = await execute(tmp_path, definition)
    checkpoints = await storage.load_checkpoints(run_id)
    assert count == 1
    assert len(checkpoints["branch"].outputs[expected_port]) == 1
    assert len(checkpoints["branch"].outputs[{"true": "false", "false": "true"}[expected_port]]) == 0


@pytest.mark.asyncio
async def test_loop_and_pagination_are_bounded(tmp_path):
    loop_flow = {
        "name": "Loop",
        "max_items": 20,
        "parameters": {"records": ["a", "b", "c", "d"]},
        "nodes": [
            node("start", "start", {"urls": ["https://example.com/root"]}),
            node("loop", "loop", {"items_path": "records", "item_name": "row", "index_name": "row_index", "max_iterations": 2}),
            node("emit", "emit", {}),
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "loop"},
            {"id": "b", "source": "loop", "target": "emit"},
        ],
    }
    storage, run_id, _, _ = await execute(tmp_path / "loop", loop_flow)
    loop_output = (await storage.load_checkpoints(run_id))["loop"].outputs["default"]
    assert [item["row"] for item in loop_output] == ["a", "b"]
    assert [item["row_index"] for item in loop_output] == [0, 1]

    pagination_flow = {
        "name": "Pagination",
        "max_items": 3,
        "nodes": [
            node("start", "start", {"urls": ["https://example.com/search?q=sift"]}),
            node("pages", "pagination", {"url": "{{url}}", "page_parameter": "page", "start_page": 4, "max_pages": 9}),
            node("emit", "emit", {}),
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "pages"},
            {"id": "b", "source": "pages", "target": "emit"},
        ],
    }
    storage, run_id, count, _ = await execute(tmp_path / "pages", pagination_flow)
    pages = (await storage.load_checkpoints(run_id))["pages"].outputs["default"]
    assert count == 3
    assert [item["page"] for item in pages] == [4, 5, 6]
    assert pages[0]["url"] == "https://example.com/search?q=sift&page=4"


@pytest.mark.asyncio
async def test_retry_succeeds_and_exhausts(tmp_path):
    definition = {
        "name": "Retry",
        "nodes": [
            node("start", "start", {"urls": ["https://example.com/item"]}),
            node(
                "request",
                "http_request",
                {"url": "{{url}}"},
                retry={"max_attempts": 2, "backoff_seconds": 0, "max_backoff_seconds": 0},
            ),
            node("emit", "emit", {}),
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "request"},
            {"id": "b", "source": "request", "target": "emit"},
        ],
    }
    http = FakeHttp([503, 200])
    storage, run_id, count, events = await execute(tmp_path / "success", definition, http)
    assert count == 1
    assert http.calls == 2
    assert [event_type for event_type, _ in events].count("node.retrying") == 1
    assert (await storage.load_checkpoints(run_id))["request"].attempt_count == 2

    failing = FakeHttp([503])
    with pytest.raises(HttpStatusError):
        await execute(tmp_path / "failure", definition, failing)
    assert failing.calls == 2


@pytest.mark.asyncio
async def test_completed_nodes_restore_without_duplicate_results(tmp_path):
    definition = {
        "name": "Checkpoint",
        "nodes": [
            node("start", "start", {"urls": ["https://example.com/item"]}),
            node("emit", "emit", {}),
        ],
        "edges": [{"id": "a", "source": "start", "target": "emit"}],
    }
    storage, run_id, count, _ = await execute(tmp_path, definition)
    flow = await storage.get_run_flow(run_id)
    assert flow is not None and count == 1
    replay_events: list[str] = []

    async def event(event_type: str, _level: str, _message: str, _data: dict[str, Any]):
        replay_events.append(event_type)

    async def progress(_node: str, _message: str, _processed: int):
        return None

    replay_count = await FlowEngine(storage, FakeHttp()).execute(
        run_id, flow, {}, asyncio.Event(), event, progress
    )
    assert replay_count == 1
    assert replay_events == ["node.restored", "node.restored"]
    assert await storage.count_items(run_id) == 1


@pytest.mark.asyncio
async def test_schedule_timezone_lease_and_idempotent_fire(tmp_path):
    service = CrawlerService(Settings(data_dir=tmp_path, worker_count=1))
    await service.storage.initialize()
    flow = await service.storage.create_flow(
        FlowDefinition.model_validate(
            {
                "name": "Scheduled",
                "nodes": [
                    node("start", "start", {"urls": ["https://example.com/item"]}),
                    node("emit", "emit", {}),
                ],
                "edges": [{"id": "a", "source": "start", "target": "emit"}],
            }
        )
    )
    definition = ScheduleDefinition(
        flow_id=flow.id,
        name="Every minute",
        cron="* * * * *",
        timezone="Asia/Shanghai",
    )
    next_run = service._next_occurrence(definition, utc_now())
    schedule = await service.storage.create_schedule(definition, utc_now())
    first, second = await asyncio.gather(
        service.storage.claim_due_schedules("one", utc_now(), lease_seconds=30),
        service.storage.claim_due_schedules("two", utc_now(), lease_seconds=30),
    )
    assert sum(len(value) for value in (first, second)) == 1
    claimed = (first or second)[0]
    owner = "one" if first else "two"
    assert claimed.id == schedule.id
    await service.storage.complete_schedule_fire(
        schedule.id,
        owner,
        fired_at=claimed.next_run_at,
        next_run_at=next_run,
        last_run_id=None,
        last_error=None,
    )
    assert (await service.storage.get_schedule(schedule.id)).next_run_at == next_run

    idempotent = await service.storage.create_schedule(definition, utc_now())
    claimed = await service.storage.claim_due_schedules(
        service._scheduler_owner, utc_now(), lease_seconds=30
    )
    claimed_schedule = next(item for item in claimed if item.id == idempotent.id)
    await service._fire_schedule(claimed_schedule)
    await service._fire_schedule(claimed_schedule)
    runs = await service.storage.list_runs()
    assert len(runs) == 1
    assert runs[0].idempotency_key == (
        f"schedule:{idempotent.id}:{claimed_schedule.next_run_at.isoformat()}"
    )
    await service.http.close()
