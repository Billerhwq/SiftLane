from __future__ import annotations

import asyncio

import pytest

from siftlane_engine.models import FlowDefinition, RunStatus, utc_now
from siftlane_engine.storage import Storage


def definition(name: str, url: str) -> FlowDefinition:
    return FlowDefinition.model_validate(
        {
            "name": name,
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "name": "Start",
                    "config": {"urls": [url]},
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
async def test_run_keeps_immutable_flow_snapshot(tmp_path):
    storage = Storage(tmp_path / "crawler.db")
    await storage.initialize()
    original = await storage.create_flow(
        definition("Original", "https://example.com/original")
    )
    run, created = await storage.create_run(original, {}, None)
    assert created is True

    updated = await storage.update_flow(
        original.id,
        definition("Updated", "https://example.com/updated"),
        expected_revision=1,
    )
    assert updated is not None and updated.revision == 2

    snapshot = await storage.get_run_flow_snapshot(run.id)
    assert snapshot is not None
    assert snapshot.flow_revision == 1
    assert snapshot.definition.name == "Original"
    assert snapshot.definition.nodes[0].config["urls"] == [
        "https://example.com/original"
    ]


@pytest.mark.asyncio
async def test_run_claim_is_atomic(tmp_path):
    storage = Storage(tmp_path / "crawler.db")
    await storage.initialize()
    flow = await storage.create_flow(definition("Atomic", "https://example.com"))
    run, _ = await storage.create_run(flow, {}, None)

    claims = await asyncio.gather(
        storage.claim_run(run.id, worker_index=0, started_at=utc_now()),
        storage.claim_run(run.id, worker_index=1, started_at=utc_now()),
    )
    claimed = [claim for claim in claims if claim is not None]
    assert len(claimed) == 1
    assert claimed[0].status == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_recovery_requeues_running_and_finishes_cancelling(tmp_path):
    storage = Storage(tmp_path / "crawler.db")
    await storage.initialize()
    flow = await storage.create_flow(definition("Recovery", "https://example.com"))
    running, _ = await storage.create_run(flow, {}, "running")
    cancelling, _ = await storage.create_run(flow, {}, "cancelling")
    await storage.update_run(running.id, status=RunStatus.RUNNING)
    await storage.update_run(cancelling.id, status=RunStatus.CANCELLING)

    plan = await storage.recover_runs()
    assert running.id in plan.recovered
    assert running.id in plan.requeued
    assert cancelling.id in plan.cancelled
    assert (await storage.get_run(running.id)).status == RunStatus.QUEUED
    cancelled = await storage.get_run(cancelling.id)
    assert cancelled.status == RunStatus.CANCELLED
    assert cancelled.finished_at is not None
