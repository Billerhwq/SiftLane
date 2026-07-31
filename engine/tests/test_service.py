from __future__ import annotations

import pytest

from siftlane_engine.config import Settings
from siftlane_engine.models import FlowDefinition, RunCreate, RunStatus, utc_now
from siftlane_engine.service import CrawlerService


def definition() -> FlowDefinition:
    return FlowDefinition.model_validate(
        {
            "name": "Service fixture",
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "name": "Start",
                    "config": {"urls": ["https://example.com/item"]},
                },
                {
                    "id": "emit",
                    "type": "emit",
                    "name": "Emit",
                    "config": {},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "emit"}],
        }
    )


@pytest.mark.asyncio
async def test_queued_cancellation_emits_terminal_event(tmp_path):
    service = CrawlerService(Settings(data_dir=tmp_path, worker_count=1))
    await service.storage.initialize()
    try:
        flow = await service.create_flow(definition())
        run = await service.create_run(RunCreate(flow_id=flow.id))
        cancelled = await service.cancel_run(run.id)
        assert cancelled.status == RunStatus.CANCELLED
        events = await service.storage.list_events(run.id)
        assert events[-1].type == "run.cancelled"
    finally:
        await service.http.close()


@pytest.mark.asyncio
async def test_terminal_subscription_replays_and_closes(tmp_path):
    service = CrawlerService(Settings(data_dir=tmp_path, worker_count=1))
    await service.storage.initialize()
    try:
        flow = await service.create_flow(definition())
        run, _ = await service.storage.create_run(flow, {}, None)
        await service.storage.add_event(run.id, "run.started", "info", "Started")
        await service.storage.add_event(run.id, "run.completed", "success", "Done")
        await service.storage.update_run(
            run.id,
            status=RunStatus.SUCCEEDED,
            finished_at=utc_now(),
        )
        replay = [event async for event in service.subscribe(run.id, after=1)]
        assert [event.type for event in replay] == ["run.completed"]
    finally:
        await service.http.close()
